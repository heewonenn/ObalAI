from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from .database import get_db
from .dependencies import get_current_user
from .marketplace import BatchResponse
from .models import Favorite, InventoryBatch, Product, Store, User


router = APIRouter(prefix="/api", tags=["favorites-compare"])

WSM_VERSION = "wsm-v1-no-distance"
DEFAULT_WEIGHTS = {
    "discount": Decimal("0.45"),
    "freshness": Decimal("0.35"),
    "price": Decimal("0.20"),
}


def require_buyer(user: User = Depends(get_current_user)) -> User:
    if user.role != "buyer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Buyer role required")
    return user


class FavoriteActionResponse(BaseModel):
    batch_id: UUID
    saved: bool


class FavoriteItemResponse(BaseModel):
    batch: BatchResponse
    added_at: datetime
    is_available: bool


class WsmWeightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount: Decimal = Field(default=DEFAULT_WEIGHTS["discount"], ge=0, le=1)
    freshness: Decimal = Field(default=DEFAULT_WEIGHTS["freshness"], ge=0, le=1)
    price: Decimal = Field(default=DEFAULT_WEIGHTS["price"], ge=0, le=1)

    @model_validator(mode="after")
    def sum_must_be_positive(self) -> "WsmWeightsInput":
        if (self.discount + self.freshness + self.price) <= 0:
            raise ValueError("Sum of weights must be positive")
        return self


class WsmCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_ids: list[UUID] = Field(min_length=1, max_length=10)
    weights: WsmWeightsInput | None = None


class WsmNormalizedScores(BaseModel):
    discount: float
    freshness: float
    price: float


class WsmItemResult(BaseModel):
    rank: int
    score: float
    discount_percent: float
    hours_left: float
    normalized: WsmNormalizedScores
    explanation: str
    batch: BatchResponse


class WsmCompareResponse(BaseModel):
    status: Literal["ok", "insufficient_data"]
    method: Literal["WSM"] = "WSM"
    version: str = WSM_VERSION
    excluded_criteria: list[str]
    weights_used: dict[str, float]
    reason: str | None = None
    items: list[WsmItemResult]


@router.get("/favorites", response_model=list[FavoriteItemResponse])
def list_favorites(
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
) -> list[FavoriteItemResponse]:
    rows = db.execute(
        select(Favorite, InventoryBatch)
        .join(Favorite.batch)
        .join(InventoryBatch.product)
        .join(InventoryBatch.store)
        .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
        .where(Favorite.user_id == buyer.id)
        .order_by(Favorite.created_at.desc())
    ).all()

    now = datetime.now(timezone.utc)
    result: list[FavoriteItemResponse] = []
    for fav, batch in rows:
        available = (
            batch.status == "active"
            and batch.quantity_available > 0
            and batch.expires_at > now
            and batch.product.is_active
            and batch.store.is_active
        )
        result.append(
            FavoriteItemResponse(
                batch=BatchResponse.model_validate(batch),
                added_at=fav.created_at,
                is_available=available,
            )
        )
    return result


@router.post("/favorites/{batch_id}", response_model=FavoriteActionResponse, status_code=201)
def add_favorite(
    batch_id: UUID,
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
) -> FavoriteActionResponse:
    batch = db.get(InventoryBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    existing = db.get(Favorite, (buyer.id, batch_id))
    if existing is None:
        db.add(Favorite(user_id=buyer.id, batch_id=batch_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return FavoriteActionResponse(batch_id=batch_id, saved=True)


@router.delete("/favorites/{batch_id}", response_model=FavoriteActionResponse)
def remove_favorite(
    batch_id: UUID,
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
) -> FavoriteActionResponse:
    existing = db.get(Favorite, (buyer.id, batch_id))
    if existing is not None:
        db.delete(existing)
        db.commit()
    return FavoriteActionResponse(batch_id=batch_id, saved=False)


def _normalize_benefit(value: float, min_val: float, max_val: float) -> float:
    if max_val <= min_val:
        return 1.0
    return (value - min_val) / (max_val - min_val)


def _normalize_cost(value: float, min_val: float, max_val: float) -> float:
    if max_val <= min_val:
        return 1.0
    return (max_val - value) / (max_val - min_val)


def _round4(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _build_explanation(norm: WsmNormalizedScores, discount_pct: float, hours_left: float) -> str:
    parts: list[str] = []
    if norm.discount >= 0.7:
        parts.append(f"жоғары жеңілдік ({discount_pct:.0f}%)")
    if norm.freshness >= 0.7:
        parts.append(f"ұзақ жарамдылық ({hours_left:.1f} сағ)")
    if norm.price >= 0.7:
        parts.append("ең тиімді баға")
    if not parts:
        return "Барлық өлшемшарттар бойынша теңгерімді ұсыныс."
    return "Артықшылығы: " + ", ".join(parts) + "."


@router.post("/compare/wsm", response_model=WsmCompareResponse)
def compare_wsm(
    payload: WsmCompareRequest,
    db: Session = Depends(get_db),
) -> WsmCompareResponse:
    raw_weights = payload.weights or WsmWeightsInput()
    total_w = raw_weights.discount + raw_weights.freshness + raw_weights.price
    w_discount = float(raw_weights.discount / total_w)
    w_freshness = float(raw_weights.freshness / total_w)
    w_price = float(raw_weights.price / total_w)
    weights_used = {
        "discount": _round4(w_discount),
        "freshness": _round4(w_freshness),
        "price": _round4(w_price),
    }

    unique_ids = list(dict.fromkeys(payload.batch_ids))
    now = datetime.now(timezone.utc)
    batches = list(
        db.scalars(
            select(InventoryBatch)
            .join(InventoryBatch.product)
            .join(InventoryBatch.store)
            .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
            .where(
                InventoryBatch.id.in_(unique_ids),
                InventoryBatch.status == "active",
                InventoryBatch.quantity_available > 0,
                InventoryBatch.expires_at > now,
                Product.is_active.is_(True),
                Store.is_active.is_(True),
            )
        ).all()
    )

    if len(batches) < 2:
        return WsmCompareResponse(
            status="insufficient_data",
            excluded_criteria=["distance"],
            weights_used=weights_used,
            reason="WSM салыстыруы үшін кемінде 2 қолжетімді және мерзімі өтпеген партия қажет.",
            items=[],
        )

    metrics: list[tuple[InventoryBatch, float, float, float]] = []
    for batch in batches:
        reg = float(batch.regular_price)
        disc = float(batch.discount_price)
        discount_ratio = ((reg - disc) / reg) if reg > 0 and disc < reg else 0.0
        hours_left = max(0.0, (batch.expires_at - now).total_seconds() / 3600.0)
        metrics.append((batch, discount_ratio, hours_left, disc))

    discounts = [m[1] for m in metrics]
    hours = [m[2] for m in metrics]
    prices = [m[3] for m in metrics]

    min_d, max_d = min(discounts), max(discounts)
    min_h, max_h = min(hours), max(hours)
    min_p, max_p = min(prices), max(prices)

    scored: list[tuple[float, float, WsmItemResult]] = []
    for batch, disc_ratio, hrs, price in metrics:
        n_disc = _normalize_benefit(disc_ratio, min_d, max_d)
        n_fresh = _normalize_benefit(hrs, min_h, max_h)
        n_price = _normalize_cost(price, min_p, max_p)
        score = w_discount * n_disc + w_freshness * n_fresh + w_price * n_price
        norm = WsmNormalizedScores(
            discount=_round4(n_disc),
            freshness=_round4(n_fresh),
            price=_round4(n_price),
        )
        disc_pct = round(disc_ratio * 100.0, 1)
        hrs_rounded = round(hrs, 1)
        item = WsmItemResult(
            rank=0,
            score=_round4(score),
            discount_percent=disc_pct,
            hours_left=hrs_rounded,
            normalized=norm,
            explanation=_build_explanation(norm, disc_pct, hrs_rounded),
            batch=BatchResponse.model_validate(batch),
        )
        scored.append((item.score, -price, item))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    ranked_items: list[WsmItemResult] = []
    for idx, (_, _, item) in enumerate(scored, start=1):
        item.rank = idx
        ranked_items.append(item)

    return WsmCompareResponse(
        status="ok",
        excluded_criteria=["distance"],
        weights_used=weights_used,
        items=ranked_items,
    )
