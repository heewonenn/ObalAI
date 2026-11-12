
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_timestamp():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_timestamp():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        CheckConstraint("role IN ('buyer', 'seller', 'admin')", name='ck_users_role'),
        Index('uq_users_email_lower', func.lower(text('email')), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='buyer', server_default='buyer')
    created_at: Mapped[datetime] = created_timestamp()
    store: Mapped['Store | None'] = relationship(back_populates='owner', uselist=False)
    favorites: Mapped[list['Favorite']] = relationship(back_populates='user', cascade='all, delete-orphan')
    orders: Mapped[list['Order']] = relationship(back_populates='buyer')


class Store(Base):
    __tablename__ = 'stores'
    __table_args__ = (
        UniqueConstraint('owner_user_id', name='uq_stores_owner_user_id'),
        Index('ix_stores_city_is_active', 'city', 'is_active'),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text('true'))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = updated_timestamp()
    owner: Mapped[User] = relationship(back_populates='store')
    batches: Mapped[list['InventoryBatch']] = relationship(back_populates='store')
    orders: Mapped[list['Order']] = relationship(back_populates='store')


class Category(Base):
    __tablename__ = 'categories'
    __table_args__ = (Index('ix_categories_parent_id', 'parent_id'),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='RESTRICT'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text('true'))
    parent: Mapped['Category | None'] = relationship(remote_side='Category.id', back_populates='children')
    children: Mapped[list['Category']] = relationship(back_populates='parent')
    products: Mapped[list['Product']] = relationship(back_populates='category')


class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (
        CheckConstraint("unit IN ('piece', 'kg', 'portion')", name='ck_products_unit'),
        Index('ix_products_category_id_is_active', 'category_id', 'is_active'),
        Index('ix_products_name', 'name'),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='RESTRICT'))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text('true'))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = updated_timestamp()
    category: Mapped[Category | None] = relationship(back_populates='products')
    batches: Mapped[list['InventoryBatch']] = relationship(back_populates='product')


class InventoryBatch(Base):
    __tablename__ = 'inventory_batches'
    __table_args__ = (
        CheckConstraint('quantity_total > 0', name='ck_batches_quantity_total_positive'),
        CheckConstraint('quantity_available >= 0 AND quantity_available <= quantity_total', name='ck_batches_quantity_available_range'),
        CheckConstraint('regular_price >= 0', name='ck_batches_regular_price_nonnegative'),
        CheckConstraint('discount_price >= 0 AND discount_price <= regular_price', name='ck_batches_discount_price_range'),
        CheckConstraint("currency = 'KZT'", name='ck_batches_currency_kzt'),
        CheckConstraint("status IN ('active', 'paused', 'sold_out', 'expired')", name='ck_batches_status'),
        Index('ix_batches_status_expires_at', 'status', 'expires_at'),
        Index('ix_batches_store_status', 'store_id', 'status'),
        Index('ix_batches_product_status', 'product_id', 'status'),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('products.id', ondelete='RESTRICT'), nullable=False)
    quantity_total: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_available: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    regular_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='KZT', server_default='KZT')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active', server_default='active')
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = updated_timestamp()
    store: Mapped[Store] = relationship(back_populates='batches')
    product: Mapped[Product] = relationship(back_populates='batches')
    favorites: Mapped[list['Favorite']] = relationship(back_populates='batch', cascade='all, delete-orphan')
    order_items: Mapped[list['OrderItem']] = relationship(back_populates='batch')


class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = (Index('ix_favorites_user_created_at', 'user_id', text('created_at DESC')),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('inventory_batches.id', ondelete='CASCADE'), primary_key=True)
    created_at: Mapped[datetime] = created_timestamp()
    user: Mapped[User] = relationship(back_populates='favorites')
    batch: Mapped[InventoryBatch] = relationship(back_populates='favorites')


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        CheckConstraint("status IN ('reserved', 'accepted', 'rejected', 'ready', 'completed', 'cancelled', 'expired')", name='ck_orders_status'),
        CheckConstraint("fulfillment_method IN ('pickup', 'delivery')", name='ck_orders_fulfillment_method'),
        CheckConstraint("(fulfillment_method = 'pickup') OR (delivery_address IS NOT NULL AND length(trim(delivery_address)) > 0)", name='ck_orders_delivery_address'),
        CheckConstraint('total_amount >= 0', name='ck_orders_total_amount_nonnegative'),
        CheckConstraint("currency = 'KZT'", name='ck_orders_currency_kzt'),
        Index('ix_orders_buyer_created_at', 'buyer_user_id', text('created_at DESC')),
        Index('ix_orders_store_status_created_at', 'store_id', 'status', 'created_at'),
        Index('ix_orders_status_reservation_expires_at', 'status', 'reservation_expires_at'),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='reserved', server_default='reserved')
    fulfillment_method: Mapped[str] = mapped_column(String(12), nullable=False)
    delivery_address: Mapped[str | None] = mapped_column(Text)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='KZT', server_default='KZT')
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_timestamp()
    updated_at: Mapped[datetime] = updated_timestamp()
    buyer: Mapped[User] = relationship(back_populates='orders')
    store: Mapped[Store] = relationship(back_populates='orders')
    items: Mapped[list['OrderItem']] = relationship(back_populates='order')


class OrderItem(Base):
    __tablename__ = 'order_items'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_order_items_quantity_positive'),
        CheckConstraint('unit_price >= 0', name='ck_order_items_unit_price_nonnegative'),
        CheckConstraint('line_total >= 0', name='ck_order_items_line_total_nonnegative'),
        Index('ix_order_items_order_id', 'order_id'),
        Index('ix_order_items_batch_id', 'batch_id'),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='RESTRICT'), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('inventory_batches.id', ondelete='RESTRICT'), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = created_timestamp()
    order: Mapped[Order] = relationship(back_populates='items')
    batch: Mapped[InventoryBatch] = relationship(back_populates='order_items')
