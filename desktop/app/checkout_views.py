from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .formatting import (
    discount_percent,
    format_datetime,
    format_decimal_api,
    format_money,
    format_quantity,
    order_status_label,
    to_decimal,
    unit_label,
)
from .widgets import FeedbackBanner, FormSymbol, SiteFooter, repolish


@dataclass
class CartItem:
    batch_id: str
    store_id: str
    store_name: str
    store_city: str
    store_address: str
    name: str
    unit: str
    regular_price: Decimal
    discount_price: Decimal
    available: Decimal
    quantity: Decimal
    expires_at: str
    currency: str = "KZT"


def cart_item_from_batch(batch: dict[str, Any], quantity: Decimal | None = None) -> CartItem:
    avail = to_decimal(batch["quantity_available"])
    default_qty = avail if avail < Decimal("1") else Decimal("1")
    qty = quantity if (quantity is not None and quantity > 0) else default_qty
    if avail > 0 and qty > avail:
        qty = avail
    return CartItem(
        batch_id=str(batch["batch_id"]),
        store_id=str(batch["store_id"]),
        store_name=batch["store"]["name"],
        store_city=batch["store"]["city"],
        store_address=batch["store"]["address"],
        name=batch["product"]["name"],
        unit=batch["product"]["unit"],
        regular_price=to_decimal(batch["regular_price"]),
        discount_price=to_decimal(batch["discount_price"]),
        available=avail,
        quantity=qty,
        expires_at=batch["expires_at"],
        currency=batch.get("currency", "KZT"),
    )


class PickupCodeWidget(QWidget):
    """Deterministic visual pickup matrix rendered natively in PySide6."""

    def __init__(self, code: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._code = code
        self.setFixedSize(148, 148)

    def set_code(self, code: str) -> None:
        self._code = code
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QColor("#d9dacb"))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        grid = 13
        margin = 14
        cell = (self.width() - margin * 2) // grid
        digest = hashlib.sha256(self._code.encode("utf-8")).digest()
        bits = "".join(f"{byte:08b}" for byte in digest)

        def is_finder(r: int, c: int) -> bool:
            for fr, fc in ((0, 0), (0, grid - 4), (grid - 4, 0)):
                if fr <= r < fr + 4 and fc <= c < fc + 4:
                    return True
            return False

        dark = QColor("#244a31")
        idx = 0
        for r in range(grid):
            for c in range(grid):
                x = margin + c * cell
                y = margin + r * cell
                if is_finder(r, c):
                    lr = r if r < 4 else r - (grid - 4)
                    lc = c if c < 4 else c - (grid - 4)
                    border = lr in (0, 3) or lc in (0, 3)
                    center = lr in (1, 2) and lc in (1, 2)
                    if border or center:
                        painter.fillRect(x, y, cell, cell, dark)
                else:
                    if bits[idx % len(bits)] == "1":
                        painter.fillRect(x, y, cell, cell, dark)
                    idx += 1
        painter.end()


def build_stepper(active_step: int) -> QWidget:
    """Visual 3-step checkout progress indicator: 1. Себет → 2. Рәсімдеу → 3. Растау."""
    bar = QWidget()
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    steps = [(1, "1. Себет"), (2, "2. Рәсімдеу"), (3, "3. Растау")]
    for idx, (num, title) in enumerate(steps):
        chip = QLabel(title)
        chip.setObjectName("stepperChip")
        chip.setProperty("active", "true" if num == active_step else "false")
        chip.setProperty("done", "true" if num < active_step else "false")
        repolish(chip)
        layout.addWidget(chip)
        if idx < len(steps) - 1:
            arrow = QLabel("→")
            arrow.setObjectName("mutedText")
            layout.addWidget(arrow)
    layout.addStretch(1)
    return bar


class ProductDetailView(QWidget):
    """Full-page product detail screen matching the Figma flow (Catalog → Detail → Cart)."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_back: Callable[[], None],
        on_add_to_cart: Callable[[dict[str, Any], Decimal, bool], None],
        on_switch_to_buyer: Callable[[dict[str, Any]], None],
        on_toggle_favorite: Callable[[str], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_back = on_back
        self.on_add_to_cart = on_add_to_cart
        self.on_switch_to_buyer = on_switch_to_buyer
        self.on_toggle_favorite = on_toggle_favorite

        self.batch: dict[str, Any] | None = None
        self.is_favorite = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        page = QWidget()
        wrap = QHBoxLayout(page)
        wrap.setContentsMargins(32, 24, 32, 24)
        wrap.setAlignment(Qt.AlignmentFlag.AlignTop)

        inner = QWidget()
        inner.setMaximumWidth(1160)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        back_btn = QPushButton("← Каталогқа оралу")
        back_btn.setProperty("variant", "link")
        back_btn.clicked.connect(self.on_back)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.feedback = FeedbackBanner()
        root.addWidget(self.feedback)

        cols = QHBoxLayout()
        cols.setSpacing(22)

        # Left column: product visual header + description + good to know
        left_card = QFrame()
        left_card.setObjectName("surfaceCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(24, 22, 24, 22)
        left_layout.setSpacing(14)

        badge_row = QHBoxLayout()
        self.unit_badge = QLabel()
        self.unit_badge.setObjectName("unitBadge")
        self.discount_badge = QLabel()
        self.discount_badge.setObjectName("discountBadge")
        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName("favButton")
        self.fav_btn.clicked.connect(self._toggle_fav)
        badge_row.addWidget(self.unit_badge)
        badge_row.addWidget(self.discount_badge)
        badge_row.addStretch(1)
        badge_row.addWidget(self.fav_btn)
        left_layout.addLayout(badge_row)

        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        left_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        left_layout.addWidget(self.desc_label)

        good_box = QFrame()
        good_box.setObjectName("storeSummary")
        good_layout = QVBoxLayout(good_box)
        good_layout.setContentsMargins(16, 14, 16, 14)
        good_layout.setSpacing(6)
        good_title = QLabel("Маңызды ақпарат")
        good_title.setObjectName("unitBadge")
        self.expiry_info = QLabel()
        self.stock_info = QLabel()
        self.policy_info = QLabel(
            "• Брондалған өнім дүкенде алып кету немесе жеткізу арқылы беріледі.\n"
            "• Төлем тапсырысты алған кезде жасалады."
        )
        self.policy_info.setObjectName("mutedText")
        self.policy_info.setWordWrap(True)
        good_layout.addWidget(good_title)
        good_layout.addWidget(self.expiry_info)
        good_layout.addWidget(self.stock_info)
        good_layout.addWidget(self.policy_info)
        left_layout.addWidget(good_box)
        left_layout.addStretch(1)

        # Right column: price, pickup address, quantity, add to cart / instant checkout
        right_card = QFrame()
        right_card.setObjectName("surfaceCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(24, 22, 24, 22)
        right_layout.setSpacing(14)

        price_row = QHBoxLayout()
        price_row.setSpacing(10)
        self.price_label = QLabel()
        self.price_label.setObjectName("priceLabel")
        self.old_price_label = QLabel()
        self.old_price_label.setObjectName("oldPriceLabel")
        price_row.addWidget(self.price_label)
        price_row.addWidget(self.old_price_label)
        price_row.addStretch(1)
        right_layout.addLayout(price_row)

        self.savings_label = QLabel()
        self.savings_label.setObjectName("savingsText")
        right_layout.addWidget(self.savings_label)

        addr_box = QFrame()
        addr_box.setObjectName("storeSummary")
        addr_layout = QVBoxLayout(addr_box)
        addr_layout.setContentsMargins(16, 14, 16, 14)
        addr_layout.setSpacing(5)
        addr_head = QHBoxLayout()
        addr_head.addWidget(FormSymbol("⌂"))
        addr_col = QVBoxLayout()
        addr_col.setSpacing(2)
        addr_kicker = QLabel("АЛЫП КЕТУ МЕКЕНЖАЙЫ")
        addr_kicker.setObjectName("stepLabel")
        self.store_name_label = QLabel()
        self.store_name_label.setObjectName("productTitle")
        self.store_name_label.setWordWrap(True)
        self.store_address_label = QLabel()
        self.store_address_label.setObjectName("mutedText")
        self.store_address_label.setWordWrap(True)
        addr_col.addWidget(addr_kicker)
        addr_col.addWidget(self.store_name_label)
        addr_col.addWidget(self.store_address_label)
        addr_head.addLayout(addr_col, stretch=1)
        addr_layout.addLayout(addr_head)

        delivery_note = QLabel("Алып кету: Тегін · Жеткізу мекенжайын себетте таңдауға болады")
        delivery_note.setObjectName("mutedText")
        delivery_note.setWordWrap(True)
        addr_layout.addWidget(delivery_note)
        right_layout.addWidget(addr_box)

        self.qty_label = QLabel("Саны")
        right_layout.addWidget(self.qty_label)

        self.qty_input = QDoubleSpinBox()
        self.qty_input.setDecimals(3)
        self.qty_input.setMinimum(0.001)
        self.qty_input.setMaximum(999_999_999.999)
        right_layout.addWidget(self.qty_input)

        self.seller_hint = QLabel("Брондау тек сатып алушыларға қолжетімді.")
        self.seller_hint.setObjectName("sellerBookingHint")
        self.seller_hint.setWordWrap(True)
        right_layout.addWidget(self.seller_hint)

        self.switch_buyer_btn = QPushButton("Сатып алушы ретінде кіру")
        self.switch_buyer_btn.clicked.connect(self._handle_switch)
        right_layout.addWidget(self.switch_buyer_btn)

        self.add_cart_btn = QPushButton("Себетке қосу")
        self.add_cart_btn.clicked.connect(lambda: self._handle_add(go_checkout=False))
        right_layout.addWidget(self.add_cart_btn)

        self.buy_now_btn = QPushButton("Бірден рәсімдеу  →")
        self.buy_now_btn.setProperty("variant", "primary")
        self.buy_now_btn.clicked.connect(lambda: self._handle_add(go_checkout=True))
        right_layout.addWidget(self.buy_now_btn)
        right_layout.addStretch(1)

        cols.addWidget(left_card, stretch=11)
        cols.addWidget(right_card, stretch=10)
        root.addLayout(cols)
        root.addWidget(SiteFooter())
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        wrap.addStretch(1)
        wrap.addWidget(inner, stretch=100)
        wrap.addStretch(1)
        scroll.setWidget(page)

    def set_batch(self, batch: dict[str, Any], *, is_favorite: bool) -> None:
        self.batch = batch
        self.is_favorite = is_favorite
        self.feedback.clear()

        product = batch["product"]
        store = batch["store"]
        unit_text = unit_label(product["unit"])
        reg = to_decimal(batch["regular_price"])
        disc = to_decimal(batch["discount_price"])
        avail = to_decimal(batch["quantity_available"])
        pct = discount_percent(reg, disc)
        currency = batch.get("currency", "KZT")

        self.unit_badge.setText(unit_text)
        self.discount_badge.setText(f"−{pct}%")
        self.discount_badge.setVisible(pct > 0)

        self.title_label.setText(product["name"])
        desc = product.get("description") or "Сипаттама көрсетілмеген."
        self.desc_label.setText(desc)
        self.expiry_info.setText(f"Жарамдылық мерзімі: {format_datetime(batch['expires_at'])}")
        self.stock_info.setText(f"Қолжетімді қалдық: {format_quantity(avail)} {unit_text}")

        self.price_label.setText(format_money(disc, currency))
        self.old_price_label.setText(format_money(reg, currency))
        self.old_price_label.setVisible(reg > disc)
        saving = max(Decimal("0"), reg - disc)
        self.savings_label.setText(f"Бірліктен үнем: {format_money(saving, currency)}")
        self.savings_label.setVisible(saving > 0)

        self.store_name_label.setText(store["name"])
        self.store_address_label.setText(f"{store['city']}, {store['address']}")

        self.qty_label.setText(f"Саны ({unit_text})")
        self.qty_input.setSingleStep(1.0 if product["unit"] != "kg" else 0.5)
        self.qty_input.setMaximum(max(float(avail), 0.001))
        self.qty_input.setValue(float(avail if avail < Decimal("1") else Decimal("1")))

        role = self.api.user.get("role") if self.api.user else None
        is_seller = role == "seller"
        is_buyer = role == "buyer"

        self.fav_btn.setVisible(is_buyer)
        self._sync_fav()
        self.seller_hint.setVisible(is_seller)
        self.switch_buyer_btn.setVisible(is_seller)
        self.qty_label.setVisible(not is_seller)
        self.qty_input.setVisible(not is_seller)
        self.add_cart_btn.setVisible(not is_seller)
        self.buy_now_btn.setVisible(not is_seller)

    def _sync_fav(self) -> None:
        self.fav_btn.setText("★ Таңдаулыларда" if self.is_favorite else "☆ Таңдаулыларға")
        self.fav_btn.setProperty("saved", "true" if self.is_favorite else "false")
        repolish(self.fav_btn)

    def _toggle_fav(self) -> None:
        if not self.batch:
            return
        self.is_favorite = self.on_toggle_favorite(str(self.batch["batch_id"]))
        self._sync_fav()

    def _handle_switch(self) -> None:
        if self.batch:
            self.on_switch_to_buyer(self.batch)

    def _handle_add(self, *, go_checkout: bool) -> None:
        if not self.batch:
            return
        qty = to_decimal(f"{self.qty_input.value():.3f}")
        self.on_add_to_cart(self.batch, qty, go_checkout)
        if not go_checkout:
            self.feedback.set_message(
                f"«{self.batch['product']['name']}» ({format_quantity(qty)} {unit_label(self.batch['product']['unit'])}) себетке қосылды.",
                "success",
            )


class CheckoutView(QWidget):
    """Full-page Cart & Checkout screen (Pickup address / Delivery + Payment method + Summary)."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_back_to_catalog: Callable[[], None],
        on_request_buyer_auth: Callable[[str], None],
        on_order_confirmed: Callable[[dict[str, Any]], None],
        on_cart_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_back_to_catalog = on_back_to_catalog
        self.on_request_buyer_auth = on_request_buyer_auth
        self.on_order_confirmed = on_order_confirmed
        self.on_cart_changed = on_cart_changed

        self.cart_items: list[CartItem] = []
        self.pending_idempotency_key: str | None = None
        self.pending_payload_sig: tuple | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        page = QWidget()
        wrap = QHBoxLayout(page)
        wrap.setContentsMargins(32, 24, 32, 24)
        wrap.setAlignment(Qt.AlignmentFlag.AlignTop)

        inner = QWidget()
        inner.setMaximumWidth(1160)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        back_btn = QPushButton("← Каталогқа оралу")
        back_btn.setProperty("variant", "link")
        back_btn.clicked.connect(self.on_back_to_catalog)
        root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("Себет және тапсырысты рәсімдеу")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        root.addWidget(build_stepper(active_step=2))

        self.feedback = FeedbackBanner()
        root.addWidget(self.feedback)

        # Empty cart panel
        self.empty_card = QFrame()
        self.empty_card.setObjectName("emptyStateCard")
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(28, 40, 28, 40)
        empty_layout.setSpacing(12)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("Себетіңіз әзірге бос")
        empty_title.setObjectName("sectionTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub = QLabel("Каталогтан өнімдерді таңдап, себетке қосыңыз.")
        empty_sub.setObjectName("mutedText")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        go_cat_btn = QPushButton("Каталогқа өту")
        go_cat_btn.setProperty("variant", "primary")
        go_cat_btn.clicked.connect(self.on_back_to_catalog)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_sub)
        empty_layout.addWidget(go_cat_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_card)

        # Main 2-column checkout body
        self.checkout_body = QWidget()
        cols = QHBoxLayout(self.checkout_body)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(22)

        # --- LEFT COLUMN: Cart items + Fulfillment + Payment ---
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # 1. Cart items card
        items_card = QFrame()
        items_card.setObjectName("surfaceCard")
        ic_layout = QVBoxLayout(items_card)
        ic_layout.setContentsMargins(22, 18, 22, 18)
        ic_layout.setSpacing(12)
        items_head = QHBoxLayout()
        items_step = QLabel("01 / СЕБЕТТЕГІ ӨНІМДЕР")
        items_step.setObjectName("stepLabel")
        clear_cart_btn = QPushButton("Себетті тазарту")
        clear_cart_btn.setProperty("variant", "link")
        clear_cart_btn.clicked.connect(self.clear_cart)
        items_head.addWidget(items_step)
        items_head.addStretch(1)
        items_head.addWidget(clear_cart_btn)
        ic_layout.addLayout(items_head)

        self.items_list_layout = QVBoxLayout()
        self.items_list_layout.setSpacing(10)
        ic_layout.addLayout(self.items_list_layout)
        left_col.addWidget(items_card)

        # 2. Fulfillment card (Pickup address vs Delivery address)
        fulfill_card = QFrame()
        fulfill_card.setObjectName("surfaceCard")
        fc_layout = QVBoxLayout(fulfill_card)
        fc_layout.setContentsMargins(22, 18, 22, 18)
        fc_layout.setSpacing(12)
        fc_step = QLabel("02 / АЛУ ТӘСІЛІ ЖӘНЕ МЕКЕНЖАЙ")
        fc_step.setObjectName("stepLabel")
        fc_layout.addWidget(fc_step)

        self.fulfillment_group = QButtonGroup(self)
        radio_row = QHBoxLayout()
        radio_row.setSpacing(12)

        pickup_opt = QFrame()
        pickup_opt.setObjectName("optionCard")
        po_layout = QVBoxLayout(pickup_opt)
        po_layout.setContentsMargins(14, 12, 14, 12)
        self.pickup_radio = QRadioButton("Алып кету · Тегін")
        self.pickup_radio.setChecked(True)
        po_sub = QLabel("Дүкеннен өзіңіз барып аласыз")
        po_sub.setObjectName("mutedText")
        po_layout.addWidget(self.pickup_radio)
        po_layout.addWidget(po_sub)

        delivery_opt = QFrame()
        delivery_opt.setObjectName("optionCard")
        do_layout = QVBoxLayout(delivery_opt)
        do_layout.setContentsMargins(14, 12, 14, 12)
        self.delivery_radio = QRadioButton("Жеткізу")
        do_sub = QLabel("Көрсетілген мекенжайға жеткізу")
        do_sub.setObjectName("mutedText")
        do_layout.addWidget(self.delivery_radio)
        do_layout.addWidget(do_sub)

        self.fulfillment_group.addButton(self.pickup_radio)
        self.fulfillment_group.addButton(self.delivery_radio)
        self.pickup_radio.toggled.connect(self._sync_fulfillment_ui)

        radio_row.addWidget(pickup_opt, stretch=1)
        radio_row.addWidget(delivery_opt, stretch=1)
        fc_layout.addLayout(radio_row)

        # Pickup address display box
        self.pickup_address_box = QFrame()
        self.pickup_address_box.setObjectName("storeSummary")
        pa_layout = QVBoxLayout(self.pickup_address_box)
        pa_layout.setContentsMargins(16, 14, 16, 14)
        pa_layout.setSpacing(4)
        pa_title = QLabel("Алып кету мекенжайы")
        pa_title.setObjectName("unitBadge")
        self.pickup_store_label = QLabel()
        self.pickup_store_label.setObjectName("productTitle")
        self.pickup_addr_label = QLabel()
        self.pickup_addr_label.setWordWrap(True)
        pa_note = QLabel("Тапсырыс расталған соң кассада тапсырыс кодын көрсетіңіз.")
        pa_note.setObjectName("mutedText")
        pa_note.setWordWrap(True)
        pa_layout.addWidget(pa_title)
        pa_layout.addWidget(self.pickup_store_label)
        pa_layout.addWidget(self.pickup_addr_label)
        pa_layout.addWidget(pa_note)
        fc_layout.addWidget(self.pickup_address_box)

        # Delivery address input box
        self.delivery_address_box = QWidget()
        da_layout = QVBoxLayout(self.delivery_address_box)
        da_layout.setContentsMargins(0, 4, 0, 0)
        da_layout.setSpacing(6)
        da_layout.addWidget(QLabel("Жеткізу мекенжайы"))
        self.delivery_address_input = QLineEdit()
        self.delivery_address_input.setMaxLength(500)
        self.delivery_address_input.setPlaceholderText("Мысалы: Алматы, Абай даңғылы, 15, 24-пәтер")
        self.delivery_address_input.textChanged.connect(self._invalidate_pending_key)
        da_layout.addWidget(self.delivery_address_input)
        self.delivery_address_box.setVisible(False)
        fc_layout.addWidget(self.delivery_address_box)

        left_col.addWidget(fulfill_card)

        # 3. Payment method card (honest: pay at pickup active, online clearly marked pending provider)
        pay_card = QFrame()
        pay_card.setObjectName("surfaceCard")
        pc_layout = QVBoxLayout(pay_card)
        pc_layout.setContentsMargins(22, 18, 22, 18)
        pc_layout.setSpacing(10)
        pc_step = QLabel("03 / ТӨЛЕМ ТӘСІЛІ")
        pc_step.setObjectName("stepLabel")
        pc_layout.addWidget(pc_step)

        pay_pickup_box = QFrame()
        pay_pickup_box.setObjectName("optionCard")
        pp_layout = QVBoxLayout(pay_pickup_box)
        pp_layout.setContentsMargins(14, 12, 14, 12)
        self.pay_pickup_radio = QRadioButton("Алып кету / жеткізу кезінде төлеу")
        self.pay_pickup_radio.setChecked(True)
        pp_sub = QLabel("Қолма-қол немесе дүкен терминалы арқылы төлейсіз")
        pp_sub.setObjectName("mutedText")
        pp_layout.addWidget(self.pay_pickup_radio)
        pp_layout.addWidget(pp_sub)

        pay_online_box = QFrame()
        pay_online_box.setObjectName("optionCard")
        pay_online_box.setProperty("disabledOption", "true")
        repolish(pay_online_box)
        po2_layout = QVBoxLayout(pay_online_box)
        po2_layout.setContentsMargins(14, 12, 14, 12)
        self.pay_online_radio = QRadioButton("Онлайн банктік карта (қосылу кезеңінде)")
        self.pay_online_radio.setEnabled(False)
        po2_sub = QLabel("Нақты төлем провайдері қосылған соң қолжетімді болады.")
        po2_sub.setObjectName("mutedText")
        po2_layout.addWidget(self.pay_online_radio)
        po2_layout.addWidget(po2_sub)

        pc_layout.addWidget(pay_pickup_box)
        pc_layout.addWidget(pay_online_box)
        left_col.addWidget(pay_card)
        left_col.addStretch(1)

        # --- RIGHT COLUMN: Order Summary & Confirm CTA ---
        summary_card = QFrame()
        summary_card.setObjectName("surfaceCard")
        summary_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        sc_layout = QVBoxLayout(summary_card)
        sc_layout.setContentsMargins(24, 22, 24, 22)
        sc_layout.setSpacing(12)

        sum_title = QLabel("Тапсырыс қорытындысы")
        sum_title.setObjectName("sectionTitle")
        sc_layout.addWidget(sum_title)

        def summary_row(label_text: str, value_obj: QLabel) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setObjectName("mutedText")
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(value_obj)
            return row

        self.sum_original_lbl = QLabel("0 ₸")
        self.sum_savings_lbl = QLabel("0 ₸")
        self.sum_savings_lbl.setObjectName("savingsText")
        self.sum_fulfill_lbl = QLabel("Тегін")
        self.sum_total_lbl = QLabel("0 ₸")
        self.sum_total_lbl.setObjectName("priceLabel")

        sc_layout.addLayout(summary_row("Бастапқы баға:", self.sum_original_lbl))
        sc_layout.addLayout(summary_row("Сіздің үнеміңіз:", self.sum_savings_lbl))
        sc_layout.addLayout(summary_row("Алу тәсілі:", self.sum_fulfill_lbl))

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        sc_layout.addWidget(divider)

        total_row = QHBoxLayout()
        total_lbl = QLabel("Барлығы:")
        total_lbl.setObjectName("productTitle")
        total_row.addWidget(total_lbl)
        total_row.addStretch(1)
        total_row.addWidget(self.sum_total_lbl)
        sc_layout.addLayout(total_row)

        # Auth gate inside summary for guests / sellers (preserving cart!)
        self.auth_notice = QLabel()
        self.auth_notice.setObjectName("sellerBookingHint")
        self.auth_notice.setWordWrap(True)
        sc_layout.addWidget(self.auth_notice)

        self.guest_login_btn = QPushButton("Кіру (себет сақталады)")
        self.guest_login_btn.setProperty("variant", "primary")
        self.guest_login_btn.clicked.connect(lambda: self.on_request_buyer_auth("login"))
        sc_layout.addWidget(self.guest_login_btn)

        self.guest_register_btn = QPushButton("Сатып алушы болып тіркелу")
        self.guest_register_btn.clicked.connect(lambda: self.on_request_buyer_auth("register"))
        sc_layout.addWidget(self.guest_register_btn)

        self.confirm_btn = QPushButton("Броньды растау  →")
        self.confirm_btn.setProperty("variant", "primary")
        self.confirm_btn.clicked.connect(self._submit_order)
        sc_layout.addWidget(self.confirm_btn)

        note = QLabel("Бронь жасалғаннан кейін қалдық автоматты түрде сізге бекітіледі.")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        sc_layout.addWidget(note)
        sc_layout.addStretch(1)

        cols.addLayout(left_col, stretch=13)
        cols.addWidget(summary_card, stretch=9, alignment=Qt.AlignmentFlag.AlignTop)
        root.addWidget(self.checkout_body)
        root.addWidget(SiteFooter())
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        wrap.addStretch(1)
        wrap.addWidget(inner, stretch=100)
        wrap.addStretch(1)
        scroll.setWidget(page)

        self.render_cart()

    def item_count(self) -> int:
        return len(self.cart_items)

    def _invalidate_pending_key(self) -> None:
        self.pending_idempotency_key = None
        self.pending_payload_sig = None

    def add_batch(self, batch: dict[str, Any], quantity: Decimal | None = None) -> tuple[bool, str]:
        incoming = cart_item_from_batch(batch, quantity=quantity)
        if self.cart_items and self.cart_items[0].store_id != incoming.store_id:
            return (
                False,
                f"Себетте «{self.cart_items[0].store_name}» дүкенінің өнімдері бар. "
                "Бір тапсырысқа тек бір дүкеннің өнімдері кіреді — алдымен себетті рәсімдеңіз немесе тазартыңыз.",
            )

        for existing in self.cart_items:
            if existing.batch_id == incoming.batch_id:
                new_qty = existing.quantity + incoming.quantity
                if existing.available > 0 and new_qty > existing.available:
                    new_qty = existing.available
                existing.quantity = new_qty
                self._invalidate_pending_key()
                self.render_cart()
                self.on_cart_changed()
                return True, f"«{existing.name}» саны себетте жаңартылды ({format_quantity(existing.quantity)} {unit_label(existing.unit)})."

        self.cart_items.append(incoming)
        self._invalidate_pending_key()
        self.render_cart()
        self.on_cart_changed()
        return True, f"«{incoming.name}» себетке қосылды."

    def clear_cart(self) -> None:
        self.cart_items.clear()
        self._invalidate_pending_key()
        self.feedback.clear()
        self.render_cart()
        self.on_cart_changed()

    def _remove_item(self, batch_id: str) -> None:
        self.cart_items = [item for item in self.cart_items if item.batch_id != batch_id]
        self._invalidate_pending_key()
        self.render_cart()
        self.on_cart_changed()

    def _update_item_qty(self, batch_id: str, value: float) -> None:
        for item in self.cart_items:
            if item.batch_id == batch_id:
                item.quantity = to_decimal(f"{value:.3f}")
                break
        self._invalidate_pending_key()
        self._update_summary()

    def _sync_fulfillment_ui(self) -> None:
        is_pickup = self.pickup_radio.isChecked()
        self.pickup_address_box.setVisible(is_pickup)
        self.delivery_address_box.setVisible(not is_pickup)
        self._invalidate_pending_key()
        self._update_summary()

    def _clear_items_layout(self) -> None:
        while self.items_list_layout.count():
            item = self.items_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def render_cart(self) -> None:
        has_items = len(self.cart_items) > 0
        self.empty_card.setVisible(not has_items)
        self.checkout_body.setVisible(has_items)
        self._clear_items_layout()

        if not has_items:
            return

        store_ref = self.cart_items[0]
        self.pickup_store_label.setText(store_ref.store_name)
        self.pickup_addr_label.setText(f"{store_ref.store_city}, {store_ref.store_address}")

        for item in self.cart_items:
            row_card = QFrame()
            row_card.setObjectName("optionCard")
            rl = QHBoxLayout(row_card)
            rl.setContentsMargins(14, 12, 14, 12)
            rl.setSpacing(12)

            info = QVBoxLayout()
            info.setSpacing(3)
            name_lbl = QLabel(item.name)
            name_lbl.setObjectName("productTitle")
            name_lbl.setWordWrap(True)
            sub_lbl = QLabel(
                f"{format_money(item.discount_price, item.currency)} / {unit_label(item.unit)} · "
                f"Қалдығы: {format_quantity(item.available)} {unit_label(item.unit)}"
            )
            sub_lbl.setObjectName("mutedText")
            info.addWidget(name_lbl)
            info.addWidget(sub_lbl)
            rl.addLayout(info, stretch=1)

            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setMinimum(0.001)
            spin.setMaximum(max(float(item.available), 0.001))
            spin.setSingleStep(1.0 if item.unit != "kg" else 0.5)
            spin.setValue(float(item.quantity))
            spin.setMaximumWidth(105)
            spin.valueChanged.connect(lambda val, bid=item.batch_id: self._update_item_qty(bid, val))
            rl.addWidget(spin)

            remove_btn = QPushButton("Өшіру")
            remove_btn.setProperty("variant", "link")
            remove_btn.clicked.connect(lambda _=False, bid=item.batch_id: self._remove_item(bid))
            rl.addWidget(remove_btn)

            self.items_list_layout.addWidget(row_card)

        self._sync_auth_controls()
        self._update_summary()

    def _sync_auth_controls(self) -> None:
        user = self.api.user
        role = user.get("role") if user else None
        is_buyer = role == "buyer" and bool(self.api.token)
        is_seller = role == "seller"

        self.confirm_btn.setVisible(is_buyer)
        if is_buyer:
            self.confirm_btn.setText("Броньды тексеру" if self.pending_idempotency_key else "Броньды растау  →")
            self.auth_notice.setVisible(False)
            self.guest_login_btn.setVisible(False)
            self.guest_register_btn.setVisible(False)
        elif is_seller:
            self.auth_notice.setText(
                "Сіз сатушы аккаунтымен кірдіңіз. Брондау тек сатып алушыларға қолжетімді — "
                "сатып алушы аккаунтына ауыссаңыз, себет сақталады."
            )
            self.auth_notice.setVisible(True)
            self.guest_login_btn.setText("Сатып алушы ретінде кіру")
            self.guest_login_btn.setVisible(True)
            self.guest_register_btn.setVisible(True)
        else:
            self.auth_notice.setText(
                "Тапсырысты растау үшін сатып алушы ретінде кіріңіз немесе тіркеліңіз. "
                "Себеттегі өнімдер мен мекенжай сақталады."
            )
            self.auth_notice.setVisible(True)
            self.guest_login_btn.setText("Кіру (себет сақталады)")
            self.guest_login_btn.setVisible(True)
            self.guest_register_btn.setVisible(True)

    def _update_summary(self) -> None:
        orig_total = Decimal("0.00")
        disc_total = Decimal("0.00")
        currency = self.cart_items[0].currency if self.cart_items else "KZT"
        for item in self.cart_items:
            orig_total += item.regular_price * item.quantity
            disc_total += item.discount_price * item.quantity
        savings = max(Decimal("0.00"), orig_total - disc_total)
        self.sum_original_lbl.setText(format_money(orig_total, currency))
        self.sum_savings_lbl.setText(f"−{format_money(savings, currency)}" if savings > 0 else "0 ₸")
        self.sum_fulfill_lbl.setText("Алып кету (Тегін)" if self.pickup_radio.isChecked() else "Жеткізу")
        self.sum_total_lbl.setText(format_money(disc_total, currency))

    def _submit_order(self) -> None:
        if not self.cart_items:
            return
        if not self.api.user or self.api.user.get("role") != "buyer" or not self.api.token:
            self._sync_auth_controls()
            return

        fulfillment = "pickup" if self.pickup_radio.isChecked() else "delivery"
        delivery_addr = self.delivery_address_input.text().strip() if fulfillment == "delivery" else None
        if fulfillment == "delivery" and not delivery_addr:
            self.feedback.set_message("Жеткізу мекенжайын енгізіңіз.", "error")
            self.delivery_address_input.setFocus()
            return

        items_payload = [
            {"batch_id": item.batch_id, "quantity": format_decimal_api(item.quantity, places=3)}
            for item in self.cart_items
        ]
        sig = (tuple((x["batch_id"], x["quantity"]) for x in items_payload), fulfillment, delivery_addr)
        if self.pending_idempotency_key is None or self.pending_payload_sig != sig:
            self.pending_idempotency_key = str(uuid.uuid4())
            self.pending_payload_sig = sig

        self.confirm_btn.setDisabled(True)
        self.feedback.set_message("Тапсырыс рәсімделуде…", "")
        try:
            order = self.api.create_cart_order(
                items=items_payload,
                fulfillment_method=fulfillment,
                delivery_address=delivery_addr,
                idempotency_key=self.pending_idempotency_key,
            )
        except ApiError as exc:
            self.confirm_btn.setDisabled(False)
            if exc.status_code in {400, 403, 404, 409, 422}:
                self._invalidate_pending_key()
                self.feedback.set_message(translate_api_error(exc), "error")
            else:
                self.confirm_btn.setText("Броньды тексеру")
                self.feedback.set_message(
                    "Бронь нәтижесі белгісіз. Сол сұрауды қайта жіберіп тексеріңіз.",
                    "error",
                )
            return

        self.confirm_btn.setDisabled(False)
        self.cart_items.clear()
        self._invalidate_pending_key()
        self.feedback.clear()
        self.render_cart()
        self.on_cart_changed()
        self.on_order_confirmed(order)


class OrderConfirmationView(QWidget):
    """Order confirmation screen with pickup code, visual QR matrix, store address, and 3 steps."""

    def __init__(
        self,
        *,
        on_back_to_catalog: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_back_to_catalog = on_back_to_catalog
        self.last_order: dict[str, Any] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        page = QWidget()
        wrap = QHBoxLayout(page)
        wrap.setContentsMargins(32, 24, 32, 24)
        wrap.setAlignment(Qt.AlignmentFlag.AlignTop)

        inner = QWidget()
        inner.setMaximumWidth(980)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        root.addWidget(build_stepper(active_step=3))

        banner = QFrame()
        banner.setObjectName("aiPanel")
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(22, 18, 22, 18)
        b_layout.setSpacing(14)
        b_layout.addWidget(FormSymbol("✓"))
        b_col = QVBoxLayout()
        b_col.setSpacing(3)
        b_title = QLabel("Бронь сәтті рәсімделді!")
        b_title.setObjectName("pageTitle")
        b_sub = QLabel("Төмендегі тапсырыс кодын дүкенде көрсетіңіз.")
        b_sub.setObjectName("mutedText")
        b_col.addWidget(b_title)
        b_col.addWidget(b_sub)
        b_layout.addLayout(b_col, stretch=1)
        root.addWidget(banner)

        # Order card with QR + details
        card = QFrame()
        card.setObjectName("surfaceCard")
        c_layout = QHBoxLayout(card)
        c_layout.setContentsMargins(26, 24, 26, 24)
        c_layout.setSpacing(26)

        qr_col = QVBoxLayout()
        qr_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        qr_col.setSpacing(10)
        self.qr_widget = PickupCodeWidget()
        self.code_label = QLabel()
        self.code_label.setObjectName("pickupCodeLabel")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill = QLabel()
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_col.addWidget(self.qr_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        qr_col.addWidget(self.code_label)
        qr_col.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignCenter)
        c_layout.addLayout(qr_col)

        details_col = QVBoxLayout()
        details_col.setSpacing(10)
        self.store_label = QLabel()
        self.store_label.setObjectName("sectionTitle")
        self.store_label.setWordWrap(True)
        self.address_label = QLabel()
        self.address_label.setWordWrap(True)
        self.payment_label = QLabel()
        self.payment_label.setObjectName("mutedText")
        self.items_summary_label = QLabel()
        self.items_summary_label.setWordWrap(True)
        self.totals_label = QLabel()
        self.totals_label.setObjectName("priceLabel")
        self.savings_label = QLabel()
        self.savings_label.setObjectName("savingsText")

        details_col.addWidget(self.store_label)
        details_col.addWidget(self.address_label)
        details_col.addWidget(self.payment_label)
        details_col.addWidget(self.items_summary_label)
        details_col.addWidget(self.totals_label)
        details_col.addWidget(self.savings_label)

        steps_box = QFrame()
        steps_box.setObjectName("storeSummary")
        sb_layout = QVBoxLayout(steps_box)
        sb_layout.setContentsMargins(16, 12, 16, 12)
        sb_layout.setSpacing(4)
        sb_title = QLabel("Тапсырысты алу қадамдары")
        sb_title.setObjectName("unitBadge")
        sb_steps = QLabel(
            "1. Сатушы тапсырысты растағанын күтіңіз.\n"
            "2. Көрсетілген мекенжайға барып, тапсырыс кодын көрсетіңіз.\n"
            "3. Өнімді алып, орнында төлеңіз."
        )
        sb_steps.setObjectName("mutedText")
        sb_steps.setWordWrap(True)
        sb_layout.addWidget(sb_title)
        sb_layout.addWidget(sb_steps)
        details_col.addWidget(steps_box)
        c_layout.addLayout(details_col, stretch=1)
        root.addWidget(card)

        actions = QHBoxLayout()
        back_cat_btn = QPushButton("Каталогқа оралу")
        back_cat_btn.setProperty("variant", "primary")
        back_cat_btn.clicked.connect(self.on_back_to_catalog)
        actions.addWidget(back_cat_btn)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addWidget(SiteFooter())
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        wrap.addStretch(1)
        wrap.addWidget(inner, stretch=100)
        wrap.addStretch(1)
        scroll.setWidget(page)

    def set_order(self, order: dict[str, Any]) -> None:
        self.last_order = order
        pickup_code = order.get("pickup_code") or f"OB-{str(order['id'])[:8].upper()}"
        self.qr_widget.set_code(pickup_code)
        self.code_label.setText(pickup_code)

        status = order.get("status", "reserved")
        self.status_pill.setText(order_status_label(status))
        self.status_pill.setProperty("orderStatus", status)
        repolish(self.status_pill)

        store = order.get("store", {})
        self.store_label.setText(store.get("name", "Дүкен"))
        if order.get("fulfillment_method") == "delivery":
            self.address_label.setText(
                f"Жеткізу мекенжайы: {order.get('delivery_address', '')}\n"
                f"Дүкен: {store.get('city', '')}, {store.get('address', '')}"
            )
        else:
            self.address_label.setText(
                f"Алып кету мекенжайы: {store.get('city', '')}, {store.get('address', '')}"
            )

        self.payment_label.setText("Төлем тәсілі: Алып кету / жеткізу кезінде төлеу")

        currency = order.get("currency", "KZT")
        lines = []
        for item in order.get("items", []):
            lines.append(
                f"• {item['product_name']} × {format_quantity(item['quantity'])} "
                f"{unit_label(item['unit'])} — {format_money(item['line_total'], currency)}"
            )
        self.items_summary_label.setText("\n".join(lines))
        self.totals_label.setText(f"Жалпы сома: {format_money(order['total_amount'], currency)}")

        savings = to_decimal(order.get("savings_amount", "0"))
        if savings > 0:
            self.savings_label.setText(f"Сіздің үнеміңіз: {format_money(savings, currency)}")
            self.savings_label.setVisible(True)
        else:
            self.savings_label.setVisible(False)
