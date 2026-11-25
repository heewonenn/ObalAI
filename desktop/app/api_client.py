from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx


DEFAULT_API_URL = "http://127.0.0.1:8000"


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
        is_network_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.is_network_error = is_network_error


def translate_api_error(error: Exception) -> str:
    if not isinstance(error, ApiError):
        return "Күтпеген қате орын алды. Қайта көріңіз."
    if error.is_network_error:
        return "Сервермен байланыс үзілді. FastAPI серверінің іске қосылғанын тексеріңіз."

    detail_map = {
        "Invalid email or password": "Email немесе құпиясөз қате.",
        "Email is already registered": "Бұл email тіркелген. Жүйеге кіріңіз.",
        "Seller already has a store": "Бұл аккаунтта дүкен бар.",
        "An active store is required": "Партия жариялау үшін белсенді дүкен қажет.",
        "Buyer role required": "Брондау үшін сатып алушы ретінде кіріңіз.",
        "Seller role required": "Бұл бөлім тек сатушыларға қолжетімді.",
        "Batch not found": "Бұл партия қазір қолжетімсіз.",
        "Batch is not available": "Бұл партия қазір қолжетімсіз.",
        "Not enough stock": "Қалған өнім саны жеткіліксіз.",
        "Order total is too large": "Бронь сомасы тым үлкен. Өнім санын азайтыңыз.",
        "All cart items must belong to the same store": (
            "Бір тапсырысқа тек бір дүкеннің өнімдері кіреді. "
            "Басқа дүкеннен тапсырыс беру үшін себетті тазартыңыз."
        ),
        "Idempotency key already used for a different reservation": (
            "Алдыңғы сұрау басқа броньға тиесілі. Қайта бастаңыз."
        ),
        "Order not found": "Тапсырыс табылмады.",
        "Only reserved orders can be accepted": "Бұл тапсырыс бұрын расталған немесе өңделген.",
        "Only active batches can be paused": "Тек белсенді партияны тоқтатуға болады.",
        "Only paused batches can be activated": "Тек тоқтатылған партияны іске қосуға болады.",
        "Discount price must not exceed regular price": "Жеңілдік бағасы бастапқы бағадан аспауы керек.",
        "Invalid or expired token": "Сеанстың уақыты аяқталды. Қайта кіріңіз.",
        "Bearer token required": "Сеанстың уақыты аяқталды. Қайта кіріңіз.",
    }
    if error.detail in detail_map:
        return detail_map[error.detail]
    if error.status_code == 403:
        return "Бұл әрекетке рұқсатыңыз жоқ."
    if error.status_code == 404:
        return "Сұралған дерек табылмады."
    if error.status_code == 409:
        return "Сұрау ағымдағы күймен сәйкес келмеді. Деректерді жаңартып, қайта көріңіз."
    if error.status_code == 422:
        return "Енгізілген деректерді тексеріңіз."
    if error.status_code == 503:
        return "Дерекқор уақытша қолжетімсіз. Кейінірек қайта көріңіз."
    return "Сұрау орындалмады. Қайта көріңіз."


class ObalApiClient:
    """Thin HTTP client for communicating with the FastAPI backend."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 20.0,
        on_unauthorized: Callable[[], None] | None = None,
    ) -> None:
        raw_url = base_url or os.getenv("OBALAI_API_URL") or DEFAULT_API_URL
        self.base_url = raw_url.rstrip("/")
        self.timeout = timeout
        self.on_unauthorized = on_unauthorized
        self.token: str | None = None
        self.user: dict[str, Any] | None = None
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    def clear_session(self) -> None:
        self.token = None
        self.user = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        authorized: bool = False,
        idempotency_key: str | None = None,
    ) -> Any:
        headers: dict[str, str] = {"Accept": "application/json"}
        request_token = self.token if authorized else None
        if request_token:
            headers["Authorization"] = f"Bearer {request_token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        try:
            response = self._client.request(
                method,
                path,
                json=json_body,
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiError("Network error", is_network_error=True) from exc

        if not response.is_success:
            detail: str | None = None
            try:
                payload = response.json()
                raw_detail = payload.get("detail")
                if isinstance(raw_detail, str):
                    detail = raw_detail
            except ValueError:
                detail = None

            if response.status_code == 401 and request_token and request_token == self.token:
                self.clear_session()
                if self.on_unauthorized is not None:
                    self.on_unauthorized()

            raise ApiError(
                detail or f"HTTP {response.status_code}",
                status_code=response.status_code,
                detail=detail,
            )

        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def register(self, email: str, password: str, role: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/auth/register",
            json_body={"email": email.strip(), "password": password, "role": role},
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/auth/login",
            json_body={"email": email.strip(), "password": password},
        )
        self.token = result["access_token"]
        self.user = result["user"]
        return result

    def me(self) -> dict[str, Any]:
        user = self._request("GET", "/api/auth/me", authorized=True)
        self.user = user
        return user

    def list_catalog(
        self,
        *,
        q: str = "",
        city: str = "",
        unit: str | None = None,
        max_price: str | None = None,
        min_discount: int | None = None,
        sort: str = "expires_asc",
        limit: int = 24,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset, "sort": sort}
        cleaned = q.strip()
        if cleaned:
            params["q"] = cleaned
        cleaned_city = city.strip()
        if cleaned_city:
            params["city"] = cleaned_city
        if unit:
            params["unit"] = unit
        if max_price is not None and str(max_price).strip():
            params["max_price"] = str(max_price).strip()
        if min_discount is not None and min_discount > 0:
            params["min_discount"] = min_discount
        return self._request("GET", "/api/catalog", params=params)

    def get_catalog_batch(self, batch_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/catalog/{batch_id}")

    def list_favorites(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/favorites", authorized=True)

    def add_favorite(self, batch_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/favorites/{batch_id}", authorized=True)

    def remove_favorite(self, batch_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/favorites/{batch_id}", authorized=True)

    def compare_wsm(
        self,
        batch_ids: list[str],
        *,
        weights: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"batch_ids": batch_ids}
        if weights is not None:
            body["weights"] = weights
        return self._request("POST", "/api/compare/wsm", json_body=body)

    def record_batch_view(self, batch_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/ai/events/view/{batch_id}", authorized=True)

    def get_buyer_recommendations(self, *, limit: int = 3) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/ai/recommendations",
            authorized=True,
            params={"limit": limit},
        )

    def create_reservation(
        self,
        *,
        batch_id: str,
        quantity: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/orders",
            authorized=True,
            idempotency_key=idempotency_key,
            json_body={"batch_id": batch_id, "quantity": quantity},
        )

    def create_cart_order(
        self,
        *,
        items: list[dict[str, str]],
        fulfillment_method: str,
        delivery_address: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "items": items,
            "fulfillment_method": fulfillment_method,
            "payment_method": "pay_at_pickup",
        }
        if fulfillment_method == "delivery":
            payload["delivery_address"] = (delivery_address or "").strip()
        return self._request(
            "POST",
            "/api/orders",
            authorized=True,
            idempotency_key=idempotency_key,
            json_body=payload,
        )

    def get_seller_store(self) -> dict[str, Any] | None:
        try:
            return self._request("GET", "/api/seller/store", authorized=True)
        except ApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    def create_seller_store(
        self,
        *,
        name: str,
        city: str,
        address: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name.strip(),
            "city": city.strip(),
            "address": address.strip(),
        }
        if description and description.strip():
            payload["description"] = description.strip()
        return self._request("POST", "/api/seller/store", authorized=True, json_body=payload)

    def publish_batch(
        self,
        *,
        product_name: str,
        unit: str,
        description: str | None,
        quantity: str,
        regular_price: str,
        discount_price: str,
        expires_at_iso: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/seller/batches",
            authorized=True,
            json_body={
                "product": {
                    "name": product_name.strip(),
                    "unit": unit,
                    "description": description.strip() if description and description.strip() else None,
                },
                "quantity": quantity,
                "regular_price": regular_price,
                "discount_price": discount_price,
                "expires_at": expires_at_iso,
            },
        )

    def list_seller_batches(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/seller/batches", authorized=True)

    def update_seller_batch(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        discount_price: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if discount_price is not None:
            payload["discount_price"] = discount_price
        return self._request(
            "PATCH",
            f"/api/seller/batches/{batch_id}",
            authorized=True,
            json_body=payload,
        )

    def list_seller_orders(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/api/seller/orders",
            authorized=True,
            params={"limit": limit, "offset": offset},
        )

    def accept_seller_order(self, order_id: str) -> dict[str, Any]:
        return self._request("PATCH", f"/api/seller/orders/{order_id}/accept", authorized=True)
