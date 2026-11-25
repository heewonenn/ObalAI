"""Record seller discount-price changes for inventory batches."""

from alembic import op


revision = "0004_price_history"
down_revision = "0003_activity_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE price_history (
            id UUID PRIMARY KEY,
            batch_id UUID NOT NULL,
            old_discount_price NUMERIC(12, 2) NOT NULL,
            new_discount_price NUMERIC(12, 2) NOT NULL,
            changed_by_user_id UUID NOT NULL,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_price_history_batch_id_inventory_batches FOREIGN KEY (batch_id)
                REFERENCES inventory_batches(id) ON DELETE RESTRICT,
            CONSTRAINT fk_price_history_changed_by_user_id_users FOREIGN KEY (changed_by_user_id)
                REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT ck_price_history_old_discount_price_nonnegative CHECK (old_discount_price >= 0),
            CONSTRAINT ck_price_history_new_discount_price_nonnegative CHECK (new_discount_price >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_price_history_batch_changed_at ON price_history (batch_id, changed_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE price_history")
