
"""Create the initial ObalAi PostgreSQL marketplace schema."""

from alembic import op

revision = '0001_initial_marketplace'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            email VARCHAR(320) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'buyer',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_users_role CHECK (role IN ('buyer', 'seller', 'admin'))
        )
    """)
    op.execute('CREATE UNIQUE INDEX ix_users_email ON users (email)')
    op.execute('CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))')

    op.execute("""
        CREATE TABLE stores (
            id UUID PRIMARY KEY,
            owner_user_id UUID NOT NULL,
            name VARCHAR(160) NOT NULL,
            description TEXT,
            address TEXT NOT NULL,
            city VARCHAR(120) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_stores_owner_user_id_users FOREIGN KEY (owner_user_id)
                REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT uq_stores_owner_user_id UNIQUE (owner_user_id)
        )
    """)
    op.execute('CREATE INDEX ix_stores_city_is_active ON stores (city, is_active)')

    op.execute("""
        CREATE TABLE categories (
            id UUID PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            slug VARCHAR(140) NOT NULL UNIQUE,
            parent_id UUID,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT fk_categories_parent_id_categories FOREIGN KEY (parent_id)
                REFERENCES categories(id) ON DELETE RESTRICT
        )
    """)
    op.execute('CREATE INDEX ix_categories_parent_id ON categories (parent_id)')

    op.execute("""
        CREATE TABLE products (
            id UUID PRIMARY KEY,
            category_id UUID,
            name VARCHAR(180) NOT NULL,
            description TEXT,
            unit VARCHAR(20) NOT NULL,
            image_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_products_category_id_categories FOREIGN KEY (category_id)
                REFERENCES categories(id) ON DELETE RESTRICT,
            CONSTRAINT ck_products_unit CHECK (unit IN ('piece', 'kg', 'portion'))
        )
    """)
    op.execute('CREATE INDEX ix_products_category_id_is_active ON products (category_id, is_active)')
    op.execute('CREATE INDEX ix_products_name ON products (name)')

    op.execute("""
        CREATE TABLE inventory_batches (
            id UUID PRIMARY KEY,
            store_id UUID NOT NULL,
            product_id UUID NOT NULL,
            quantity_total NUMERIC(12, 3) NOT NULL,
            quantity_available NUMERIC(12, 3) NOT NULL,
            regular_price NUMERIC(12, 2) NOT NULL,
            discount_price NUMERIC(12, 2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'KZT',
            expires_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_inventory_batches_store_id_stores FOREIGN KEY (store_id)
                REFERENCES stores(id) ON DELETE RESTRICT,
            CONSTRAINT fk_inventory_batches_product_id_products FOREIGN KEY (product_id)
                REFERENCES products(id) ON DELETE RESTRICT,
            CONSTRAINT ck_batches_quantity_total_positive CHECK (quantity_total > 0),
            CONSTRAINT ck_batches_quantity_available_range CHECK (quantity_available >= 0 AND quantity_available <= quantity_total),
            CONSTRAINT ck_batches_regular_price_nonnegative CHECK (regular_price >= 0),
            CONSTRAINT ck_batches_discount_price_range CHECK (discount_price >= 0 AND discount_price <= regular_price),
            CONSTRAINT ck_batches_currency_kzt CHECK (currency = 'KZT'),
            CONSTRAINT ck_batches_status CHECK (status IN ('active', 'paused', 'sold_out', 'expired'))
        )
    """)
    op.execute('CREATE INDEX ix_batches_status_expires_at ON inventory_batches (status, expires_at)')
    op.execute('CREATE INDEX ix_batches_store_status ON inventory_batches (store_id, status)')
    op.execute('CREATE INDEX ix_batches_product_status ON inventory_batches (product_id, status)')

    op.execute("""
        CREATE TABLE favorites (
            user_id UUID NOT NULL,
            batch_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_favorites PRIMARY KEY (user_id, batch_id),
            CONSTRAINT fk_favorites_user_id_users FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_favorites_batch_id_inventory_batches FOREIGN KEY (batch_id)
                REFERENCES inventory_batches(id) ON DELETE CASCADE
        )
    """)
    op.execute('CREATE INDEX ix_favorites_user_created_at ON favorites (user_id, created_at DESC)')

    op.execute("""
        CREATE TABLE orders (
            id UUID PRIMARY KEY,
            buyer_user_id UUID NOT NULL,
            store_id UUID NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'reserved',
            fulfillment_method VARCHAR(12) NOT NULL,
            delivery_address TEXT,
            total_amount NUMERIC(12, 2) NOT NULL,
            currency CHAR(3) NOT NULL DEFAULT 'KZT',
            reservation_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_orders_buyer_user_id_users FOREIGN KEY (buyer_user_id)
                REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT fk_orders_store_id_stores FOREIGN KEY (store_id)
                REFERENCES stores(id) ON DELETE RESTRICT,
            CONSTRAINT ck_orders_status CHECK (status IN ('reserved', 'accepted', 'rejected', 'ready', 'completed', 'cancelled', 'expired')),
            CONSTRAINT ck_orders_fulfillment_method CHECK (fulfillment_method IN ('pickup', 'delivery')),
            CONSTRAINT ck_orders_delivery_address CHECK (fulfillment_method = 'pickup' OR (delivery_address IS NOT NULL AND length(trim(delivery_address)) > 0)),
            CONSTRAINT ck_orders_total_amount_nonnegative CHECK (total_amount >= 0),
            CONSTRAINT ck_orders_currency_kzt CHECK (currency = 'KZT')
        )
    """)
    op.execute('CREATE INDEX ix_orders_buyer_created_at ON orders (buyer_user_id, created_at DESC)')
    op.execute('CREATE INDEX ix_orders_store_status_created_at ON orders (store_id, status, created_at)')
    op.execute('CREATE INDEX ix_orders_status_reservation_expires_at ON orders (status, reservation_expires_at)')

    op.execute("""
        CREATE TABLE order_items (
            id UUID PRIMARY KEY,
            order_id UUID NOT NULL,
            batch_id UUID NOT NULL,
            quantity NUMERIC(12, 3) NOT NULL,
            unit_price NUMERIC(12, 2) NOT NULL,
            line_total NUMERIC(12, 2) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_order_items_order_id_orders FOREIGN KEY (order_id)
                REFERENCES orders(id) ON DELETE RESTRICT,
            CONSTRAINT fk_order_items_batch_id_inventory_batches FOREIGN KEY (batch_id)
                REFERENCES inventory_batches(id) ON DELETE RESTRICT,
            CONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0),
            CONSTRAINT ck_order_items_unit_price_nonnegative CHECK (unit_price >= 0),
            CONSTRAINT ck_order_items_line_total_nonnegative CHECK (line_total >= 0)
        )
    """)
    op.execute('CREATE INDEX ix_order_items_order_id ON order_items (order_id)')
    op.execute('CREATE INDEX ix_order_items_batch_id ON order_items (batch_id)')


def downgrade() -> None:
    op.execute('DROP TABLE order_items')
    op.execute('DROP TABLE orders')
    op.execute('DROP TABLE favorites')
    op.execute('DROP TABLE inventory_batches')
    op.execute('DROP TABLE products')
    op.execute('DROP TABLE categories')
    op.execute('DROP TABLE stores')
    op.execute('DROP TABLE users')
