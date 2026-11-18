"""Store the request key of a buyer's reservation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0002_order_idempotency"
down_revision = "0001_initial_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("idempotency_key", UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint(
        "uq_orders_buyer_idempotency_key", "orders", ["buyer_user_id", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_buyer_idempotency_key", "orders", type_="unique")
    op.drop_column("orders", "idempotency_key")
