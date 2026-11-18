from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_current_user
from .models import InventoryBatch, Order, OrderItem, Product, Store, User


router = APIRouter(prefix="/api", tags=["orders"])
CENT = Decimal("0.01")
QUANTITY_STEP = Decimal("0.001")
MAX_ORDER_TOTAL = Decimal("9999999999.99")


class ReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class ReservationResponse(BaseModel):
    id: UUID
    batch_id: UUID
    store_id: UUID
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal
    currency: Literal["KZT"]
    status: str


def reservation_response(order: Order, item: OrderItem) -> ReservationResponse:
    return ReservationResponse(
        id=order.id,
        batch_id=item.batch_id,
        store_id=order.store_id,
        quantity=item.quantity,
        unit_price=item.unit_price,
        total_amount=order.total_amount,
        currency=order.currency,
        status=order.status,
    )


@router.post(
    "/orders",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": ReservationResponse, "description": "Existing reservation"}},
)
def reserve_batch(
    payload: ReservationRequest,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    buyer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReservationResponse:
    if buyer.role != "buyer":
        raise HTTPException(status_code=403, detail="Buyer role required")

    # Serialize retries of the same request before checking inventory.
    lock_key = func.hashtextextended(f"obalai:booking:{buyer.id}:{idempotency_key}", 0)
    db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    existing = db.execute(
        select(Order, OrderItem).join(Order.items).where(
            Order.buyer_user_id == buyer.id,
            Order.idempotency_key == idempotency_key,
        )
    ).one_or_none()
    if existing is not None:
        order, item = existing
        if item.batch_id != payload.batch_id or item.quantity != payload.quantity:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key already used for a different reservation",
            )
        response.status_code = status.HTTP_200_OK
        return reservation_response(order, item)

    batch = db.scalar(
        select(InventoryBatch)
        .join(InventoryBatch.store)
        .join(InventoryBatch.product)
        .where(
            InventoryBatch.id == payload.batch_id,
            Store.is_active.is_(True),
            Product.is_active.is_(True),
        )
        .with_for_update(of=InventoryBatch)
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.expires_at <= datetime.now(timezone.utc) or batch.status not in {"active", "sold_out"}:
        raise HTTPException(status_code=409, detail="Batch is not available")
    if batch.status == "sold_out" or batch.quantity_available < payload.quantity:
        raise HTTPException(status_code=409, detail="Not enough stock")

    total = (batch.discount_price * payload.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    if total > MAX_ORDER_TOTAL:
        raise HTTPException(status_code=422, detail="Order total is too large")

    item = OrderItem(
        batch_id=batch.id,
        quantity=payload.quantity.quantize(QUANTITY_STEP),
        unit_price=batch.discount_price,
        line_total=total,
    )
    order = Order(
        buyer_user_id=buyer.id,
        store_id=batch.store_id,
        idempotency_key=idempotency_key,
        status="reserved",
        fulfillment_method="pickup",
        total_amount=total,
        currency=batch.currency,
        items=[item],
    )
    batch.quantity_available -= payload.quantity
    if batch.quantity_available == 0:
        batch.status = "sold_out"
    db.add(order)
    db.commit()
    return reservation_response(order, item)
