from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .dependencies import require_buyer
from .marketplace import StoreSummary
from .models import InventoryBatch, Order, OrderItem, User


router = APIRouter(prefix="/api", tags=["orders"])


class BuyerOrderItemResponse(BaseModel):
    batch_id: UUID
    product_name: str
    unit: Literal["piece", "kg", "portion"]
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class BuyerOrderResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    total_amount: Decimal
    currency: Literal["KZT"]
    store: StoreSummary
    items: list[BuyerOrderItemResponse]


def serialize_buyer_order(order: Order) -> BuyerOrderResponse:
    """Build an API response from the persisted order and its real product data."""
    return BuyerOrderResponse(
        id=order.id,
        status=order.status,
        created_at=order.created_at,
        total_amount=order.total_amount,
        currency=order.currency,
        store=StoreSummary.model_validate(order.store),
        items=[
            BuyerOrderItemResponse(
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


@router.get("/orders", response_model=list[BuyerOrderResponse])
def list_buyer_orders(
    buyer: User = Depends(require_buyer),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[BuyerOrderResponse]:
    orders = db.scalars(
        select(Order)
        .options(
            selectinload(Order.store),
            selectinload(Order.items)
            .selectinload(OrderItem.batch)
            .selectinload(InventoryBatch.product),
        )
        .where(Order.buyer_user_id == buyer.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [serialize_buyer_order(order) for order in orders]
