"""Create activity_events table for real buyer interactions used by AI recommendations."""

from alembic import op


revision = "0003_activity_events"
down_revision = "0002_order_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE activity_events (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            batch_id UUID,
            query_text VARCHAR(180),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_activity_events_user_id_users FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_activity_events_batch_id_inventory_batches FOREIGN KEY (batch_id)
                REFERENCES inventory_batches(id) ON DELETE SET NULL,
            CONSTRAINT ck_activity_events_type CHECK (
                event_type IN ('view_batch', 'favorite_add', 'favorite_remove', 'booking_created', 'catalog_search')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_activity_events_user_created_at ON activity_events (user_id, created_at DESC)")
    op.execute("CREATE INDEX ix_activity_events_type_created_at ON activity_events (event_type, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE activity_events")
