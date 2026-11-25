from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .dialogs import BookingAttempt, BookingDraft
from .formatting import (
    discount_percent,
    format_datetime,
    format_money,
    format_quantity,
    to_decimal,
    unit_label,
)
from .widgets import FeedbackBanner


PAGE_SIZE = 24


class ProductCard(QFrame):
    """Single offer card in the public catalog."""

    def __init__(
        self,
        batch: dict[str, Any],
        *,
        user: dict[str, Any] | None,
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("productCard")
        self.batch = batch

        product = batch["product"]
        store = batch["store"]
        unit_text = unit_label(product["unit"])
        pct = discount_percent(batch["regular_price"], batch["discount_price"])
        currency = batch.get("currency", "KZT")

        draft = BookingDraft(
            batch_id=str(batch["batch_id"]),
            name=product["name"],
            unit=product["unit"],
            available=to_decimal(batch["quantity_available"]),
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("productCardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 9, 14, 9)
        unit_badge = QLabel(unit_text)
        unit_badge.setObjectName("unitBadge")
        header_layout.addWidget(unit_badge)
        header_layout.addStretch(1)
        if pct > 0:
            disc_badge = QLabel(f"−{pct}%")
            disc_badge.setObjectName("discountBadge")
            header_layout.addWidget(disc_badge)
        outer.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 16)
        body_layout.setSpacing(6)

        title = QLabel(product["name"])
        title.setObjectName("productTitle")
        title.setWordWrap(True)
        body_layout.addWidget(title)

        if product.get("description"):
            desc = QLabel(product["description"])
            desc.setWordWrap(True)
            body_layout.addWidget(desc)

        meta = QLabel(f"{store['name']} · {store['city']}")
        meta.setObjectName("mutedText")
        meta.setWordWrap(True)
        body_layout.addWidget(meta)

        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        price_label = QLabel(format_money(batch["discount_price"], currency))
        price_label.setObjectName("priceLabel")
        price_row.addWidget(price_label)
        if to_decimal(batch["regular_price"]) > to_decimal(batch["discount_price"]):
            old_price = QLabel(format_money(batch["regular_price"], currency))
            old_price.setObjectName("oldPriceLabel")
            price_row.addWidget(old_price)
        price_row.addStretch(1)
        body_layout.addLayout(price_row)

        stock_label = QLabel(f"Қалдығы: {format_quantity(batch['quantity_available'])} {unit_text}")
        stock_label.setObjectName("mutedText")
        expiry_label = QLabel(f"Жарамды: {format_datetime(batch['expires_at'])}")
        expiry_label.setObjectName("mutedText")
        body_layout.addWidget(stock_label)
        body_layout.addWidget(expiry_label)

        body_layout.addStretch(1)

        role = user.get("role") if user else None
        if role == "seller":
            hint = QLabel("Брондау тек сатып алушыларға қолжетімді.")
            hint.setObjectName("sellerBookingHint")
            hint.setWordWrap(True)
            body_layout.addWidget(hint)

            self.action_button = QPushButton("Сатып алушы ретінде кіру")
            self.action_button.clicked.connect(lambda: on_switch_to_buyer(draft))
            body_layout.addWidget(self.action_button)
        else:
            self.action_button = QPushButton("Брондау")
            self.action_button.setProperty("variant", "primary")
            self.action_button.clicked.connect(lambda: on_book(draft))
            body_layout.addWidget(self.action_button)

        outer.addWidget(body)


class CatalogView(QWidget):
    """Public catalog screen with search, pagination, and booking entry points."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        on_retry_pending: Callable[[], None],
        on_open_seller: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_book = on_book
        self.on_switch_to_buyer = on_switch_to_buyer
        self.on_retry_pending = on_retry_pending
        self.on_open_seller = on_open_seller

        self.batches: list[dict[str, Any]] = []
        self.offset = 0
        self.current_query = ""
        self._last_columns = 3

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Қолжетімді өнімдер")
        title.setObjectName("pageTitle")
        self.count_label = QLabel()
        self.count_label.setObjectName("mutedText")
        self.count_label.setVisible(False)
        title_col.addWidget(title)
        title_col.addWidget(self.count_label)
        top_row.addLayout(title_col)
        top_row.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Өнімді іздеу")
        self.search_input.setMaxLength(180)
        self.search_input.setMinimumWidth(240)
        self.search_input.returnPressed.connect(lambda: self.load_catalog(append=False))
        top_row.addWidget(self.search_input)

        self.clear_button = QPushButton("Тазалау")
        self.clear_button.setVisible(False)
        self.clear_button.clicked.connect(self._clear_search)
        top_row.addWidget(self.clear_button)

        self.search_button = QPushButton("Іздеу")
        self.search_button.setProperty("variant", "dark")
        self.search_button.clicked.connect(lambda: self.load_catalog(append=False))
        top_row.addWidget(self.search_button)

        self.refresh_button = QPushButton("Жаңарту")
        self.refresh_button.clicked.connect(lambda: self.load_catalog(append=False))
        top_row.addWidget(self.refresh_button)

        root.addLayout(top_row)

        self.booking_feedback = FeedbackBanner()
        root.addWidget(self.booking_feedback)

        self.pending_bar = QFrame()
        self.pending_bar.setObjectName("feedbackBanner")
        pending_layout = QHBoxLayout(self.pending_bar)
        pending_layout.setContentsMargins(12, 8, 12, 8)
        pending_text = QLabel("Алдыңғы броньдың нәтижесі әзірге белгісіз.")
        pending_text.setObjectName("feedbackLabel")
        self.pending_retry_button = QPushButton("Броньды тексеру")
        self.pending_retry_button.clicked.connect(self.on_retry_pending)
        pending_layout.addWidget(pending_text)
        pending_layout.addStretch(1)
        pending_layout.addWidget(self.pending_retry_button)
        self.pending_bar.setVisible(False)
        root.addWidget(self.pending_bar)

        self.state_banner = FeedbackBanner()
        root.addWidget(self.state_banner)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(16)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_layout.addLayout(self.grid)

        self.more_button = QPushButton("Тағы көрсету")
        self.more_button.setVisible(False)
        self.more_button.clicked.connect(lambda: self.load_catalog(append=True))
        scroll_layout.addWidget(self.more_button, alignment=Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addStretch(1)

        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, stretch=1)

    def set_search_query(self, text: str) -> None:
        self.search_input.setText(text)

    def set_booking_feedback(self, message: str = "", tone: str = "") -> None:
        self.booking_feedback.set_message(message, tone)

    def set_pending_attempt(self, attempt: BookingAttempt | None) -> None:
        self.pending_bar.setVisible(attempt is not None)

    def _clear_search(self) -> None:
        self.search_input.clear()
        self.load_catalog(append=False)
        self.search_input.setFocus()

    def _column_count(self) -> int:
        width = self.width()
        if width < 640:
            return 1
        if width < 980:
            return 2
        return 3

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cols = self._column_count()
        if cols != self._last_columns and self.batches:
            self._render_cards()

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _render_cards(self) -> None:
        self._clear_grid()
        cols = self._column_count()
        self._last_columns = cols
        for index, batch in enumerate(self.batches):
            card = ProductCard(
                batch,
                user=self.api.user,
                on_book=self.on_book,
                on_switch_to_buyer=self.on_switch_to_buyer,
            )
            row, col = divmod(index, cols)
            self.grid.addWidget(card, row, col)
        for col in range(cols):
            self.grid.setColumnStretch(col, 1)

    def refresh_card_actions(self) -> None:
        if self.batches:
            self._render_cards()

    def find_batch(self, batch_id: str) -> dict[str, Any] | None:
        for batch in self.batches:
            if str(batch["batch_id"]) == str(batch_id):
                return batch
        return None

    def load_catalog(self, *, append: bool = False) -> list[dict[str, Any]]:
        if not append:
            self.offset = 0
            self.current_query = self.search_input.text().strip()
            self.batches = []
            self._clear_grid()
            self.count_label.setVisible(False)
        self.clear_button.setVisible(bool(self.current_query))
        self.more_button.setVisible(False)
        self.state_banner.set_message("Каталог жүктелуде…", "")

        try:
            page = self.api.list_catalog(
                q=self.current_query,
                limit=PAGE_SIZE,
                offset=self.offset,
            )
        except ApiError as exc:
            self.state_banner.set_message(translate_api_error(exc), "error")
            if append:
                self.more_button.setVisible(True)
            return self.batches

        self.batches.extend(page)
        self.offset += len(page)
        self._render_cards()

        if self.batches:
            self.count_label.setText(f"{len(self.batches)} ұсыныс")
            self.count_label.setVisible(True)
            self.state_banner.clear()
        else:
            self.count_label.setVisible(False)
            empty_text = (
                "Іздеу нәтижесі табылмады."
                if self.current_query
                else "Қазір қолжетімді партиялар жоқ."
            )
            self.state_banner.set_message(empty_text, "")

        self.more_button.setVisible(len(page) == PAGE_SIZE)
        return self.batches
