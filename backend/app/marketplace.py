from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, selectinload

from .database import get_db
from .dependencies import require_seller
from .models import InventoryBatch, PriceHistory, Product, Store, User


router = APIRouter(prefix="/api")


class StoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class StoreSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    address: str
    city: str


class StoreResponse(StoreSummary):
    id: UUID
    description: str | None
    is_active: bool


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=180)
    unit: Literal["piece", "kg", "portion"] = "piece"
    description: str | None = Field(default=None, max_length=2000)


class ProductSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    unit: Literal["piece", "kg", "portion"]
    description: str | None


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: ProductCreate
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    regular_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    discount_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    expires_at: AwareDatetime

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_in_future(cls, value: datetime) -> datetime:
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return value

    @model_validator(mode="after")
    def discount_cannot_exceed_regular_price(self) -> "BatchCreate":
        if self.discount_price > self.regular_price:
            raise ValueError("discount_price must not exceed regular_price")
        return self


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: UUID = Field(validation_alias="id")
    store_id: UUID
    product_id: UUID
    product: ProductSummary
    store: StoreSummary
    quantity_available: Decimal
    regular_price: Decimal
    discount_price: Decimal
    currency: Literal["KZT"]
    expires_at: datetime


class SellerBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: UUID = Field(validation_alias="id")
    product_id: UUID
    product: ProductSummary
    quantity_total: Decimal
    quantity_available: Decimal
    regular_price: Decimal
    discount_price: Decimal
    currency: Literal["KZT"]
    expires_at: datetime
    status: Literal["active", "paused", "sold_out", "expired"]
    created_at: datetime
    updated_at: datetime


class SellerBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "paused"] | None = None
    discount_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def require_a_change(self) -> "SellerBatchUpdate":
        if self.status is None and self.discount_price is None:
            raise ValueError("Provide status or discount_price")
        return self


@router.get("/seller/store", response_model=StoreResponse, tags=["seller"])
def get_store(seller: User = Depends(require_seller), db: Session = Depends(get_db)):
    store = db.scalar(select(Store).where(Store.owner_user_id == seller.id))
    if store is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller has no store")
    return store


@router.post("/seller/store", response_model=StoreResponse, status_code=201, tags=["seller"])
def create_store(
    payload: StoreCreate,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    store = Store(owner_user_id=seller.id, **payload.model_dump())
    db.add(store)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_stores_owner_user_id":
            raise HTTPException(status_code=409, detail="Seller already has a store") from exc
        raise
    return store


@router.post("/seller/batches", response_model=BatchResponse, status_code=201, tags=["seller"])
def publish_batch(
    payload: BatchCreate,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
):
    store = db.scalar(select(Store).where(Store.owner_user_id == seller.id, Store.is_active.is_(True)))
    if store is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active store is required")

    batch = InventoryBatch(
        store=store,
        product=Product(**payload.product.model_dump()),
        quantity_total=payload.quantity,
        quantity_available=payload.quantity,
        regular_price=payload.regular_price,
        discount_price=payload.discount_price,
        expires_at=payload.expires_at,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/seller/batches", response_model=list[SellerBatchResponse], tags=["seller"])
def list_seller_batches(
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> list[InventoryBatch]:
    return list(
        db.scalars(
            select(InventoryBatch)
            .join(InventoryBatch.store)
            .options(selectinload(InventoryBatch.product))
            .where(Store.owner_user_id == seller.id)
            .order_by(InventoryBatch.created_at.desc(), InventoryBatch.id.desc())
        ).all()
    )


@router.patch("/seller/batches/{batch_id}", response_model=SellerBatchResponse, tags=["seller"])
def update_seller_batch(
    batch_id: UUID,
    payload: SellerBatchUpdate,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> InventoryBatch:
    batch = db.scalar(
        select(InventoryBatch)
        .join(InventoryBatch.store)
        .options(selectinload(InventoryBatch.product))
        .where(InventoryBatch.id == batch_id, Store.owner_user_id == seller.id)
        .with_for_update(of=InventoryBatch)
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    if payload.status is not None:
        if payload.status == "paused" and batch.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active batches can be paused")
        if payload.status == "active" and batch.status != "paused":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only paused batches can be activated")
        batch.status = payload.status

    if payload.discount_price is not None:
        if payload.discount_price > batch.regular_price:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Discount price must not exceed regular price",
            )
        if payload.discount_price != batch.discount_price:
            db.add(
                PriceHistory(
                    batch_id=batch.id,
                    old_discount_price=batch.discount_price,
                    new_discount_price=payload.discount_price,
                    changed_by_user_id=seller.id,
                )
            )
            batch.discount_price = payload.discount_price

    db.commit()
    db.refresh(batch)
    return batch


@router.get("/catalog", response_model=list[BatchResponse], tags=["catalog"])
def list_catalog(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=180, description="Search by product name"),
    city: str | None = Query(default=None, max_length=120, description="Filter by store city"),
    unit: Literal["piece", "kg", "portion"] | None = Query(default=None, description="Filter by unit"),
    max_price: Decimal | None = Query(default=None, ge=0, description="Maximum discount price in KZT"),
    min_discount: int | None = Query(default=None, ge=0, le=100, description="Minimum discount percentage"),
    sort: Literal["expires_asc", "price_asc", "price_desc", "discount_desc"] = Query(
        default="expires_asc",
        description="Sort order",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = (
        select(InventoryBatch)
        .join(InventoryBatch.product)
        .join(InventoryBatch.store)
        .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
        .where(
            InventoryBatch.status == "active",
            InventoryBatch.quantity_available > 0,
            InventoryBatch.expires_at > func.now(),
            Product.is_active.is_(True),
            Store.is_active.is_(True),
        )
    )
    search = q.strip() if q else ""
    if search:
        query = query.where(Product.name.icontains(search, autoescape=True))
    city_filter = city.strip() if city else ""
    if city_filter:
        query = query.where(Store.city.icontains(city_filter, autoescape=True))
    if unit is not None:
        query = query.where(Product.unit == unit)
    if max_price is not None:
        query = query.where(InventoryBatch.discount_price <= max_price)
    if min_discount is not None and min_discount > 0:
        query = query.where(
            InventoryBatch.regular_price > 0,
            (InventoryBatch.regular_price - InventoryBatch.discount_price) * 100
            >= min_discount * InventoryBatch.regular_price,
        )

    if sort == "price_asc":
        order_by = (InventoryBatch.discount_price.asc(), InventoryBatch.expires_at.asc(), InventoryBatch.id.asc())
    elif sort == "price_desc":
        order_by = (InventoryBatch.discount_price.desc(), InventoryBatch.expires_at.asc(), InventoryBatch.id.asc())
    elif sort == "discount_desc":
        discount_ratio = case(
            (
                InventoryBatch.regular_price > 0,
                (InventoryBatch.regular_price - InventoryBatch.discount_price) / InventoryBatch.regular_price,
            ),
            else_=0,
        )
        order_by = (discount_ratio.desc(), InventoryBatch.expires_at.asc(), InventoryBatch.id.asc())
    else:
        order_by = (InventoryBatch.expires_at.asc(), InventoryBatch.id.asc())

    query = query.order_by(*order_by).offset(offset).limit(limit)
    return db.scalars(query).all()


@router.get("/catalog/{batch_id}", response_model=BatchResponse, tags=["catalog"])
def get_catalog_batch(batch_id: UUID, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(InventoryBatch)
        .join(InventoryBatch.product)
        .join(InventoryBatch.store)
        .options(contains_eager(InventoryBatch.product), contains_eager(InventoryBatch.store))
        .where(
            InventoryBatch.id == batch_id,
            InventoryBatch.status == "active",
            InventoryBatch.quantity_available > 0,
            InventoryBatch.expires_at > func.now(),
            Product.is_active.is_(True),
            Store.is_active.is_(True),
        )
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return batch
