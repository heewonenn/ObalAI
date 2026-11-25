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
