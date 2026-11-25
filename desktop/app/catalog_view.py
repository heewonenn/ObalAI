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
from .widgets import FeedbackBanner, HeroImageWidget, SiteFooter


PAGE_SIZE = 24


class ProductCard(QFrame):
    """Single offer card matching the ObalAi editorial design."""

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
        header_layout.setContentsMargins(16, 10, 16, 10)
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
        body_layout.setContentsMargins(18, 16, 18, 18)
        body_layout.setSpacing(7)

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
        price_row.setContentsMargins(0, 6, 0, 2)
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
    """Editorial hero + public catalog screen with search, cards, and footer."""

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)

        page = QWidget()
        page_wrap = QHBoxLayout(page)
        page_wrap.setContentsMargins(32, 24, 32, 24)

        inner = QWidget()
        inner.setMaximumWidth(1160)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(26)

        # --- HERO BANNER (matching ObalAi site design) ---
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(0)

        hero_copy = QWidget()
        copy_layout = QVBoxLayout(hero_copy)
        copy_layout.setContentsMargins(46, 44, 38, 44)
        copy_layout.setSpacing(16)

        eyebrow_row = QHBoxLayout()
        eyebrow_row.setSpacing(8)
        dot = QLabel()
        dot.setObjectName("eyebrowDot")
        dot.setFixedSize(8, 8)
        eyebrow = QLabel("ЖЕРГІЛІКТІ АЗЫҚ-ТҮЛІК")
        eyebrow.setObjectName("eyebrowLabel")
        eyebrow_row.addWidget(dot)
        eyebrow_row.addWidget(eyebrow)
        eyebrow_row.addStretch(1)
        copy_layout.addLayout(eyebrow_row)

        hero_title = QLabel(
            'Жақсы тағамға<br><span style="font-style:italic;color:#244a31;">екінші мүмкіндік</span>'
        )
        hero_title.setObjectName("heroTitle")
        hero_title.setTextFormat(Qt.TextFormat.RichText)
        hero_title.setWordWrap(True)
        copy_layout.addWidget(hero_title)

        hero_desc = QLabel(
            "Жергілікті дүкендер мен дәмханалардың жеңілдікпен ұсынған өнімдерін табыңыз."
        )
        hero_desc.setObjectName("heroDescription")
        hero_desc.setWordWrap(True)
        copy_layout.addWidget(hero_desc)

        hero_actions = QHBoxLayout()
        hero_actions.setSpacing(12)
        browse_btn = QPushButton("Каталогты қарау  ↓")
        browse_btn.setProperty("variant", "primary")
        browse_btn.clicked.connect(self._scroll_to_offers)

        add_batch_btn = QPushButton("Партия қосу  ↗")
        add_batch_btn.setProperty("variant", "link")
        add_batch_btn.clicked.connect(self.on_open_seller)

        hero_actions.addWidget(browse_btn)
        hero_actions.addWidget(add_batch_btn)
        hero_actions.addStretch(1)
        copy_layout.addSpacing(4)
        copy_layout.addLayout(hero_actions)
        copy_layout.addStretch(1)

        self.hero_image = HeroImageWidget()
        hero_layout.addWidget(hero_copy, stretch=10)
        hero_layout.addWidget(self.hero_image, stretch=11)
        root.addWidget(hero)

        # --- CATALOG SECTION ---
        self.offers_section = QWidget()
        offers_layout = QVBoxLayout(self.offers_section)
        offers_layout.setContentsMargins(0, 12, 0, 8)
        offers_layout.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
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
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Өнімді іздеу")
        self.search_input.setMaxLength(180)
        self.search_input.setMinimumWidth(250)
        self.search_input.returnPressed.connect(lambda: self.load_catalog(append=False))
        top_row.addWidget(self.search_input)

        self.clear_button = QPushButton("×")
        self.clear_button.setObjectName("iconPillButton")
        self.clear_button.setFixedSize(40, 40)
        self.clear_button.setToolTip("Іздеуді тазалау")
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

        offers_layout.addLayout(top_row)

        self.booking_feedback = FeedbackBanner()
        offers_layout.addWidget(self.booking_feedback)

        self.pending_bar = QFrame()
        self.pending_bar.setObjectName("feedbackBanner")
        pending_layout = QHBoxLayout(self.pending_bar)
        pending_layout.setContentsMargins(14, 10, 14, 10)
        pending_text = QLabel("Алдыңғы броньдың нәтижесі әзірге белгісіз.")
        pending_text.setObjectName("feedbackLabel")
        self.pending_retry_button = QPushButton("Броньды тексеру")
        self.pending_retry_button.clicked.connect(self.on_retry_pending)
        pending_layout.addWidget(pending_text)
        pending_layout.addStretch(1)
        pending_layout.addWidget(self.pending_retry_button)
        self.pending_bar.setVisible(False)
        offers_layout.addWidget(self.pending_bar)

        self.state_banner = FeedbackBanner()
        offers_layout.addWidget(self.state_banner)

        # Styled empty-state dashed card matching the site
        self.empty_card = QFrame()
        self.empty_card.setObjectName("emptyStateCard")
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(24, 34, 24, 34)
        empty_layout.setSpacing(10)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel("Қазір қолжетімді партиялар жоқ.")
        self.empty_title.setObjectName("mutedText")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_action = QPushButton("Партия қосу  ↗")
        self.empty_action.setProperty("variant", "link")
        self.empty_action.clicked.connect(self.on_open_seller)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_action, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_card.setVisible(False)
        offers_layout.addWidget(self.empty_card)

        self.grid = QGridLayout()
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        offers_layout.addLayout(self.grid)

        self.more_button = QPushButton("Тағы көрсету")
        self.more_button.setVisible(False)
        self.more_button.clicked.connect(lambda: self.load_catalog(append=True))
        offers_layout.addWidget(self.more_button, alignment=Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.offers_section)
        root.addStretch(1)
        root.addWidget(SiteFooter())

        page_wrap.addStretch(1)
        page_wrap.addWidget(inner, stretch=100)
        page_wrap.addStretch(1)
        self.scroll.setWidget(page)

    def _scroll_to_offers(self) -> None:
        self.scroll.ensureWidgetVisible(self.offers_section, 0, 24)
        bar = self.scroll.verticalScrollBar()
        bar.setValue(max(0, self.offers_section.y() - 16))

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
        if width < 680:
            return 1
        if width < 1020:
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
            self.empty_card.setVisible(False)
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
        self.state_banner.clear()

        if self.batches:
            self.count_label.setText(f"{len(self.batches)} ұсыныс")
            self.count_label.setVisible(True)
            self.empty_card.setVisible(False)
        else:
            self.count_label.setVisible(False)
            self.empty_title.setText(
                "Іздеу нәтижесі табылмады."
                if self.current_query
                else "Қазір қолжетімді партиялар жоқ."
            )
            self.empty_action.setVisible(not self.current_query)
            self.empty_card.setVisible(True)

        self.more_button.setVisible(len(page) == PAGE_SIZE)
        return self.batches
