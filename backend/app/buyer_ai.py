from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from .compare import require_buyer
from .database import get_db
from .marketplace import BatchResponse
from .models import ActivityEvent, Favorite, InventoryBatch, Order, OrderItem, Product, Store, User


router = APIRouter(prefix="/api/ai", tags=["ai-recommendations"])

MODEL_VERSION = "buyer-content-pref-v1"
METHOD_NAME = "tfidf_behavioral_preference"
BASELINE_NAME = "discount_expiry_baseline"
MIN_INTERACTIONS = 3
TIME_DECAY_DAYS = 14.0

EVENT_WEIGHTS: dict[str, float] = {
    "view_batch": 1.0,
    "favorite_add": 2.5,
    "booking_created": 4.0,
}

TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]{2,}")


class EventRecordedResponse(BaseModel):
    event_id: UUID
    event_type: str
    batch_id: UUID


class RecommendationItem(BaseModel):
    score: float
    baseline_score: float
    lift_vs_baseline: float
    reason_codes: list[str]
    explanation: str
    batch: BatchResponse


class BuyerRecommendationsResponse(BaseModel):
    status: Literal["ok", "insufficient_data"]
    model_version: str = MODEL_VERSION
    method: str = METHOD_NAME
    baseline_used: str = BASELINE_NAME
    data_sources: list[str]
    current_interactions: int
    required_interactions: int = MIN_INTERACTIONS
    reason: str | None = None
    items: list[RecommendationItem]


def _tokenize_batch(batch: InventoryBatch) -> list[str]:
    text_parts = [
        batch.product.name or "",
        batch.product.description or "",
        batch.store.name or "",
        batch.store.city or "",
        batch.product.unit or "",
    ]
    return [tok.lower() for tok in TOKEN_PATTERN.findall(" ".join(text_parts))]


def _compute_tfidf(docs: dict[UUID, list[str]]) -> dict[UUID, dict[str, float]]:
    n_docs = max(len(docs), 1)
    doc_freq: Counter[str] = Counter()
    for tokens in docs.values():
        doc_freq.update(set(tokens))

    vectors: dict[UUID, dict[str, float]] = {}
    for doc_id, tokens in docs.items():
        if not tokens:
            vectors[doc_id] = {}
            continue
        tf = Counter(tokens)
        total = float(len(tokens))
        vec: dict[str, float] = {}
        for tok, count in tf.items():
            idf = math.log((1.0 + n_docs) / (1.0 + doc_freq[tok])) + 1.0
            vec[tok] = (count / total) * idf
        vectors[doc_id] = vec
    return vectors


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(val * b.get(tok, 0.0) for tok, val in a.items())
    if dot <= 0.0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _discount_ratio(batch: InventoryBatch) -> float:
    reg = float(batch.regular_price)
    disc = float(batch.discount_price)
    if reg <= 0.0 or disc >= reg:
        return 0.0
    return (reg - disc) / reg


def _build_reasons(
    *,
    text_sim: float,
    store_match: float,
    unit_match: float,
    price_fit: float,
    discount_pct: float,
) -> tuple[list[str], str]:
    codes: list[str] = []
    phrases: list[str] = []
    if text_sim >= 0.25:
        codes.append("text_similarity")
        phrases.append("бұрын қараған немесе таңдаған өнімдеріңізге ұқсас")
    if store_match >= 0.5:
        codes.append("preferred_store")
        phrases.append("сіз жиі таңдайтын дүкеннен")
    if unit_match >= 0.5:
        codes.append("preferred_unit")
    if price_fit >= 0.65:
        codes.append("price_fit")
        phrases.append("бағасы сіздің таңдауыңызға сәйкес")
    if discount_pct >= 25.0:
        codes.append("high_discount")
        phrases.append(f"жеңілдігі −{discount_pct:.0f}%")

    if not phrases:
        explanation = "Сіздің нақты әрекеттеріңіз бен ағымдағы жеңілдіктер негізінде іріктелді."
    else:
        joined = ", ".join(phrases)
        explanation = joined[0].upper() + joined[1:] + "."
    return codes, explanation


@router.post("/events/view/{batch_id}", response_model=EventRecordedResponse, status_code=201)
def record_batch_view(
    batch_id: UUID,
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
) -> EventRecordedResponse:
    batch = db.get(InventoryBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    event = ActivityEvent(user_id=buyer.id, event_type="view_batch", batch_id=batch_id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventRecordedResponse(event_id=event.id, event_type=event.event_type, batch_id=batch_id)


@router.get("/recommendations", response_model=BuyerRecommendationsResponse)
def get_buyer_recommendations(
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
    limit: int = Query(default=6, ge=1, le=20),
) -> BuyerRecommendationsResponse:
    now = datetime.now(timezone.utc)
    data_sources = ["activity_events", "favorites", "orders", "inventory_batches"]

    # 1. Load real positive interaction signals for this buyer from PostgreSQL
    events = list(
        db.scalars(
            select(ActivityEvent)
            .where(
                ActivityEvent.user_id == buyer.id,
                ActivityEvent.event_type.in_(tuple(EVENT_WEIGHTS.keys())),
                ActivityEvent.batch_id.is_not(None),
            )
            .order_by(ActivityEvent.created_at.desc())
            .limit(200)
        ).all()
    )

    interactions: list[tuple[UUID, float, datetime]] = []
    seen_event_keys: set[tuple[str, UUID]] = set()
    for ev in events:
        if ev.batch_id is None:
            continue
        base_w = EVENT_WEIGHTS[ev.event_type]
        interactions.append((ev.batch_id, base_w, ev.created_at))
        seen_event_keys.add((ev.event_type, ev.batch_id))

    # Include pre-existing favorites and orders if not already represented in activity_events
    favs = list(db.scalars(select(Favorite).where(Favorite.user_id == buyer.id)).all())
    for fav in favs:
        if ("favorite_add", fav.batch_id) not in seen_event_keys:
            interactions.append((fav.batch_id, EVENT_WEIGHTS["favorite_add"], fav.created_at))

    order_rows = db.execute(
        select(OrderItem.batch_id, Order.created_at)
        .join(OrderItem.order)
        .where(Order.buyer_user_id == buyer.id)
    ).all()
    for batch_id, created_at in order_rows:
        if ("booking_created", batch_id) not in seen_event_keys:
            interactions.append((batch_id, EVENT_WEIGHTS["booking_created"], created_at))

    current_count = len(interactions)
    if current_count < MIN_INTERACTIONS:
        return BuyerRecommendationsResponse(
            status="insufficient_data",
            data_sources=data_sources,
            current_interactions=current_count,
            required_interactions=MIN_INTERACTIONS,
            reason=(
                f"Жеке AI ұсыныстары үшін кемінде {MIN_INTERACTIONS} нақты әрекет "
                f"(өнімді қарау, таңдаулыларға қосу немесе брондау) қажет. "
                f"Қазір: {current_count}/{MIN_INTERACTIONS}."
            ),
            items=[],
        )

    # 2. Load candidate available, non-expired catalog batches
    candidates = list(
        db.scalars(
            select(InventoryBatch)
            .join(InventoryBatch.product)
            .join(InventoryBatch.store)
            .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
            .where(
                InventoryBatch.status == "active",
                InventoryBatch.quantity_available > 0,
                InventoryBatch.expires_at > now,
                Product.is_active.is_(True),
                Store.is_active.is_(True),
            )
        ).all()
    )
    if not candidates:
        return BuyerRecommendationsResponse(
            status="insufficient_data",
            data_sources=data_sources,
            current_interactions=current_count,
            required_interactions=MIN_INTERACTIONS,
            reason="Қазір ұсынылатын қолжетімді және мерзімі өтпеген партиялар жоқ.",
            items=[],
        )

    # 3. Load interacted batches (including historical/sold-out ones to learn real preferences)
    interacted_ids = {bid for bid, _, _ in interactions}
    candidate_map = {b.id: b for b in candidates}
    missing_ids = interacted_ids - set(candidate_map.keys())
    all_batches: dict[UUID, InventoryBatch] = dict(candidate_map)
    if missing_ids:
        hist_batches = list(
            db.scalars(
                select(InventoryBatch)
                .join(InventoryBatch.product)
                .join(InventoryBatch.store)
                .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
                .where(InventoryBatch.id.in_(missing_ids))
            ).all()
        )
        for b in hist_batches:
            all_batches[b.id] = b

    docs = {bid: _tokenize_batch(b) for bid, b in all_batches.items()}
    tfidf = _compute_tfidf(docs)

    # 4. Build time-decayed user preference profile
    profile_vec: dict[str, float] = defaultdict(float)
    store_weights: dict[UUID, float] = defaultdict(float)
    unit_weights: dict[str, float] = defaultdict(float)
    weighted_price_sum = 0.0
    total_weight = 0.0

    for bid, base_w, ts in interactions:
        batch = all_batches.get(bid)
        if batch is None:
            continue
        age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
        weight = base_w * math.exp(-age_days / TIME_DECAY_DAYS)
        total_weight += weight
        store_weights[batch.store_id] += weight
        unit_weights[batch.product.unit] += weight
        weighted_price_sum += float(batch.discount_price) * weight
        for tok, val in tfidf.get(bid, {}).items():
            profile_vec[tok] += val * weight

    if total_weight <= 0.0:
        return BuyerRecommendationsResponse(
            status="insufficient_data",
            data_sources=data_sources,
            current_interactions=0,
            required_interactions=MIN_INTERACTIONS,
            reason="Ұсыныс есептеу үшін жарамды әрекет деректері жеткіліксіз.",
            items=[],
        )

    preferred_price = weighted_price_sum / total_weight
    max_store_w = max(store_weights.values(), default=1.0)
    max_unit_w = max(unit_weights.values(), default=1.0)

    # Normalize candidate deal metrics for baseline and deal_quality
    cand_hours = [max(0.0, (b.expires_at - now).total_seconds() / 3600.0) for b in candidates]
    min_h, max_h = min(cand_hours), max(cand_hours)

    scored_items: list[RecommendationItem] = []
    for batch, hrs in zip(candidates, cand_hours):
        text_sim = _cosine_similarity(profile_vec, tfidf.get(batch.id, {}))
        store_aff = store_weights.get(batch.store_id, 0.0) / max_store_w if max_store_w > 0 else 0.0
        unit_aff = unit_weights.get(batch.product.unit, 0.0) / max_unit_w if max_unit_w > 0 else 0.0
        affinity = 0.65 * store_aff + 0.35 * unit_aff

        price = float(batch.discount_price)
        if preferred_price > 0:
            price_diff_ratio = abs(price - preferred_price) / max(preferred_price, 1.0)
            price_fit = max(0.0, 1.0 - min(price_diff_ratio, 1.0))
        else:
            price_fit = 0.5

        disc_ratio = _discount_ratio(batch)
        freshness_norm = 1.0 if max_h <= min_h else (hrs - min_h) / (max_h - min_h)
        baseline_score = round(0.60 * disc_ratio + 0.40 * freshness_norm, 4)

        ai_score = round(
            0.45 * text_sim + 0.25 * affinity + 0.15 * price_fit + 0.15 * baseline_score,
            4,
        )
        lift = round(ai_score - baseline_score, 4)
        codes, explanation = _build_reasons(
            text_sim=text_sim,
            store_match=store_aff,
            unit_match=unit_aff,
            price_fit=price_fit,
            discount_pct=disc_ratio * 100.0,
        )
        scored_items.append(
            RecommendationItem(
                score=ai_score,
                baseline_score=baseline_score,
                lift_vs_baseline=lift,
                reason_codes=codes,
                explanation=explanation,
                batch=BatchResponse.model_validate(batch),
            )
        )

    scored_items.sort(key=lambda item: (item.score, item.baseline_score), reverse=True)
    return BuyerRecommendationsResponse(
        status="ok",
        data_sources=data_sources,
        current_interactions=current_count,
        required_interactions=MIN_INTERACTIONS,
        items=scored_items[:limit],
    )
