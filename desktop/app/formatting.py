from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ROLES: dict[str, str] = {
    "buyer": "Сатып алушы",
    "seller": "Сатушы",
    "admin": "Әкімші",
}

UNITS: dict[str, str] = {
    "piece": "дана",
    "kg": "кг",
    "portion": "порция",
}

UNIT_LABELS: list[tuple[str, str]] = [
    ("piece", "Дана"),
    ("kg", "Килограмм"),
    ("portion", "Порция"),
]

ORDER_STATUSES: dict[str, str] = {
    "reserved": "Брондалған",
    "accepted": "Расталған",
    "rejected": "Қабылданбаған",
    "ready": "Дайын",
    "completed": "Аяқталған",
    "cancelled": "Бас тартылған",
    "expired": "Мерзімі өткен",
}

BATCH_STATUSES: dict[str, str] = {
    "active": "Белсенді",
    "paused": "Тоқтатылған",
    "sold_out": "Сатылып кетті",
    "expired": "Мерзімі өткен",
}


def to_decimal(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def format_money(value: Decimal | str | int | float, currency: str = "KZT") -> str:
    amount = to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == amount.to_integral_value():
        formatted = f"{int(amount):,}".replace(",", " ")
    else:
        formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    symbol = "₸" if currency == "KZT" else currency
    return f"{formatted} {symbol}"


def format_quantity(value: Decimal | str | int | float) -> str:
    qty = to_decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    normalized = format(qty.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized.replace(".", ",")


def format_decimal_api(value: Decimal | str | int | float, places: int = 3) -> str:
    quant = Decimal("1").scaleb(-places)
    dec = to_decimal(value).quantize(quant, rounding=ROUND_HALF_UP)
    text = format(dec.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_datetime(iso_value: str) -> str:
    try:
        parsed = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        local_dt = parsed.astimezone()
        return local_dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_value


def discount_percent(regular: Decimal | str | int | float, discount: Decimal | str | int | float) -> int:
    reg = to_decimal(regular)
    disc = to_decimal(discount)
    if reg <= 0 or disc >= reg:
        return 0
    pct = ((reg - disc) / reg * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, int(pct))


def role_label(role: str | None) -> str:
    if not role:
        return ""
    return ROLES.get(role, role)


def unit_label(unit: str) -> str:
    return UNITS.get(unit, unit)


def order_status_label(status: str) -> str:
    return ORDER_STATUSES.get(status, status)


def batch_status_label(status: str) -> str:
    return BATCH_STATUSES.get(status, status)
