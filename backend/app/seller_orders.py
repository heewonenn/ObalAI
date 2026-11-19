from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .dependencies import require_seller
from .models import Order, Store, User


router = APIRouter(prefix="/api/seller", tags=["seller"])


class SellerOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: UUID
    quantity: Decimal
    unit_price: Decimal


class SellerOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    created_at: datetime
    total_amount: Decimal
    currency: Literal["KZT"]
    items: list[SellerOrderItemResponse]


class SellerOrderAcceptResponse(BaseModel):
    id: UUID
    status: Literal["accepted"]


@router.get("/orders", response_model=list[SellerOrderResponse])
def list_seller_orders(
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Order]:
    query = (
        select(Order)
        .join(Order.store)
        .options(selectinload(Order.items))
        .where(Store.owner_user_id == seller.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(query).all())


@router.patch(
    "/orders/{order_id}/accept",
    response_model=SellerOrderAcceptResponse,
)
def accept_seller_order(
    order_id: UUID,
    seller: User = Depends(require_seller),
    db: Session = Depends(get_db),
) -> SellerOrderAcceptResponse:
    order = db.scalar(
        select(Order)
        .join(Order.store)
        .where(
            Order.id == order_id,
            Store.owner_user_id == seller.id,
        )
        .with_for_update(of=Order)
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "reserved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only reserved orders can be accepted",
        )

    order.status = "accepted"
    db.commit()
    return SellerOrderAcceptResponse(id=order.id, status="accepted")
