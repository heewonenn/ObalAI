from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .formatting import (
    format_datetime,
    format_money,
    format_quantity,
    order_status_label,
    unit_label,
)
from .widgets import FeedbackBanner, FormSymbol, SiteFooter, repolish


ORDERS_PAGE_SIZE = 50


class BuyerOrdersView(QWidget):
    """Authenticated buyer's real reservation and order history."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_request_auth: Callable[[str, str], None],
        on_back_to_catalog: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_request_auth = on_request_auth
        self.on_back_to_catalog = on_back_to_catalog
        self.orders: list[dict[str, Any]] = []
        self.orders_offset = 0
        self.orders_has_more = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        page_wrap = QHBoxLayout(page)
        page_wrap.setContentsMargins(32, 24, 32, 24)

        content = QWidget()
        content.setMaximumWidth(1160)
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        if self.on_back_to_catalog is not None:
            back_btn = QPushButton("← Каталогқа оралу")
            back_btn.setProperty("variant", "link")
            back_btn.clicked.connect(self.on_back_to_catalog)
            root.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        heading = QLabel("Тапсырыстарым")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Броньдарыңыз бен тапсырыстарыңыздың өзекті күйін осы жерден қадағалаңыз.")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)

        self.gate_card = QFrame()
        self.gate_card.setObjectName("surfaceCard")
        self.gate_card.setMaximumWidth(700)
        gate_layout = QVBoxLayout(self.gate_card)
        gate_layout.setContentsMargins(26, 24, 26, 24)
        gate_layout.setSpacing(12)
        gate_layout.addWidget(FormSymbol("↗"))
        gate_title = QLabel("Сатып алушы аккаунты")
        gate_title.setObjectName("sectionTitle")
        self.gate_message = QLabel("Тапсырыстарды көру үшін сатып алушы ретінде кіріңіз.")
        self.gate_message.setObjectName("mutedText")
        self.gate_message.setWordWrap(True)
        gate_buttons = QHBoxLayout()
        self.gate_login_btn = QPushButton("Кіру")
        self.gate_login_btn.setProperty("variant", "primary")
        self.gate_login_btn.clicked.connect(lambda: self.on_request_auth("login", "buyer"))
        self.gate_register_btn = QPushButton("Сатып алушы болып тіркелу")
        self.gate_register_btn.clicked.connect(lambda: self.on_request_auth("register", "buyer"))
        gate_buttons.addWidget(self.gate_login_btn)
        gate_buttons.addWidget(self.gate_register_btn)
        gate_buttons.addStretch(1)
        gate_layout.addWidget(gate_title)
        gate_layout.addWidget(self.gate_message)
        gate_layout.addLayout(gate_buttons)
        root.addWidget(self.gate_card)

        self.workspace = QWidget()
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(12)

        orders_card = QFrame()
        orders_card.setObjectName("surfaceCard")
        orders_layout = QVBoxLayout(orders_card)
        orders_layout.setContentsMargins(20, 18, 20, 18)
        orders_layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Менің броньдарым")
        title.setObjectName("sectionTitle")
        self.refresh_btn = QPushButton("Жаңарту")
        self.refresh_btn.clicked.connect(lambda: self.load_orders(append=False))
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_btn)
        orders_layout.addLayout(header)

        self.state = FeedbackBanner()
        orders_layout.addWidget(self.state)
        self.orders_container = QVBoxLayout()
        self.orders_container.setSpacing(10)
        orders_layout.addLayout(self.orders_container)
        self.more_btn = QPushButton("Тағы көрсету")
        self.more_btn.setVisible(False)
        self.more_btn.clicked.connect(lambda: self.load_orders(append=True))
        orders_layout.addWidget(self.more_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        workspace_layout.addWidget(orders_card)
        root.addWidget(self.workspace)
        root.addStretch(1)
        root.addWidget(SiteFooter())

        page_wrap.addStretch(1)
        page_wrap.addWidget(content, stretch=100)
        page_wrap.addStretch(1)
        scroll.setWidget(page)
        outer.addWidget(scroll)

    def reset_state(self) -> None:
        self.orders = []
        self.orders_offset = 0
        self.orders_has_more = False
        self.state.clear()
        self._clear_order_widgets()

    def refresh(self) -> None:
        user = self.api.user
        is_buyer = user is not None and user.get("role") == "buyer"
        self.gate_card.setVisible(not is_buyer)
        self.workspace.setVisible(is_buyer)
        if not is_buyer:
            if user is not None:
                self.gate_message.setText("Тапсырыстарды көру үшін сатып алушы аккаунтымен кіріңіз.")
                self.gate_login_btn.setText("Сатып алушы ретінде кіру")
            else:
                self.gate_message.setText("Тапсырыстарды көру үшін сатып алушы ретінде кіріңіз.")
                self.gate_login_btn.setText("Кіру")
            return
        self.load_orders(append=False)

    def _clear_order_widgets(self) -> None:
        while self.orders_container.count():
            item = self.orders_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def load_orders(self, *, append: bool = False) -> list[dict[str, Any]]:
        if not self.api.user or self.api.user.get("role") != "buyer":
            return []
        offset = self.orders_offset if append else 0
        self.refresh_btn.setDisabled(True)
        self.more_btn.setDisabled(True)
        if not self.orders or not append:
            self.state.set_message("Тапсырыстар жүктелуде…", "")
        try:
            page = self.api.list_buyer_orders(limit=ORDERS_PAGE_SIZE, offset=offset)
        except ApiError as exc:
            self.refresh_btn.setDisabled(False)
            self.more_btn.setDisabled(False)
            self.state.set_message(translate_api_error(exc), "error")
            return self.orders

        merged = {str(order["id"]): order for order in (self.orders if append else [])}
        for order in page:
            merged[str(order["id"])] = order
        self.orders = list(merged.values())
        self.orders_offset = offset + len(page)
        self.orders_has_more = len(page) == ORDERS_PAGE_SIZE
        self._render_orders()
        if self.orders:
            self.state.clear()
        else:
            self.state.set_message("Әзірге тапсырыстар жоқ.", "")
        self.refresh_btn.setDisabled(False)
        self.more_btn.setVisible(self.orders_has_more)
        self.more_btn.setDisabled(False)
        return self.orders

    def _render_orders(self) -> None:
        self._clear_order_widgets()
        for order in self.orders:
            card = QFrame()
            card.setObjectName("orderCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)

            order_id = str(order["id"])
            currency = order.get("currency", "KZT")
            status = order["status"]
            head = QHBoxLayout()
            title = QLabel(f"Тапсырыс №{order_id[:8]}")
            title.setObjectName("productTitle")
            pill = QLabel(order_status_label(status))
            pill.setObjectName("statusPill")
            pill.setProperty("orderStatus", status)
            repolish(pill)
            head.addWidget(title)
            head.addStretch(1)
            head.addWidget(pill)
            layout.addLayout(head)

            store = order.get("store", {})
            store_text = " · ".join(
                value for value in (store.get("name"), store.get("city"), store.get("address")) if value
            )
            if store_text:
                store_label = QLabel(store_text)
                store_label.setObjectName("mutedText")
                store_label.setWordWrap(True)
                layout.addWidget(store_label)
            meta = QLabel(
                f"{format_datetime(order['created_at'])} · "
                f"Жалпы сома: {format_money(order['total_amount'], currency)}"
            )
            meta.setObjectName("mutedText")
            layout.addWidget(meta)
            for item in order.get("items", []):
                line = QLabel(
                    f"• {item.get('product_name', 'Өнім')} · "
                    f"{format_quantity(item['quantity'])} {unit_label(item.get('unit', 'piece'))} × "
                    f"{format_money(item['unit_price'], currency)} = "
                    f"{format_money(item['line_total'], currency)}"
                )
                line.setWordWrap(True)
                layout.addWidget(line)
            self.orders_container.addWidget(card)
