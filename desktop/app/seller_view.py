from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .formatting import (
    UNIT_LABELS,
    format_datetime,
    format_decimal_api,
    format_money,
    format_quantity,
    order_status_label,
)
from .widgets import FeedbackBanner, FormSymbol, SiteFooter, repolish


ORDERS_PAGE_SIZE = 50


class SellerView(QWidget):
    """Seller dashboard: store setup, batch publishing, and order confirmation."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_request_auth: Callable[[str, str], None],
        on_view_published: Callable[[str], None],
        on_back_to_catalog: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_request_auth = on_request_auth
        self.on_view_published = on_view_published
        self.on_back_to_catalog = on_back_to_catalog

        self.store: dict[str, Any] | None = None
        self.published_product_name: str | None = None
        self.orders: list[dict[str, Any]] = []
        self.orders_offset = 0
        self.orders_has_more = False
        self.confirming_ids: set[str] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        page_wrap = QHBoxLayout(page)
        page_wrap.setContentsMargins(32, 24, 32, 24)

        content = QWidget()
        content.setMaximumWidth(1160)
        self.root = QVBoxLayout(content)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(18)

        if self.on_back_to_catalog is not None:
            back_btn = QPushButton("← Каталогқа оралу")
            back_btn.setProperty("variant", "link")
            back_btn.clicked.connect(self.on_back_to_catalog)
            self.root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        heading = QLabel("Сатушы кабинеті")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Өнім партияларын жариялап, дүкеніңізге түскен тапсырыстарды растаңыз.")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        self.root.addWidget(heading)
        self.root.addWidget(subtitle)

        # Gate panel for guests or buyers
        self.gate_card = QFrame()
        self.gate_card.setObjectName("surfaceCard")
        self.gate_card.setMaximumWidth(700)
        gate_layout = QVBoxLayout(self.gate_card)
        gate_layout.setContentsMargins(26, 24, 26, 24)
        gate_layout.setSpacing(12)
        gate_layout.addWidget(FormSymbol("↗"))
        gate_title = QLabel("Сатушы аккаунты")
        gate_title.setObjectName("sectionTitle")
        self.gate_message = QLabel("Дүкен ашып, өнім жариялау үшін сатушы аккаунтына кіріңіз.")
        self.gate_message.setObjectName("mutedText")
        self.gate_message.setWordWrap(True)
        gate_buttons = QHBoxLayout()
        self.gate_login_btn = QPushButton("Кіру")
        self.gate_login_btn.setProperty("variant", "primary")
        self.gate_login_btn.clicked.connect(lambda: self.on_request_auth("login", "seller"))
        self.gate_register_btn = QPushButton("Сатушы болып тіркелу")
        self.gate_register_btn.clicked.connect(lambda: self.on_request_auth("register", "seller"))
        gate_buttons.addWidget(self.gate_login_btn)
        gate_buttons.addWidget(self.gate_register_btn)
        gate_buttons.addStretch(1)
        gate_layout.addWidget(gate_title)
        gate_layout.addWidget(self.gate_message)
        gate_layout.addLayout(gate_buttons)
        self.root.addWidget(self.gate_card)

        # Workspace for authenticated sellers
        self.workspace = QWidget()
        ws_layout = QVBoxLayout(self.workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(16)

        top_panels = QHBoxLayout()
        top_panels.setSpacing(16)

        # 01 / Store panel
        store_card = QFrame()
        store_card.setObjectName("surfaceCard")
        store_layout = QVBoxLayout(store_card)
        store_layout.setContentsMargins(20, 18, 20, 18)
        store_layout.setSpacing(10)

        step1 = QLabel("01 / ДҮКЕН")
        step1.setObjectName("stepLabel")
        store_heading = QLabel("Сіздің дүкен")
        store_heading.setObjectName("sectionTitle")
        self.store_feedback = FeedbackBanner()
        store_layout.addWidget(step1)
        store_layout.addWidget(store_heading)
        store_layout.addWidget(self.store_feedback)

        self.store_details = QFrame()
        self.store_details.setObjectName("storeSummary")
        details_layout = QVBoxLayout(self.store_details)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(6)
        details_layout.addWidget(FormSymbol("⌂"))
        self.store_name_label = QLabel()
        self.store_name_label.setObjectName("productTitle")
        self.store_name_label.setWordWrap(True)
        self.store_location_label = QLabel()
        self.store_location_label.setObjectName("mutedText")
        self.store_location_label.setWordWrap(True)
        details_layout.addWidget(self.store_name_label)
        details_layout.addWidget(self.store_location_label)
        self.store_details.setVisible(False)
        store_layout.addWidget(self.store_details)

        self.store_form = QWidget()
        sf_layout = QVBoxLayout(self.store_form)
        sf_layout.setContentsMargins(0, 0, 0, 0)
        sf_layout.setSpacing(8)
        sf_layout.addWidget(QLabel("Дүкен атауы"))
        self.store_name_input = QLineEdit()
        self.store_name_input.setMaxLength(160)
        self.store_name_input.setPlaceholderText("Мысалы, Күнде нан")
        sf_layout.addWidget(self.store_name_input)

        sf_layout.addWidget(QLabel("Қала"))
        self.store_city_input = QLineEdit()
        self.store_city_input.setMaxLength(120)
        self.store_city_input.setPlaceholderText("Мысалы, Қызылорда")
        sf_layout.addWidget(self.store_city_input)

        sf_layout.addWidget(QLabel("Мекенжай"))
        self.store_address_input = QLineEdit()
        self.store_address_input.setMaxLength(500)
        self.store_address_input.setPlaceholderText("Көше, үй нөмірі")
        sf_layout.addWidget(self.store_address_input)

        self.store_submit_btn = QPushButton("Дүкенді сақтау")
        self.store_submit_btn.setProperty("variant", "primary")
        self.store_submit_btn.clicked.connect(self._submit_store)
        sf_layout.addWidget(self.store_submit_btn)
        self.store_form.setVisible(False)
        store_layout.addWidget(self.store_form)
        store_layout.addStretch(1)

        # 02 / Batch panel
        batch_card = QFrame()
        batch_card.setObjectName("surfaceCard")
        batch_layout = QVBoxLayout(batch_card)
        batch_layout.setContentsMargins(20, 18, 20, 18)
        batch_layout.setSpacing(10)

        step2 = QLabel("02 / ПАРТИЯ")
        step2.setObjectName("stepLabel")
        batch_heading = QLabel("Жаңа партия")
        batch_heading.setObjectName("sectionTitle")
        self.batch_placeholder = QLabel("Партия жариялау үшін алдымен дүкеніңізді қосыңыз.")
        self.batch_placeholder.setObjectName("mutedText")
        self.batch_placeholder.setWordWrap(True)
        batch_layout.addWidget(step2)
        batch_layout.addWidget(batch_heading)
        batch_layout.addWidget(self.batch_placeholder)

        self.batch_form = QWidget()
        bf_layout = QVBoxLayout(self.batch_form)
        bf_layout.setContentsMargins(0, 0, 0, 0)
        bf_layout.setSpacing(8)

        row_name = QHBoxLayout()
        name_col = QVBoxLayout()
        name_col.addWidget(QLabel("Өнім атауы"))
        self.product_name_input = QLineEdit()
        self.product_name_input.setMaxLength(180)
        self.product_name_input.setPlaceholderText("Мысалы, ашытқылы нан")
        name_col.addWidget(self.product_name_input)

        unit_col = QVBoxLayout()
        unit_col.addWidget(QLabel("Өлшем бірлігі"))
        self.unit_combo = QComboBox()
        for value, label in UNIT_LABELS:
            self.unit_combo.addItem(label, value)
        unit_col.addWidget(self.unit_combo)

        row_name.addLayout(name_col, stretch=2)
        row_name.addLayout(unit_col, stretch=1)
        bf_layout.addLayout(row_name)

        bf_layout.addWidget(QLabel("Өнім туралы (міндетті емес)"))
        self.product_desc_input = QPlainTextEdit()
        self.product_desc_input.setMaximumHeight(64)
        self.product_desc_input.setPlaceholderText("Құрамы, салмағы немесе басқа мәлімет")
        bf_layout.addWidget(self.product_desc_input)

        row_nums = QHBoxLayout()
        qty_col = QVBoxLayout()
        qty_col.addWidget(QLabel("Саны"))
        self.batch_qty_input = QDoubleSpinBox()
        self.batch_qty_input.setDecimals(3)
        self.batch_qty_input.setMinimum(0.001)
        self.batch_qty_input.setMaximum(999_999_999.999)
        self.batch_qty_input.setValue(3.0)
        qty_col.addWidget(self.batch_qty_input)

        reg_col = QVBoxLayout()
        reg_col.addWidget(QLabel("Бастапқы баға, ₸"))
        self.regular_price_input = QDoubleSpinBox()
        self.regular_price_input.setDecimals(2)
        self.regular_price_input.setMinimum(0.0)
        self.regular_price_input.setMaximum(9_999_999_999.99)
        self.regular_price_input.setValue(1000.0)
        reg_col.addWidget(self.regular_price_input)

        disc_col = QVBoxLayout()
        disc_col.addWidget(QLabel("Жеңілдік бағасы, ₸"))
        self.discount_price_input = QDoubleSpinBox()
        self.discount_price_input.setDecimals(2)
        self.discount_price_input.setMinimum(0.0)
        self.discount_price_input.setMaximum(9_999_999_999.99)
        self.discount_price_input.setValue(700.0)
        disc_col.addWidget(self.discount_price_input)

        row_nums.addLayout(qty_col)
        row_nums.addLayout(reg_col)
        row_nums.addLayout(disc_col)
        bf_layout.addLayout(row_nums)

        bf_layout.addWidget(QLabel("Жарамдылық мерзімі"))
        self.expires_input = QDateTimeEdit()
        self.expires_input.setCalendarPopup(True)
        self.expires_input.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._reset_default_expiry()
        bf_layout.addWidget(self.expires_input)

        publish_row = QHBoxLayout()
        self.publish_btn = QPushButton("Партияны жариялау")
        self.publish_btn.setProperty("variant", "primary")
        self.publish_btn.clicked.connect(self._submit_batch)
        self.view_published_btn = QPushButton("Каталогта көру →")
        self.view_published_btn.setProperty("variant", "link")
        self.view_published_btn.setVisible(False)
        self.view_published_btn.clicked.connect(self._open_published_in_catalog)
        publish_row.addWidget(self.publish_btn)
        publish_row.addWidget(self.view_published_btn)
        publish_row.addStretch(1)
        bf_layout.addLayout(publish_row)

        self.batch_form.setVisible(False)
        batch_layout.addWidget(self.batch_form)

        self.publish_feedback = FeedbackBanner()
        batch_layout.addWidget(self.publish_feedback)

        top_panels.addWidget(store_card, stretch=1)
        top_panels.addWidget(batch_card, stretch=2)
        ws_layout.addLayout(top_panels)

        # 03 / Orders panel
        orders_card = QFrame()
        orders_card.setObjectName("surfaceCard")
        orders_layout = QVBoxLayout(orders_card)
        orders_layout.setContentsMargins(20, 18, 20, 18)
        orders_layout.setSpacing(12)

        orders_header = QHBoxLayout()
        orders_title = QLabel("Тапсырыстар")
        orders_title.setObjectName("sectionTitle")
        self.orders_refresh_btn = QPushButton("Жаңарту")
        self.orders_refresh_btn.clicked.connect(lambda: self.load_orders(append=False))
        orders_header.addWidget(orders_title)
        orders_header.addStretch(1)
        orders_header.addWidget(self.orders_refresh_btn)
        orders_layout.addLayout(orders_header)

        self.orders_state = FeedbackBanner()
        self.orders_action_feedback = FeedbackBanner()
        orders_layout.addWidget(self.orders_state)
        orders_layout.addWidget(self.orders_action_feedback)

        self.orders_container = QVBoxLayout()
        self.orders_container.setSpacing(10)
        orders_layout.addLayout(self.orders_container)

        self.orders_more_btn = QPushButton("Тағы көрсету")
        self.orders_more_btn.setVisible(False)
        self.orders_more_btn.clicked.connect(lambda: self.load_orders(append=True))
        orders_layout.addWidget(self.orders_more_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        ws_layout.addWidget(orders_card)
        self.root.addWidget(self.workspace)
        self.root.addStretch(1)
        self.root.addWidget(SiteFooter())

        page_wrap.addStretch(1)
        page_wrap.addWidget(content, stretch=100)
        page_wrap.addStretch(1)
        scroll.setWidget(page)
        outer.addWidget(scroll)

    def _reset_default_expiry(self) -> None:
        future = datetime.now() + timedelta(hours=24)
        self.expires_input.setDateTime(
            QDateTime(future.year, future.month, future.day, future.hour, future.minute, 0)
        )

    def reset_state(self) -> None:
        self.store = None
        self.published_product_name = None
        self.orders = []
        self.orders_offset = 0
        self.orders_has_more = False
        self.confirming_ids.clear()
        self.store_name_input.clear()
        self.store_city_input.clear()
        self.store_address_input.clear()
        self.product_name_input.clear()
        self.product_desc_input.clear()
        self.view_published_btn.setVisible(False)
        self.store_feedback.clear()
        self.publish_feedback.clear()
        self.orders_state.clear()
        self.orders_action_feedback.clear()
        self._clear_orders_widgets()

    def refresh(self) -> None:
        user = self.api.user
        is_seller = user is not None and user.get("role") == "seller"
        self.gate_card.setVisible(not is_seller)
        self.workspace.setVisible(is_seller)

        if not is_seller:
            if user is not None:
                self.gate_message.setText("Партия жариялау үшін сатушы аккаунтымен кіріңіз.")
                self.gate_login_btn.setText("Сатушы ретінде кіру")
            else:
                self.gate_message.setText("Дүкен ашып, өнім жариялау үшін сатушы аккаунтына кіріңіз.")
                self.gate_login_btn.setText("Кіру")
            return

        self.store_form.setVisible(False)
        self.store_details.setVisible(False)
        self.batch_form.setVisible(False)
        self.batch_placeholder.setVisible(False)
        self.store_feedback.set_message("Дүкен деректері жүктелуде…", "")

        try:
            store = self.api.get_seller_store()
        except ApiError as exc:
            self.store_feedback.set_message(translate_api_error(exc), "error")
        else:
            self._render_store(store)

        self.load_orders(append=False)

    def _render_store(self, store: dict[str, Any] | None) -> None:
        self.store = store
        has_store = store is not None
        is_active = bool(store and store.get("is_active"))

        self.store_form.setVisible(not has_store)
        self.store_details.setVisible(has_store)
        self.batch_form.setVisible(is_active)
        self.batch_placeholder.setVisible(not is_active)

        if has_store:
            self.store_name_label.setText(store["name"])
            self.store_location_label.setText(f"{store['city']} · {store['address']}")
            if not is_active:
                self.batch_placeholder.setText("Партия жариялау үшін дүкен белсенді болуы керек.")
                self.store_feedback.set_message("Дүкен белсенді емес.", "error")
            else:
                self.store_feedback.clear()
        else:
            self.batch_placeholder.setText("Партия жариялау үшін алдымен дүкеніңізді қосыңыз.")
            self.store_feedback.clear()

    def _submit_store(self) -> None:
        name = self.store_name_input.text().strip()
        city = self.store_city_input.text().strip()
        address = self.store_address_input.text().strip()
        if not name or not city or not address:
            self.store_feedback.set_message("Дүкен атауы, қала және мекенжайды толтырыңыз.", "error")
            return

        self.store_submit_btn.setDisabled(True)
        self.store_feedback.clear()
        try:
            store = self.api.create_seller_store(name=name, city=city, address=address)
        except ApiError as exc:
            self.store_submit_btn.setDisabled(False)
            if exc.status_code == 409:
                self.refresh()
            else:
                self.store_feedback.set_message(translate_api_error(exc), "error")
            return

        self.store_submit_btn.setDisabled(False)
        self._render_store(store)
        self.store_feedback.set_message("Дүкен ашылды. Енді партия жариялауға болады.", "success")
        self.product_name_input.setFocus()

    def _submit_batch(self) -> None:
        name = self.product_name_input.text().strip()
        description = self.product_desc_input.toPlainText().strip()
        unit = self.unit_combo.currentData()
        qty = Decimal(f"{self.batch_qty_input.value():.3f}")
        regular_price = Decimal(f"{self.regular_price_input.value():.2f}")
        discount_price = Decimal(f"{self.discount_price_input.value():.2f}")

        self.view_published_btn.setVisible(False)
        if not name:
            self.publish_feedback.set_message("Өнім атауын енгізіңіз.", "error")
            return
        if discount_price > regular_price:
            self.publish_feedback.set_message(
                "Жеңілдік бағасы бастапқы бағадан аспауы керек.",
                "error",
            )
            return

        local_dt = self.expires_input.dateTime().toPython().astimezone()
        if local_dt <= datetime.now(timezone.utc):
            self.publish_feedback.set_message(
                "Жарамдылық мерзімі болашақ уақытты көрсетуі керек.",
                "error",
            )
            return

        self.publish_btn.setDisabled(True)
        self.publish_feedback.clear()
        try:
            result = self.api.publish_batch(
                product_name=name,
                unit=unit,
                description=description or None,
                quantity=format_decimal_api(qty, places=3),
                regular_price=format_decimal_api(regular_price, places=2),
                discount_price=format_decimal_api(discount_price, places=2),
                expires_at_iso=local_dt.astimezone(timezone.utc).isoformat(),
            )
        except ApiError as exc:
            self.publish_btn.setDisabled(False)
            self.publish_feedback.set_message(translate_api_error(exc), "error")
            return

        self.publish_btn.setDisabled(False)
        self.published_product_name = result["product"]["name"]
        self.product_name_input.clear()
        self.product_desc_input.clear()
        self._reset_default_expiry()
        self.publish_feedback.set_message(
            f"«{self.published_product_name}» каталогта жарияланды.",
            "success",
        )
        self.view_published_btn.setVisible(True)

    def _open_published_in_catalog(self) -> None:
        if self.published_product_name:
            self.on_view_published(self.published_product_name)

    def _clear_orders_widgets(self) -> None:
        while self.orders_container.count():
            item = self.orders_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def load_orders(self, *, append: bool = False) -> list[dict[str, Any]]:
        if not self.api.user or self.api.user.get("role") != "seller":
            return []
        start = self.orders_offset if append else 0
        self.orders_refresh_btn.setDisabled(True)
        self.orders_more_btn.setDisabled(True)
        if not self.orders or not append:
            self.orders_state.set_message("Тапсырыстар жүктелуде…", "")

        try:
            page = self.api.list_seller_orders(limit=ORDERS_PAGE_SIZE, offset=start)
        except ApiError as exc:
            self.orders_refresh_btn.setDisabled(False)
            self.orders_more_btn.setDisabled(False)
            if exc.status_code in {403, 404}:
                self.orders = []
                self.orders_offset = 0
                self.orders_has_more = False
                self._render_orders()
            self.orders_state.set_message(translate_api_error(exc), "error")
            return self.orders

        merged: dict[str, dict[str, Any]] = {
            str(o["id"]): o for o in (self.orders if append else [])
        }
        for order in page:
            merged[str(order["id"])] = order
        self.orders = list(merged.values())
        self.orders_offset = start + len(page)
        self.orders_has_more = len(page) == ORDERS_PAGE_SIZE
        self._render_orders()

        if self.orders:
            self.orders_state.clear()
        else:
            self.orders_state.set_message("Әзірге тапсырыстар жоқ.", "")

        self.orders_refresh_btn.setDisabled(False)
        self.orders_more_btn.setVisible(self.orders_has_more)
        self.orders_more_btn.setDisabled(False)
        return self.orders

    def _render_orders(self) -> None:
        self._clear_orders_widgets()
        for order in self.orders:
            card = QFrame()
            card.setObjectName("orderCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)

            order_id = str(order["id"])
            short_num = order_id[:8]
            status = order["status"]
            currency = order.get("currency", "KZT")

            head = QHBoxLayout()
            title = QLabel(f"Тапсырыс №{short_num}")
            title.setObjectName("productTitle")
            pill = QLabel(order_status_label(status))
            pill.setObjectName("statusPill")
            pill.setProperty("orderStatus", status)
            repolish(pill)
            head.addWidget(title)
            head.addStretch(1)
            head.addWidget(pill)
            layout.addLayout(head)

            meta = QLabel(
                f"{format_datetime(order['created_at'])} · "
                f"Жалпы сома: {format_money(order['total_amount'], currency)}"
            )
            meta.setObjectName("mutedText")
            layout.addWidget(meta)

            for item in order.get("items", []):
                batch_short = str(item["batch_id"])[:8]
                line = QLabel(
                    f"• Партия №{batch_short} · Саны: {format_quantity(item['quantity'])} · "
                    f"Бірлік бағасы: {format_money(item['unit_price'], currency)}"
                )
                line.setWordWrap(True)
                layout.addWidget(line)

            if status == "reserved":
                accept_btn = QPushButton("Растау")
                accept_btn.setProperty("variant", "primary")
                accept_btn.setDisabled(order_id in self.confirming_ids)
                accept_btn.setObjectName(f"acceptOrder_{order_id}")
                accept_btn.clicked.connect(lambda _=False, oid=order_id: self._accept_order(oid))
                layout.addWidget(accept_btn, alignment=Qt.AlignmentFlag.AlignLeft)

            self.orders_container.addWidget(card)

    def _accept_order(self, order_id: str) -> None:
        if order_id in self.confirming_ids:
            return
        self.confirming_ids.add(order_id)
        self.orders_action_feedback.clear()
        self._render_orders()

        try:
            updated = self.api.accept_seller_order(order_id)
        except ApiError as exc:
            self.confirming_ids.discard(order_id)
            self.orders_action_feedback.set_message(translate_api_error(exc), "error")
            if exc.status_code in {404, 409}:
                self.load_orders(append=False)
            else:
                self._render_orders()
            return

        self.confirming_ids.discard(order_id)
        for order in self.orders:
            if str(order["id"]) == order_id:
                order["status"] = updated["status"]
        self._render_orders()
        self.orders_action_feedback.set_message(
            f"Тапсырыс №{order_id[:8]} расталды.",
            "success",
        )
