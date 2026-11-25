from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .dependencies import get_current_user
from .marketplace import StoreSummary
from .models import ActivityEvent, InventoryBatch, Order, OrderItem, Product, Store, User


router = APIRouter(prefix="/api", tags=["orders"])
CENT = Decimal("0.01")
QUANTITY_STEP = Decimal("0.001")
MAX_ORDER_TOTAL = Decimal("9999999999.99")


class ReservationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class ReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    items: list[ReservationItemInput] | None = Field(default=None, min_length=1, max_length=20)
    fulfillment_method: Literal["pickup", "delivery"] = "pickup"
    delivery_address: str | None = Field(default=None, max_length=500)
    payment_method: Literal["pay_at_pickup"] = "pay_at_pickup"

    @model_validator(mode="after")
    def validate_items_and_fulfillment(self) -> "ReservationRequest":
        if self.items is None:
            if self.batch_id is None or self.quantity is None:
                raise ValueError("Provide either items or batch_id and quantity")
        else:
            if self.batch_id is not None or self.quantity is not None:
                raise ValueError("Provide either items or batch_id/quantity, not both")

        cleaned_address = self.delivery_address.strip() if self.delivery_address else ""
        if self.fulfillment_method == "delivery":
            if not cleaned_address:
                raise ValueError("delivery_address is required when fulfillment_method is delivery")
            self.delivery_address = cleaned_address
        else:
            self.delivery_address = None
        return self

    def normalized_items(self) -> list[tuple[UUID, Decimal]]:
        merged: dict[UUID, Decimal] = {}
        raw = self.items or [ReservationItemInput(batch_id=self.batch_id, quantity=self.quantity)]
        for entry in raw:
            qty = entry.quantity.quantize(QUANTITY_STEP)
            merged[entry.batch_id] = (merged.get(entry.batch_id, Decimal("0")) + qty).quantize(QUANTITY_STEP)
        return sorted(merged.items(), key=lambda pair: str(pair[0]))


class ReservationItemDetail(BaseModel):
    batch_id: UUID
    product_name: str
    unit: Literal["piece", "kg", "portion"]
    quantity: Decimal
    regular_price: Decimal
    unit_price: Decimal
    line_total: Decimal


class ReservationResponse(BaseModel):
    id: UUID
    pickup_code: str
    batch_id: UUID
    store_id: UUID
    store: StoreSummary
    quantity: Decimal
    unit_price: Decimal
    original_total: Decimal
    savings_amount: Decimal
    total_amount: Decimal
    currency: Literal["KZT"]
    status: str
    fulfillment_method: Literal["pickup", "delivery"]
    delivery_address: str | None
    payment_method: Literal["pay_at_pickup"] = "pay_at_pickup"
    items: list[ReservationItemDetail]


def reservation_response(order: Order) -> ReservationResponse:
    items = list(order.items)
    first = items[0]
    item_details: list[ReservationItemDetail] = []
    original_total = Decimal("0.00")
    for oi in items:
        reg_price = oi.batch.regular_price if oi.batch else oi.unit_price
        original_line = (reg_price * oi.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        original_total += original_line
        item_details.append(
            ReservationItemDetail(
                batch_id=oi.batch_id,
                product_name=oi.batch.product.name if oi.batch and oi.batch.product else "",
                unit=oi.batch.product.unit if oi.batch and oi.batch.product else "piece",
                quantity=oi.quantity,
                regular_price=reg_price,
                unit_price=oi.unit_price,
                line_total=oi.line_total,
            )
        )
    savings = max(Decimal("0.00"), (original_total - order.total_amount).quantize(CENT, rounding=ROUND_HALF_UP))
    return ReservationResponse(
        id=order.id,
        pickup_code=f"OB-{str(order.id)[:8].upper()}",
        batch_id=first.batch_id,
        store_id=order.store_id,
        store=StoreSummary.model_validate(order.store),
        quantity=first.quantity,
        unit_price=first.unit_price,
        original_total=original_total.quantize(CENT, rounding=ROUND_HALF_UP),
        savings_amount=savings,
        total_amount=order.total_amount,
        currency=order.currency,
        status=order.status,
        fulfillment_method=order.fulfillment_method,
        delivery_address=order.delivery_address,
        payment_method="pay_at_pickup",
        items=item_details,
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

    requested_items = payload.normalized_items()

    # Serialize retries of the same request before checking inventory.
    lock_key = func.hashtextextended(f"obalai:booking:{buyer.id}:{idempotency_key}", 0)
    db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    existing_order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.items).selectinload(OrderItem.batch).selectinload(InventoryBatch.product),
        )
        .where(
            Order.buyer_user_id == buyer.id,
            Order.idempotency_key == idempotency_key,
        )
    )
    if existing_order is not None:
        existing_sig = sorted(
            [(oi.batch_id, oi.quantity.quantize(QUANTITY_STEP)) for oi in existing_order.items],
            key=lambda pair: str(pair[0]),
        )
        if (
            existing_sig != requested_items
            or existing_order.fulfillment_method != payload.fulfillment_method
            or existing_order.delivery_address != payload.delivery_address
        ):
            raise HTTPException(
                status_code=409,
                detail="Idempotency key already used for a different reservation",
            )
        response.status_code = status.HTTP_200_OK
        return reservation_response(existing_order)

    batch_ids = [bid for bid, _ in requested_items]
    batches = list(
        db.scalars(
            select(InventoryBatch)
            .join(InventoryBatch.store)
            .join(InventoryBatch.product)
            .options(selectinload(InventoryBatch.store), selectinload(InventoryBatch.product))
            .where(
                InventoryBatch.id.in_(batch_ids),
                Store.is_active.is_(True),
                Product.is_active.is_(True),
            )
            .order_by(InventoryBatch.id)
            .with_for_update(of=InventoryBatch)
        ).all()
    )
    batch_map = {b.id: b for b in batches}

    now = datetime.now(timezone.utc)
    store_ids: set[UUID] = set()
    for bid, qty in requested_items:
        batch = batch_map.get(bid)
        if batch is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        store_ids.add(batch.store_id)
        if batch.expires_at <= now or batch.status not in {"active", "sold_out"}:
            raise HTTPException(status_code=409, detail="Batch is not available")
        if batch.status == "sold_out" or batch.quantity_available < qty:
            raise HTTPException(status_code=409, detail="Not enough stock")

    if len(store_ids) > 1:
        raise HTTPException(
            status_code=409,
            detail="All cart items must belong to the same store",
        )

    store_id = next(iter(store_ids))
    order_items: list[OrderItem] = []
    total_amount = Decimal("0.00")
    currency = "KZT"
    store_obj: Store | None = None

    for bid, qty in requested_items:
        batch = batch_map[bid]
        store_obj = batch.store
        currency = batch.currency
        line_total = (batch.discount_price * qty).quantize(CENT, rounding=ROUND_HALF_UP)
        total_amount += line_total
        if total_amount > MAX_ORDER_TOTAL:
            raise HTTPException(status_code=422, detail="Order total is too large")
        order_items.append(
            OrderItem(
                batch_id=batch.id,
                batch=batch,
                quantity=qty,
                unit_price=batch.discount_price,
                line_total=line_total,
            )
        )
        batch.quantity_available -= qty
        if batch.quantity_available == 0:
            batch.status = "sold_out"

    order = Order(
        buyer_user_id=buyer.id,
        store_id=store_id,
        store=store_obj,
        idempotency_key=idempotency_key,
        status="reserved",
        fulfillment_method=payload.fulfillment_method,
        delivery_address=payload.delivery_address,
        total_amount=total_amount.quantize(CENT, rounding=ROUND_HALF_UP),
        currency=currency,
        items=order_items,
    )
    db.add(order)
    for bid, _ in requested_items:
        db.add(ActivityEvent(user_id=buyer.id, event_type="booking_created", batch_id=bid))
    db.commit()
    return reservation_response(order)
