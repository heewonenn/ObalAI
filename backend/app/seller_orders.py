from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .dependencies import require_seller
from .models import InventoryBatch, Order, OrderItem, Store, User


router = APIRouter(prefix="/api/seller", tags=["seller"])


class SellerOrderItemResponse(BaseModel):
    batch_id: UUID
    product_name: str
    unit: Literal["piece", "kg", "portion"]
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class SellerOrderResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    total_amount: Decimal
    currency: Literal["KZT"]
    items: list[SellerOrderItemResponse]


class SellerOrderStatusResponse(BaseModel):
    id: UUID
    status: Literal["accepted", "rejected", "ready", "completed"]


def serialize_seller_order(order: Order) -> SellerOrderResponse:
    return SellerOrderResponse(
        id=order.id,
        status=order.status,
        created_at=order.created_at,
        total_amount=order.total_amount,
        currency=order.currency,
        items=[
            SellerOrderItemResponse(
                batch_id=item.batch_id,
                product_name=item.batch.product.name,
                unit=item.batch.product.unit,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
            for item in order.items
        ],
    )


def locked_seller_order(order_id: UUID, seller: User, db: Session) -> Order:
    order = db.scalar(
        select(Order)
        .join(Order.store)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Store.owner_user_id == seller.id)
        .with_for_update(of=Order)
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("/orders", response_model=list[SellerOrderResponse])
def list_seller_orders(
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SellerOrderResponse]:
    query = (
        select(Order)
        .join(Order.store)
        .options(
            selectinload(Order.items)
            .selectinload(OrderItem.batch)
            .selectinload(InventoryBatch.product),
        )
        .where(Store.owner_user_id == seller.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [serialize_seller_order(order) for order in db.scalars(query).all()]


@router.patch(
    "/orders/{order_id}/accept",
    response_model=SellerOrderStatusResponse,
)
def accept_seller_order(
    order_id: UUID,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> SellerOrderStatusResponse:
    order = locked_seller_order(order_id, seller, db)
    if order.status != "reserved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only reserved orders can be accepted",
        )

    order.status = "accepted"
    db.commit()
    return SellerOrderStatusResponse(id=order.id, status="accepted")


@router.patch("/orders/{order_id}/reject", response_model=SellerOrderStatusResponse)
def reject_seller_order(
    order_id: UUID,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> SellerOrderStatusResponse:
    order = locked_seller_order(order_id, seller, db)
    if order.status != "reserved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only reserved orders can be rejected",
        )

    items = list(order.items)
    batch_ids = sorted({item.batch_id for item in items}, key=str)
    batches = db.scalars(
        select(InventoryBatch)
        .where(InventoryBatch.id.in_(batch_ids))
        .order_by(InventoryBatch.id)
        .with_for_update(of=InventoryBatch)
    ).all()
    batches_by_id = {batch.id: batch for batch in batches}
    if len(batches_by_id) != len(batch_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order inventory is unavailable")

    for item in items:
        batch = batches_by_id[item.batch_id]
        batch.quantity_available += item.quantity
        if batch.status == "sold_out":
            batch.status = "active" if batch.expires_at > datetime.now(timezone.utc) else "expired"

    order.status = "rejected"
    db.commit()
    return SellerOrderStatusResponse(id=order.id, status="rejected")


@router.patch("/orders/{order_id}/ready", response_model=SellerOrderStatusResponse)
def mark_seller_order_ready(
    order_id: UUID,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> SellerOrderStatusResponse:
    order = locked_seller_order(order_id, seller, db)
    if order.status != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only accepted orders can be marked ready",
        )
    order.status = "ready"
    db.commit()
    return SellerOrderStatusResponse(id=order.id, status="ready")


@router.patch("/orders/{order_id}/complete", response_model=SellerOrderStatusResponse)
def complete_seller_order(
    order_id: UUID,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> SellerOrderStatusResponse:
    order = locked_seller_order(order_id, seller, db)
    if order.status not in {"accepted", "ready"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only accepted or ready orders can be completed",
        )
    order.status = "completed"
    db.commit()
    return SellerOrderStatusResponse(id=order.id, status="completed")
