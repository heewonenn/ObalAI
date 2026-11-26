from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.database import engine
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as tc:
        yield tc


@pytest.fixture()
def marketplace_fixture(client: TestClient):
    """Create disposable seller, store, 3 batches, and buyer in real PostgreSQL; clean up after."""
    suffix = uuid.uuid4().hex[:8]
    seller_email = f"pytest_seller_{suffix}@example.com"
    buyer_email = f"pytest_buyer_{suffix}@example.com"
    password = "PytestPassword123!"
    prefix = f"PyTest_{suffix}_"

    r = client.post("/api/auth/register", json={"email": seller_email, "password": password, "role": "seller"})
    assert r.status_code == 201
    seller_token = client.post("/api/auth/login", json={"email": seller_email, "password": password}).json()["access_token"]
    seller_headers = {"Authorization": f"Bearer {seller_token}"}

    st = client.post(
        "/api/seller/store",
        headers=seller_headers,
        json={"name": f"{prefix}Store", "city": f"City_{suffix}", "address": "Abay 1"},
    )
    assert st.status_code == 201

    now = datetime.now(timezone.utc)
    specs = [
        (f"{prefix}Сүзбе балғын 5%", "piece", "Сүт өнімі, табиғи сүзбе", "5", "1000.00", "600.00", now + timedelta(hours=36)),
        (f"{prefix}Қаймақ сүт 20%", "piece", "Табиғи сүт қаймақ", "4", "1200.00", "700.00", now + timedelta(hours=48)),
        (f"{prefix}Круассан порция", "portion", "Дәмхана пісірмесі", "3", "2000.00", "1500.00", now + timedelta(hours=18)),
    ]
    batches = []
    for name, unit, desc, qty, reg, disc, exp in specs:
        resp = client.post(
            "/api/seller/batches",
            headers=seller_headers,
            json={
                "product": {"name": name, "unit": unit, "description": desc},
                "quantity": qty,
                "regular_price": reg,
                "discount_price": disc,
                "expires_at": exp.isoformat(),
            },
        )
        assert resp.status_code == 201
        batches.append(resp.json())

    rb = client.post("/api/auth/register", json={"email": buyer_email, "password": password, "role": "buyer"})
    assert rb.status_code == 201
    buyer_token = client.post("/api/auth/login", json={"email": buyer_email, "password": password}).json()["access_token"]
    buyer_headers = {"Authorization": f"Bearer {buyer_token}"}

    try:
        yield {
            "suffix": suffix,
            "prefix": prefix,
            "city": f"City_{suffix}",
            "seller_headers": seller_headers,
            "buyer_headers": buyer_headers,
            "batches": batches,
        }
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM activity_events WHERE user_id IN (SELECT id FROM users WHERE email IN (:s, :b))"),
                {"s": seller_email, "b": buyer_email},
            )
            conn.execute(
                text("DELETE FROM favorites WHERE user_id IN (SELECT id FROM users WHERE email IN (:s, :b))"),
                {"s": seller_email, "b": buyer_email},
            )
            conn.execute(
                text(
                    "DELETE FROM order_items WHERE order_id IN ("
                    "SELECT o.id FROM orders o JOIN users u ON u.id = o.buyer_user_id WHERE u.email = :b)"
                ),
                {"b": buyer_email},
            )
            conn.execute(
                text(
                    "DELETE FROM price_history WHERE batch_id IN ("
                    "SELECT ib.id FROM inventory_batches ib JOIN stores s ON s.id = ib.store_id "
                    "JOIN users u ON u.id = s.owner_user_id WHERE u.email = :s)"
                ),
                {"s": seller_email},
            )
            conn.execute(
                text("DELETE FROM orders WHERE buyer_user_id IN (SELECT id FROM users WHERE email = :b)"),
                {"b": buyer_email},
            )
            conn.execute(
                text(
                    "DELETE FROM inventory_batches WHERE store_id IN ("
                    "SELECT s.id FROM stores s JOIN users u ON u.id = s.owner_user_id WHERE u.email = :s)"
                ),
                {"s": seller_email},
            )
            conn.execute(text("DELETE FROM products WHERE name LIKE :pfx"), {"pfx": f"{prefix}%"})
            conn.execute(
                text("DELETE FROM stores WHERE owner_user_id IN (SELECT id FROM users WHERE email = :s)"),
                {"s": seller_email},
            )
            conn.execute(text("DELETE FROM users WHERE email IN (:s, :b)"), {"s": seller_email, "b": buyer_email})


def test_health_postgresql_connected(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "connected"}


def test_catalog_filters_sorting_and_detail(client: TestClient, marketplace_fixture):
    city = marketplace_fixture["city"]

    asc = client.get("/api/catalog", params={"city": city, "sort": "price_asc"}).json()
    assert len(asc) == 3
    assert [Decimal(b["discount_price"]) for b in asc] == [Decimal("600.00"), Decimal("700.00"), Decimal("1500.00")]

    desc = client.get("/api/catalog", params={"city": city, "sort": "price_desc"}).json()
    assert [Decimal(b["discount_price"]) for b in desc] == [Decimal("1500.00"), Decimal("700.00"), Decimal("600.00")]

    disc_sort = client.get("/api/catalog", params={"city": city, "sort": "discount_desc"}).json()
    assert disc_sort[0]["product"]["name"].endswith("Қаймақ сүт 20%")  # 41.67% > 40% > 25%

    only_portions = client.get("/api/catalog", params={"city": city, "unit": "portion"}).json()
    assert len(only_portions) == 1
    assert only_portions[0]["product"]["unit"] == "portion"

    max_p = client.get("/api/catalog", params={"city": city, "max_price": "700"}).json()
    assert len(max_p) == 2

    batch_id = asc[0]["batch_id"]
    detail = client.get(f"/api/catalog/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["batch_id"] == batch_id


def test_booking_atomic_idempotent_and_guards(client: TestClient, marketplace_fixture):
    batch = marketplace_fixture["batches"][0]
    batch_id = batch["batch_id"]
    buyer_headers = marketplace_fixture["buyer_headers"]
    seller_headers = marketplace_fixture["seller_headers"]

    # Seller cannot book
    forbidden = client.post(
        "/api/orders",
        headers={**seller_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": batch_id, "quantity": "1"},
    )
    assert forbidden.status_code == 403

    # Idempotent booking deduplicates retries
    idem = str(uuid.uuid4())
    r1 = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": idem},
        json={"batch_id": batch_id, "quantity": "2"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": idem},
        json={"batch_id": batch_id, "quantity": "2"},
    )
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    # Stock dropped once: 5 -> 3
    after = client.get(f"/api/catalog/{batch_id}").json()
    assert Decimal(after["quantity_available"]) == Decimal("3.000")

    # Insufficient stock -> 409
    too_many = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": batch_id, "quantity": "10"},
    )
    assert too_many.status_code == 409


def test_favorites_and_wsm_comparison(client: TestClient, marketplace_fixture):
    batches = marketplace_fixture["batches"]
    ids = [b["batch_id"] for b in batches]
    buyer_headers = marketplace_fixture["buyer_headers"]
    seller_headers = marketplace_fixture["seller_headers"]

    # Seller blocked from favorites
    assert client.get("/api/favorites", headers=seller_headers).status_code == 403

    # Buyer adds & lists & removes favorite
    assert client.post(f"/api/favorites/{ids[0]}", headers=buyer_headers).status_code == 201
    favs = client.get("/api/favorites", headers=buyer_headers).json()
    assert len(favs) == 1 and favs[0]["batch"]["batch_id"] == ids[0]
    assert client.delete(f"/api/favorites/{ids[0]}", headers=buyer_headers).status_code == 200
    assert client.get("/api/favorites", headers=buyer_headers).json() == []

    # WSM insufficient_data with 1 batch
    insuff = client.post("/api/compare/wsm", json={"batch_ids": [ids[0]]}).json()
    assert insuff["status"] == "insufficient_data"
    assert insuff["excluded_criteria"] == ["distance"]

    # WSM with 3 batches
    wsm = client.post("/api/compare/wsm", json={"batch_ids": ids}).json()
    assert wsm["status"] == "ok"
    assert wsm["method"] == "WSM"
    assert wsm["excluded_criteria"] == ["distance"]
    assert [item["rank"] for item in wsm["items"]] == [1, 2, 3]
    weights = wsm["weights_used"]
    for item in wsm["items"]:
        n = item["normalized"]
        expected = round(weights["discount"] * n["discount"] + weights["freshness"] * n["freshness"] + weights["price"] * n["price"], 4)
        assert abs(item["score"] - expected) < 0.001


def test_buyer_ai_recommendations_insufficient_then_ok(client: TestClient, marketplace_fixture):
    batches = marketplace_fixture["batches"]
    dairy_1 = batches[0]["batch_id"]  # Сүзбе
    dairy_2 = batches[1]["batch_id"]  # Қаймақ
    buyer_headers = marketplace_fixture["buyer_headers"]
    seller_headers = marketplace_fixture["seller_headers"]

    # Seller cannot call buyer recommendations
    assert client.get("/api/ai/recommendations", headers=seller_headers).status_code == 403

    # 0 interactions -> honest insufficient_data
    r0 = client.get("/api/ai/recommendations", headers=buyer_headers).json()
    assert r0["status"] == "insufficient_data"
    assert r0["current_interactions"] == 0
    assert r0["required_interactions"] == 3
    assert r0["items"] == []

    # 2 real interactions -> still insufficient_data
    assert client.post(f"/api/ai/events/view/{dairy_1}", headers=buyer_headers).status_code == 201
    assert client.post(f"/api/favorites/{dairy_1}", headers=buyer_headers).status_code == 201
    r2 = client.get("/api/ai/recommendations", headers=buyer_headers).json()
    assert r2["status"] == "insufficient_data"
    assert r2["current_interactions"] == 2

    # 3rd real interaction (booking) -> AI recommendations activate!
    b_res = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": dairy_1, "quantity": "1"},
    )
    assert b_res.status_code == 201

    r3 = client.get("/api/ai/recommendations", headers=buyer_headers).json()
    assert r3["status"] == "ok"
    assert r3["model_version"] == "buyer-content-pref-v1"
    assert r3["current_interactions"] >= 3
    assert len(r3["items"]) >= 2
    rec_ids = [item["batch"]["batch_id"] for item in r3["items"]]
    assert dairy_1 in rec_ids and dairy_2 in rec_ids
    for item in r3["items"]:
        assert 0.0 <= item["score"] <= 1.0
        assert isinstance(item["explanation"], str) and len(item["explanation"]) > 5


def test_cart_checkout_multi_item_and_delivery(client: TestClient, marketplace_fixture):
    batches = marketplace_fixture["batches"]
    buyer_headers = marketplace_fixture["buyer_headers"]

    # Delivery without address must fail with 422
    bad_delivery = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "items": [{"batch_id": batches[0]["batch_id"], "quantity": "1"}],
            "fulfillment_method": "delivery",
            "delivery_address": "   ",
        },
    )
    assert bad_delivery.status_code == 422

    # Multi-item cart order with pickup returns pickup_code, store address, and savings
    idem = str(uuid.uuid4())
    res = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": idem},
        json={
            "items": [
                {"batch_id": batches[0]["batch_id"], "quantity": "1"},
                {"batch_id": batches[1]["batch_id"], "quantity": "2"},
            ],
            "fulfillment_method": "pickup",
            "payment_method": "pay_at_pickup",
        },
    )
    assert res.status_code == 201
    order = res.json()
    assert order["pickup_code"].startswith("OB-")
    assert order["fulfillment_method"] == "pickup"
    assert order["delivery_address"] is None
    assert order["store"]["address"] == "Abay 1"
    assert len(order["items"]) == 2
    assert Decimal(order["total_amount"]) == Decimal("2000.00")  # 600 + 2*700
    assert Decimal(order["original_total"]) == Decimal("3400.00")  # 1000 + 2*1200
    assert Decimal(order["savings_amount"]) == Decimal("1400.00")

    # Idempotent retry returns 200 with identical order
    retry = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": idem},
        json={
            "items": [
                {"batch_id": batches[0]["batch_id"], "quantity": "1"},
                {"batch_id": batches[1]["batch_id"], "quantity": "2"},
            ],
            "fulfillment_method": "pickup",
            "payment_method": "pay_at_pickup",
        },
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == order["id"]

    # Delivery with valid address succeeds
    deliv = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "items": [{"batch_id": batches[2]["batch_id"], "quantity": "1"}],
            "fulfillment_method": "delivery",
            "delivery_address": "Алматы, Абай 15, кв 24",
            "payment_method": "pay_at_pickup",
        },
    )
    assert deliv.status_code == 201
    assert deliv.json()["fulfillment_method"] == "delivery"
    assert deliv.json()["delivery_address"] == "Алматы, Абай 15, кв 24"


def test_buyer_order_history_and_seller_status_transitions(client: TestClient, marketplace_fixture):
    """Orders remain buyer-scoped while seller transitions use real PostgreSQL rows."""
    batches = marketplace_fixture["batches"]
    buyer_headers = marketplace_fixture["buyer_headers"]
    seller_headers = marketplace_fixture["seller_headers"]

    # A seller cannot access the buyer-only history endpoint.
    assert client.get("/api/orders", headers=seller_headers).status_code == 403

    # Reserving the complete batch makes it sold out; rejection must restore it atomically.
    rejected_order = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": batches[0]["batch_id"], "quantity": "5"},
    )
    assert rejected_order.status_code == 201
    rejected_id = rejected_order.json()["id"]

    history = client.get("/api/orders", headers=buyer_headers, params={"limit": 1, "offset": 0})
    assert history.status_code == 200
    assert len(history.json()) == 1
    item = history.json()[0]["items"][0]
    assert item["product_name"].endswith("Сүзбе балғын 5%")
    assert item["unit"] == "piece"
    assert Decimal(item["quantity"]) == Decimal("5.000")
    assert Decimal(item["unit_price"]) == Decimal("600.00")
    assert Decimal(item["line_total"]) == Decimal("3000.00")
    assert history.json()[0]["store"]["name"].startswith(marketplace_fixture["prefix"])

    seller_orders = client.get("/api/seller/orders", headers=seller_headers)
    assert seller_orders.status_code == 200
    seller_item = next(order for order in seller_orders.json() if order["id"] == rejected_id)["items"][0]
    assert seller_item["product_name"] == item["product_name"]
    assert seller_item["unit"] == item["unit"]

    rejected = client.patch(f"/api/seller/orders/{rejected_id}/reject", headers=seller_headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.patch(f"/api/seller/orders/{rejected_id}/reject", headers=seller_headers).status_code == 409

    restored_batch = client.get(f"/api/catalog/{batches[0]['batch_id']}")
    assert restored_batch.status_code == 200
    assert Decimal(restored_batch.json()["quantity_available"]) == Decimal("5.000")
    buyer_history = client.get("/api/orders", headers=buyer_headers).json()
    assert next(order for order in buyer_history if order["id"] == rejected_id)["status"] == "rejected"

    # Accepted -> ready -> completed is allowed, but repeating a terminal transition is not.
    ready_order = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": batches[1]["batch_id"], "quantity": "1"},
    )
    assert ready_order.status_code == 201
    ready_id = ready_order.json()["id"]
    assert client.patch(f"/api/seller/orders/{ready_id}/accept", headers=seller_headers).json()["status"] == "accepted"
    assert client.patch(f"/api/seller/orders/{ready_id}/ready", headers=seller_headers).json()["status"] == "ready"
    assert client.patch(f"/api/seller/orders/{ready_id}/complete", headers=seller_headers).json()["status"] == "completed"
    assert client.patch(f"/api/seller/orders/{ready_id}/complete", headers=seller_headers).status_code == 409

    # Completing an accepted order directly is also a documented valid transition.
    accepted_order = client.post(
        "/api/orders",
        headers={**buyer_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"batch_id": batches[2]["batch_id"], "quantity": "1"},
    )
    assert accepted_order.status_code == 201
    accepted_id = accepted_order.json()["id"]
    assert client.patch(f"/api/seller/orders/{accepted_id}/accept", headers=seller_headers).status_code == 200
    assert client.patch(f"/api/seller/orders/{accepted_id}/complete", headers=seller_headers).json()["status"] == "completed"

    # Pagination returns separate pages of this buyer's history.
    first_page = client.get("/api/orders", headers=buyer_headers, params={"limit": 1, "offset": 0}).json()
    second_page = client.get("/api/orders", headers=buyer_headers, params={"limit": 1, "offset": 1}).json()
    assert first_page and second_page and first_page[0]["id"] != second_page[0]["id"]


def test_seller_batch_management_and_price_history(client: TestClient, marketplace_fixture):
    seller_headers = marketplace_fixture["seller_headers"]
    buyer_headers = marketplace_fixture["buyer_headers"]
    batch = marketplace_fixture["batches"][0]
    batch_id = batch["batch_id"]

    # Listing is seller-only and includes every own batch with its product data.
    assert client.get("/api/seller/batches", headers=buyer_headers).status_code == 403
    listed = client.get("/api/seller/batches", headers=seller_headers)
    assert listed.status_code == 200
    mine = next(item for item in listed.json() if item["batch_id"] == batch_id)
    assert mine["product"]["name"].endswith("Сүзбе балғын 5%")
    assert mine["product"]["unit"] == "piece"
    assert mine["status"] == "active"

    paused = client.patch(f"/api/seller/batches/{batch_id}", headers=seller_headers, json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert client.patch(
        f"/api/seller/batches/{batch_id}", headers=seller_headers, json={"status": "paused"}
    ).status_code == 409
    resumed = client.patch(f"/api/seller/batches/{batch_id}", headers=seller_headers, json={"status": "active"})
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    price_change = client.patch(
        f"/api/seller/batches/{batch_id}",
        headers=seller_headers,
        json={"discount_price": "500.00"},
    )
    assert price_change.status_code == 200
    assert Decimal(price_change.json()["discount_price"]) == Decimal("500.00")
    with engine.connect() as conn:
        history = conn.execute(
            text(
                "SELECT old_discount_price, new_discount_price, changed_by_user_id "
                "FROM price_history WHERE batch_id = :batch_id"
            ),
            {"batch_id": batch_id},
        ).mappings().all()
    assert len(history) == 1
    assert Decimal(history[0]["old_discount_price"]) == Decimal("600.00")
    assert Decimal(history[0]["new_discount_price"]) == Decimal("500.00")
    assert history[0]["changed_by_user_id"]

    # Sending the same price does not manufacture a price-history observation.
    same_price = client.patch(
        f"/api/seller/batches/{batch_id}",
        headers=seller_headers,
        json={"discount_price": "500.00"},
    )
    assert same_price.status_code == 200
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM price_history WHERE batch_id = :batch_id"), {"batch_id": batch_id}
        ).scalar_one()
    assert count == 1

    # A failed combined update rolls back the status change as well as the bad price.
    invalid = client.patch(
        f"/api/seller/batches/{batch_id}",
        headers=seller_headers,
        json={"status": "paused", "discount_price": "1001.00"},
    )
    assert invalid.status_code == 422
    current = next(
        item for item in client.get("/api/seller/batches", headers=seller_headers).json() if item["batch_id"] == batch_id
    )
    assert current["status"] == "active"
    assert Decimal(current["discount_price"]) == Decimal("500.00")


def test_seller_batch_endpoints_hide_foreign_store_batches(client: TestClient, marketplace_fixture):
    """A seller cannot discover or mutate batches belonging to a different store."""
    suffix = uuid.uuid4().hex[:8]
    email = f"pytest_other_seller_{suffix}@example.com"
    password = "PytestPassword123!"
    prefix = f"PyTestForeign_{suffix}_"
    original_seller_headers = marketplace_fixture["seller_headers"]

    registered = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "role": "seller"},
    )
    assert registered.status_code == 201
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    foreign_headers = {"Authorization": f"Bearer {token}"}
    store = client.post(
        "/api/seller/store",
        headers=foreign_headers,
        json={"name": f"{prefix}Store", "city": "OtherCity", "address": "Other 1"},
    )
    assert store.status_code == 201
    foreign_batch = client.post(
        "/api/seller/batches",
        headers=foreign_headers,
        json={
            "product": {"name": f"{prefix}Өнім", "unit": "piece"},
            "quantity": "2",
            "regular_price": "900.00",
            "discount_price": "500.00",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        },
    )
    assert foreign_batch.status_code == 201
    foreign_batch_id = foreign_batch.json()["batch_id"]

    try:
        visible_ids = {item["batch_id"] for item in client.get("/api/seller/batches", headers=original_seller_headers).json()}
        assert foreign_batch_id not in visible_ids
        assert client.patch(
            f"/api/seller/batches/{foreign_batch_id}",
            headers=original_seller_headers,
            json={"status": "paused"},
        ).status_code == 404
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM price_history WHERE batch_id IN ("
                    "SELECT ib.id FROM inventory_batches ib JOIN stores s ON s.id = ib.store_id "
                    "JOIN users u ON u.id = s.owner_user_id WHERE u.email = :email)"
                ),
                {"email": email},
            )
            conn.execute(
                text(
                    "DELETE FROM inventory_batches WHERE store_id IN ("
                    "SELECT s.id FROM stores s JOIN users u ON u.id = s.owner_user_id WHERE u.email = :email)"
                ),
                {"email": email},
            )
            conn.execute(text("DELETE FROM products WHERE name LIKE :prefix"), {"prefix": f"{prefix}%"})
            conn.execute(
                text("DELETE FROM stores WHERE owner_user_id IN (SELECT id FROM users WHERE email = :email)"),
                {"email": email},
            )
            conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
