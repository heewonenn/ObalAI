from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .dialogs import BookingAttempt, BookingDraft
from .formatting import (
    UNIT_LABELS,
    discount_percent,
    format_datetime,
    format_money,
    format_quantity,
    to_decimal,
    unit_label,
)
from .widgets import FeedbackBanner, HeroImageWidget, SiteFooter, repolish


PAGE_SIZE = 24

SORT_OPTIONS: list[tuple[str, str]] = [
    ("expires_asc", "Мерзімі жақын"),
    ("price_asc", "Ең арзан"),
    ("price_desc", "Ең қымбат"),
    ("discount_desc", "Жеңілдігі жоғары"),
]


class ProductCard(QFrame):
    """Single offer card with booking, favorite toggle, detail, and WSM compare actions."""

    def __init__(
        self,
        batch: dict[str, Any],
        *,
        user: dict[str, Any] | None,
        is_favorite: bool,
        in_compare: bool,
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        on_open_detail: Callable[[dict[str, Any]], None],
        on_toggle_favorite: Callable[[str], None],
        on_toggle_compare: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("productCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(310)
        self.batch = batch
        batch_id = str(batch["batch_id"])

        product = batch["product"]
        store = batch["store"]
        unit_text = unit_label(product["unit"])
        pct = discount_percent(batch["regular_price"], batch["discount_price"])
        currency = batch.get("currency", "KZT")

        draft = BookingDraft(
            batch_id=batch_id,
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
        header_layout.setContentsMargins(16, 9, 12, 9)
        header_layout.setSpacing(8)
        unit_badge = QLabel(unit_text)
        unit_badge.setObjectName("unitBadge")
        header_layout.addWidget(unit_badge)
        header_layout.addStretch(1)
        if pct > 0:
            disc_badge = QLabel(f"−{pct}%")
            disc_badge.setObjectName("discountBadge")
            header_layout.addWidget(disc_badge)

        role = user.get("role") if user else None
        self.fav_button: QPushButton | None = None
        if role == "buyer":
            fav_btn = QPushButton("★" if is_favorite else "☆")
            fav_btn.setObjectName("favButton")
            fav_btn.setProperty("saved", "true" if is_favorite else "false")
            fav_btn.setToolTip("Таңдаулылардан алу" if is_favorite else "Таңдаулыларға қосу")
            repolish(fav_btn)
            fav_btn.clicked.connect(lambda _=False, bid=batch_id: on_toggle_favorite(bid))
            header_layout.addWidget(fav_btn)
            self.fav_button = fav_btn

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

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        self.detail_button = QPushButton("Толығырақ")
        self.detail_button.setObjectName("cardSecondaryBtn")
        self.detail_button.clicked.connect(lambda _=False, b=batch: on_open_detail(b))

        self.compare_button = QPushButton("✓ Салыстыруда" if in_compare else "Салыстыру")
        self.compare_button.setObjectName("cardSecondaryBtn")
        self.compare_button.setProperty("selected", "true" if in_compare else "false")
        repolish(self.compare_button)
        self.compare_button.clicked.connect(lambda _=False, bid=batch_id: on_toggle_compare(bid))

        secondary_row.addWidget(self.detail_button, stretch=1)
        secondary_row.addWidget(self.compare_button, stretch=1)
        body_layout.addLayout(secondary_row)

        outer.addWidget(body)


class CatalogView(QWidget):
    """Editorial hero + catalog with filters, sorting, favorites, and WSM comparison."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        on_retry_pending: Callable[[], None],
        on_open_seller: Callable[[], None],
        on_open_detail: Callable[[dict[str, Any]], None],
        on_open_compare: Callable[[list[str]], None],
        on_toggle_favorite: Callable[[str], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.on_book = on_book
        self.on_switch_to_buyer = on_switch_to_buyer
        self.on_retry_pending = on_retry_pending
        self.on_open_seller = on_open_seller
        self.on_open_detail = on_open_detail
        self.on_open_compare = on_open_compare
        self.on_toggle_favorite = on_toggle_favorite

        self.batches: list[dict[str, Any]] = []
        self.favorite_ids: set[str] = set()
        self.compare_ids: list[str] = []
        self.favorites_only = False
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
        root.setSpacing(24)

        # --- HERO BANNER ---
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setMinimumHeight(350)
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
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
        hero_title.setMinimumHeight(108)
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
        offers_layout.setContentsMargins(0, 10, 0, 8)
        offers_layout.setSpacing(14)

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
        self.search_input.setMinimumWidth(240)
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

        # --- FILTER & SORT BAR ---
        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        fb_layout = QHBoxLayout(filter_bar)
        fb_layout.setContentsMargins(14, 10, 14, 10)
        fb_layout.setSpacing(10)

        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("Қала (барлығы)")
        self.city_input.setMaxLength(120)
        self.city_input.setMaximumWidth(160)
        self.city_input.returnPressed.connect(lambda: self.load_catalog(append=False))
        fb_layout.addWidget(self.city_input)

        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Барлық бірлік", None)
        for value, label in UNIT_LABELS:
            self.unit_combo.addItem(label, value)
        self.unit_combo.currentIndexChanged.connect(lambda: self.load_catalog(append=False))
        fb_layout.addWidget(self.unit_combo)

        self.max_price_input = QLineEdit()
        self.max_price_input.setPlaceholderText("Макс. баға, ₸")
        self.max_price_input.setMaximumWidth(130)
        self.max_price_input.returnPressed.connect(lambda: self.load_catalog(append=False))
        fb_layout.addWidget(self.max_price_input)

        self.sort_combo = QComboBox()
        for value, label in SORT_OPTIONS:
            self.sort_combo.addItem(label, value)
        self.sort_combo.currentIndexChanged.connect(lambda: self.load_catalog(append=False))
        fb_layout.addWidget(self.sort_combo)

        self.favorites_filter_btn = QPushButton("★ Таңдаулылар")
        self.favorites_filter_btn.setObjectName("favoritesFilterBtn")
        self.favorites_filter_btn.setProperty("checked", "false")
        self.favorites_filter_btn.setVisible(False)
        self.favorites_filter_btn.clicked.connect(self._toggle_favorites_only)
        fb_layout.addWidget(self.favorites_filter_btn)

        fb_layout.addStretch(1)

        self.apply_filters_btn = QPushButton("Сүзгілеу")
        self.apply_filters_btn.clicked.connect(lambda: self.load_catalog(append=False))
        fb_layout.addWidget(self.apply_filters_btn)

        self.reset_filters_btn = QPushButton("Тазарту")
        self.reset_filters_btn.setProperty("variant", "link")
        self.reset_filters_btn.clicked.connect(self._reset_filters)
        fb_layout.addWidget(self.reset_filters_btn)

        offers_layout.addWidget(filter_bar)

        # --- WSM COMPARE BAR ---
        self.compare_bar = QFrame()
        self.compare_bar.setObjectName("compareBar")
        cb_layout = QHBoxLayout(self.compare_bar)
        cb_layout.setContentsMargins(16, 10, 16, 10)
        cb_layout.setSpacing(10)
        self.compare_label = QLabel()
        self.compare_label.setObjectName("unitBadge")
        self.compare_run_btn = QPushButton("WSM салыстыру")
        self.compare_run_btn.setProperty("variant", "primary")
        self.compare_run_btn.clicked.connect(self._open_wsm_compare)
        self.compare_clear_btn = QPushButton("Тазалау")
        self.compare_clear_btn.clicked.connect(self.clear_compare)
        cb_layout.addWidget(self.compare_label)
        cb_layout.addStretch(1)
        cb_layout.addWidget(self.compare_run_btn)
        cb_layout.addWidget(self.compare_clear_btn)
        self.compare_bar.setVisible(False)
        offers_layout.addWidget(self.compare_bar)

        # --- BUYER AI RECOMMENDATIONS PANEL ---
        self.ai_panel = QFrame()
        self.ai_panel.setObjectName("aiPanel")
        ai_layout = QVBoxLayout(self.ai_panel)
        ai_layout.setContentsMargins(18, 16, 18, 16)
        ai_layout.setSpacing(10)

        ai_header = QHBoxLayout()
        ai_title_col = QVBoxLayout()
        ai_title_col.setSpacing(2)
        ai_title = QLabel("Жеке AI ұсыныстар")
        ai_title.setObjectName("sectionTitle")
        self.ai_meta_label = QLabel()
        self.ai_meta_label.setObjectName("mutedText")
        self.ai_meta_label.setWordWrap(True)
        ai_title_col.addWidget(ai_title)
        ai_title_col.addWidget(self.ai_meta_label)
        ai_header.addLayout(ai_title_col, stretch=1)

        self.ai_refresh_btn = QPushButton("Жаңарту")
        self.ai_refresh_btn.clicked.connect(self.load_ai_recommendations)
        ai_header.addWidget(self.ai_refresh_btn)
        ai_layout.addLayout(ai_header)

        self.ai_feedback = FeedbackBanner()
        ai_layout.addWidget(self.ai_feedback)

        self.ai_cards_layout = QHBoxLayout()
        self.ai_cards_layout.setSpacing(12)
        ai_layout.addLayout(self.ai_cards_layout)

        self.ai_panel.setVisible(False)
        self.last_ai_response: dict[str, Any] | None = None
        offers_layout.addWidget(self.ai_panel)

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
        root.addWidget(SiteFooter())
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        page_wrap.setAlignment(Qt.AlignmentFlag.AlignTop)
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

    def set_favorites(self, fav_ids: set[str]) -> None:
        self.favorite_ids = set(fav_ids)
        is_buyer = self.api.user is not None and self.api.user.get("role") == "buyer"
        self.favorites_filter_btn.setVisible(is_buyer)
        if not is_buyer and self.favorites_only:
            self.favorites_only = False
            self.favorites_filter_btn.setProperty("checked", "false")
            repolish(self.favorites_filter_btn)
        if self.batches:
            self._render_cards()

    def _toggle_favorites_only(self) -> None:
        self.favorites_only = not self.favorites_only
        self.favorites_filter_btn.setProperty("checked", "true" if self.favorites_only else "false")
        repolish(self.favorites_filter_btn)
        self.load_catalog(append=False)

    def _handle_card_favorite(self, batch_id: str) -> None:
        saved = self.on_toggle_favorite(batch_id)
        if saved:
            self.favorite_ids.add(batch_id)
        else:
            self.favorite_ids.discard(batch_id)
        if self.favorites_only and not saved:
            self.load_catalog(append=False)
        else:
            self._render_cards()

    def _toggle_compare(self, batch_id: str) -> None:
        if batch_id in self.compare_ids:
            self.compare_ids.remove(batch_id)
        elif len(self.compare_ids) < 10:
            self.compare_ids.append(batch_id)
        self._update_compare_bar()
        self._render_cards()

    def clear_compare(self) -> None:
        self.compare_ids.clear()
        self._update_compare_bar()
        self._render_cards()

    def _update_compare_bar(self) -> None:
        count = len(self.compare_ids)
        self.compare_bar.setVisible(count > 0)
        if count == 1:
            self.compare_label.setText("Салыстыруға 1 партия таңдалды — тағы кемінде 1 партия таңдаңыз.")
            self.compare_run_btn.setDisabled(True)
        else:
            self.compare_label.setText(f"WSM салыстыруға таңдалды: {count} партия")
            self.compare_run_btn.setDisabled(False)

    def _open_wsm_compare(self) -> None:
        if len(self.compare_ids) >= 2:
            self.on_open_compare(list(self.compare_ids))

    def _clear_search(self) -> None:
        self.search_input.clear()
        self.load_catalog(append=False)
        self.search_input.setFocus()

    def _reset_filters(self) -> None:
        self.search_input.clear()
        self.city_input.clear()
        self.max_price_input.clear()
        self.unit_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(0)
        self.unit_combo.blockSignals(False)
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.blockSignals(False)
        self.favorites_only = False
        self.favorites_filter_btn.setProperty("checked", "false")
        repolish(self.favorites_filter_btn)
        self.load_catalog(append=False)

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

    def _clear_ai_cards(self) -> None:
        while self.ai_cards_layout.count():
            item = self.ai_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def load_ai_recommendations(self) -> dict[str, Any] | None:
        is_buyer = self.api.user is not None and self.api.user.get("role") == "buyer" and bool(self.api.token)
        self.ai_panel.setVisible(is_buyer)
        self._clear_ai_cards()
        if not is_buyer:
            self.last_ai_response = None
            return None

        self.ai_feedback.set_message("AI ұсыныстары есептелуде…", "")
        try:
            data = self.api.get_buyer_recommendations(limit=3)
        except ApiError as exc:
            self.ai_feedback.set_message(translate_api_error(exc), "error")
            return None

        self.last_ai_response = data
        self.ai_meta_label.setText(
            f"Модель: {data.get('model_version', '')} · "
            f"Нақты әрекеттер: {data.get('current_interactions', 0)}/{data.get('required_interactions', 3)} · "
            f"Baseline: {data.get('baseline_used', '')}"
        )

        if data.get("status") != "ok":
            self.ai_feedback.set_message(
                data.get("reason")
                or "Жеке AI ұсыныстары үшін деректер жеткіліксіз (insufficient_data).",
                "",
            )
            return data

        self.ai_feedback.clear()
        for rec in data.get("items", []):
            batch = rec["batch"]
            product = batch["product"]
            store = batch["store"]
            pct = discount_percent(batch["regular_price"], batch["discount_price"])
            unit_text = unit_label(product["unit"])

            card = QFrame()
            card.setObjectName("aiCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 14)
            cl.setSpacing(6)

            top = QHBoxLayout()
            badge = QLabel(f"AI · {rec['score']:.2f}")
            badge.setObjectName("aiBadge")
            top.addWidget(badge)
            if pct > 0:
                disc_lbl = QLabel(f"−{pct}%")
                disc_lbl.setObjectName("discountBadge")
                top.addWidget(disc_lbl)
            top.addStretch(1)
            cl.addLayout(top)

            title = QLabel(product["name"])
            title.setObjectName("productTitle")
            title.setWordWrap(True)
            cl.addWidget(title)

            meta = QLabel(
                f"{store['name']} · {format_money(batch['discount_price'], batch.get('currency', 'KZT'))} · "
                f"{format_quantity(batch['quantity_available'])} {unit_text}"
            )
            meta.setObjectName("mutedText")
            meta.setWordWrap(True)
            cl.addWidget(meta)

            expl = QLabel(rec.get("explanation", ""))
            expl.setObjectName("mutedText")
            expl.setWordWrap(True)
            cl.addWidget(expl)

            cl.addStretch(1)
            draft = BookingDraft(
                batch_id=str(batch["batch_id"]),
                name=product["name"],
                unit=product["unit"],
                available=to_decimal(batch["quantity_available"]),
            )
            book_btn = QPushButton("Брондау")
            book_btn.setProperty("variant", "primary")
            book_btn.clicked.connect(lambda _=False, d=draft: self.on_book(d))
            cl.addWidget(book_btn)

            self.ai_cards_layout.addWidget(card, stretch=1)

        return data

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
            bid = str(batch["batch_id"])
            card = ProductCard(
                batch,
                user=self.api.user,
                is_favorite=bid in self.favorite_ids,
                in_compare=bid in self.compare_ids,
                on_book=self.on_book,
                on_switch_to_buyer=self.on_switch_to_buyer,
                on_open_detail=self.on_open_detail,
                on_toggle_favorite=self._handle_card_favorite,
                on_toggle_compare=self._toggle_compare,
            )
            row, col = divmod(index, cols)
            self.grid.addWidget(card, row, col)
        for col in range(cols):
            self.grid.setColumnStretch(col, 1)

    def refresh_card_actions(self) -> None:
        is_buyer = self.api.user is not None and self.api.user.get("role") == "buyer"
        self.favorites_filter_btn.setVisible(is_buyer)
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

        max_price_raw = self.max_price_input.text().strip().replace(",", ".")
        if max_price_raw:
            try:
                if float(max_price_raw) < 0:
                    raise ValueError
            except ValueError:
                self.state_banner.set_message("Максималды баға дұрыс сан болуы керек.", "error")
                return self.batches

        try:
            if self.favorites_only and self.api.user and self.api.user.get("role") == "buyer":
                fav_items = self.api.list_favorites()
                page = [item["batch"] for item in fav_items if item.get("is_available")]
                has_more = False
            else:
                page = self.api.list_catalog(
                    q=self.current_query,
                    city=self.city_input.text().strip(),
                    unit=self.unit_combo.currentData(),
                    max_price=max_price_raw or None,
                    sort=self.sort_combo.currentData() or "expires_asc",
                    limit=PAGE_SIZE,
                    offset=self.offset,
                )
                has_more = len(page) == PAGE_SIZE
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
            if self.favorites_only:
                empty_text = "Таңдаулыларда қолжетімді партиялар жоқ."
            elif self.current_query or self.city_input.text().strip() or self.unit_combo.currentData() or max_price_raw:
                empty_text = "Сүзгі немесе іздеу бойынша нәтиже табылмады."
            else:
                empty_text = "Қазір қолжетімді партиялар жоқ."
            self.empty_title.setText(empty_text)
            self.empty_action.setVisible(not self.favorites_only and not self.current_query)
            self.empty_card.setVisible(True)

        self.more_button.setVisible(has_more)
        return self.batches
