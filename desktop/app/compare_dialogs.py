from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .dialogs import BookingDraft
from .formatting import (
    discount_percent,
    format_datetime,
    format_money,
    format_quantity,
    to_decimal,
    unit_label,
)
from .widgets import FeedbackBanner, FormSymbol, repolish


class ProductDetailDialog(QDialog):
    """Detailed view of a single catalog batch with full store address and actions."""

    def __init__(
        self,
        batch: dict[str, Any],
        *,
        user: dict[str, Any] | None,
        is_favorite: bool,
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        on_toggle_favorite: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.batch = batch
        self.batch_id = str(batch["batch_id"])
        self.is_favorite = is_favorite
        self.on_toggle_favorite = on_toggle_favorite

        product = batch["product"]
        store = batch["store"]
        unit_text = unit_label(product["unit"])
        pct = discount_percent(batch["regular_price"], batch["discount_price"])
        currency = batch.get("currency", "KZT")

        draft = BookingDraft(
            batch_id=self.batch_id,
            name=product["name"],
            unit=product["unit"],
            available=to_decimal(batch["quantity_available"]),
        )

        self.setWindowTitle(f"ObalAi — {product['name']}")
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        top = QHBoxLayout()
        unit_badge = QLabel(unit_text)
        unit_badge.setObjectName("unitBadge")
        top.addWidget(unit_badge)
        if pct > 0:
            disc_badge = QLabel(f"−{pct}%")
            disc_badge.setObjectName("discountBadge")
            top.addWidget(disc_badge)
        top.addStretch(1)
        if user and user.get("role") == "buyer" and on_toggle_favorite is not None:
            self.fav_btn = QPushButton()
            self.fav_btn.setObjectName("favButton")
            self._sync_fav_button()
            self.fav_btn.clicked.connect(self._handle_fav_click)
            top.addWidget(self.fav_btn)
        root.addLayout(top)

        title = QLabel(product["name"])
        title.setObjectName("dialogTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        if product.get("description"):
            desc = QLabel(product["description"])
            desc.setWordWrap(True)
            root.addWidget(desc)

        price_row = QHBoxLayout()
        price_row.setSpacing(10)
        price_lbl = QLabel(format_money(batch["discount_price"], currency))
        price_lbl.setObjectName("priceLabel")
        price_row.addWidget(price_lbl)
        if to_decimal(batch["regular_price"]) > to_decimal(batch["discount_price"]):
            old_lbl = QLabel(format_money(batch["regular_price"], currency))
            old_lbl.setObjectName("oldPriceLabel")
            price_row.addWidget(old_lbl)
        price_row.addStretch(1)
        root.addLayout(price_row)

        info_box = QFrame()
        info_box.setObjectName("storeSummary")
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(6)
        info_layout.addWidget(QLabel(f"Дүкен: {store['name']}"))
        info_layout.addWidget(QLabel(f"Мекенжай: {store['city']}, {store['address']}"))
        info_layout.addWidget(QLabel(f"Қалдығы: {format_quantity(batch['quantity_available'])} {unit_text}"))
        info_layout.addWidget(QLabel(f"Жарамдылық мерзімі: {format_datetime(batch['expires_at'])}"))
        root.addWidget(info_box)

        role = user.get("role") if user else None
        actions = QHBoxLayout()
        actions.setSpacing(10)
        if role == "seller":
            hint = QLabel("Брондау тек сатып алушыларға қолжетімді.")
            hint.setObjectName("sellerBookingHint")
            hint.setWordWrap(True)
            root.addWidget(hint)
            switch_btn = QPushButton("Сатып алушы ретінде кіру")
            switch_btn.clicked.connect(lambda: (self.accept(), on_switch_to_buyer(draft)))
            actions.addWidget(switch_btn)
        else:
            book_btn = QPushButton("Брондау")
            book_btn.setProperty("variant", "primary")
            book_btn.clicked.connect(lambda: (self.accept(), on_book(draft)))
            actions.addWidget(book_btn)

        actions.addStretch(1)
        close_btn = QPushButton("Жабу")
        close_btn.clicked.connect(self.reject)
        actions.addWidget(close_btn)
        root.addLayout(actions)

    def _sync_fav_button(self) -> None:
        self.fav_btn.setText("★ Таңдаулыларда" if self.is_favorite else "☆ Таңдаулыларға")
        self.fav_btn.setProperty("saved", "true" if self.is_favorite else "false")
        repolish(self.fav_btn)

    def _handle_fav_click(self) -> None:
        if self.on_toggle_favorite is None:
            return
        self.is_favorite = self.on_toggle_favorite(self.batch_id)
        self._sync_fav_button()


class WsmCompareDialog(QDialog):
    """Weighted Sum Model (WSM) comparison dialog backed by POST /api/compare/wsm."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        batch_ids: list[str],
        on_book: Callable[[BookingDraft], None],
        on_switch_to_buyer: Callable[[BookingDraft], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.batch_ids = list(batch_ids)
        self.on_book = on_book
        self.on_switch_to_buyer = on_switch_to_buyer
        self.last_result: dict[str, Any] | None = None

        self.setWindowTitle("ObalAi — WSM салыстыру")
        self.setModal(True)
        self.resize(740, 620)
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(FormSymbol("⚖"))
        title = QLabel("Ұсыныстарды WSM салыстыру")
        title.setObjectName("dialogTitle")
        top.addWidget(title)
        top.addStretch(1)
        root.addLayout(top)

        # Weight controls
        weights_frame = QFrame()
        weights_frame.setObjectName("filterBar")
        wf_layout = QHBoxLayout(weights_frame)
        wf_layout.setContentsMargins(14, 10, 14, 10)
        wf_layout.setSpacing(12)

        wf_layout.addWidget(QLabel("Жеңілдік:"))
        self.w_discount = QSpinBox()
        self.w_discount.setRange(0, 100)
        self.w_discount.setValue(45)
        self.w_discount.setSuffix("%")
        wf_layout.addWidget(self.w_discount)

        wf_layout.addWidget(QLabel("Мерзім:"))
        self.w_freshness = QSpinBox()
        self.w_freshness.setRange(0, 100)
        self.w_freshness.setValue(35)
        self.w_freshness.setSuffix("%")
        wf_layout.addWidget(self.w_freshness)

        wf_layout.addWidget(QLabel("Баға:"))
        self.w_price = QSpinBox()
        self.w_price.setRange(0, 100)
        self.w_price.setValue(20)
        self.w_price.setSuffix("%")
        wf_layout.addWidget(self.w_price)

        wf_layout.addStretch(1)
        self.recalc_btn = QPushButton("Есептеу")
        self.recalc_btn.setProperty("variant", "dark")
        self.recalc_btn.clicked.connect(self.load_comparison)
        wf_layout.addWidget(self.recalc_btn)
        root.addWidget(weights_frame)

        self.meta_label = QLabel()
        self.meta_label.setObjectName("mutedText")
        self.meta_label.setWordWrap(True)
        root.addWidget(self.meta_label)

        self.feedback = FeedbackBanner()
        root.addWidget(self.feedback)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.results_host = QWidget()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 4, 0)
        self.results_layout.setSpacing(12)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.results_host)
        root.addWidget(scroll, stretch=1)

        close_btn = QPushButton("Жабу")
        close_btn.clicked.connect(self.reject)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.load_comparison()

    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def load_comparison(self) -> dict[str, Any] | None:
        total = self.w_discount.value() + self.w_freshness.value() + self.w_price.value()
        if total <= 0:
            self.feedback.set_message("Салмақтардың қосындысы 0-ден үлкен болуы керек.", "error")
            return None

        weights = {
            "discount": f"{self.w_discount.value() / total:.4f}",
            "freshness": f"{self.w_freshness.value() / total:.4f}",
            "price": f"{self.w_price.value() / total:.4f}",
        }
        self.recalc_btn.setDisabled(True)
        self.feedback.set_message("WSM есептелуде…", "")
        self._clear_results()

        try:
            result = self.api.compare_wsm(self.batch_ids, weights=weights)
        except ApiError as exc:
            self.recalc_btn.setDisabled(False)
            self.feedback.set_message(translate_api_error(exc), "error")
            return None

        self.recalc_btn.setDisabled(False)
        self.last_result = result
        w_used = result.get("weights_used", {})
        self.meta_label.setText(
            f"Әдіс: {result.get('method', 'WSM')} ({result.get('version', '')}) · "
            f"Салмақтар: жеңілдік {w_used.get('discount', 0):.2f}, "
            f"мерзім {w_used.get('freshness', 0):.2f}, "
            f"баға {w_used.get('price', 0):.2f} · "
            "Қашықтық өлшемшарты (distance) координаттар болмағандықтан қосылмады."
        )

        if result.get("status") != "ok":
            self.feedback.set_message(
                result.get("reason") or "Салыстыру үшін деректер жеткіліксіз.",
                "error",
            )
            return result

        self.feedback.clear()
        role = self.api.user.get("role") if self.api.user else None

        for entry in result.get("items", []):
            batch = entry["batch"]
            product = batch["product"]
            store = batch["store"]
            norm = entry["normalized"]
            rank = entry["rank"]

            card = QFrame()
            card.setObjectName("orderCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(6)

            head = QHBoxLayout()
            badge = QLabel(f"#{rank} Ең тиімді" if rank == 1 else f"#{rank}")
            badge.setObjectName("wsmRankBadge")
            badge.setProperty("top", "true" if rank == 1 else "false")
            repolish(badge)
            head.addWidget(badge)

            name_lbl = QLabel(product["name"])
            name_lbl.setObjectName("productTitle")
            name_lbl.setWordWrap(True)
            head.addWidget(name_lbl, stretch=1)

            score_lbl = QLabel(f"S = {entry['score']:.3f}")
            score_lbl.setObjectName("wsmScoreLabel")
            head.addWidget(score_lbl)
            cl.addLayout(head)

            meta = QLabel(
                f"{store['name']} · {store['city']} · "
                f"{format_money(batch['discount_price'], batch.get('currency', 'KZT'))} "
                f"(−{entry['discount_percent']:.0f}%) · "
                f"Мерзімі: {entry['hours_left']:.1f} сағ · "
                f"Қалдығы: {format_quantity(batch['quantity_available'])} {unit_label(product['unit'])}"
            )
            meta.setObjectName("mutedText")
            meta.setWordWrap(True)
            cl.addWidget(meta)

            breakdown = QLabel(
                f"Нормалданған бағалар — Жеңілдік: {norm['discount']:.2f} · "
                f"Мерзім: {norm['freshness']:.2f} · Баға: {norm['price']:.2f}"
            )
            breakdown.setObjectName("mutedText")
            cl.addWidget(breakdown)

            expl = QLabel(entry.get("explanation", ""))
            expl.setWordWrap(True)
            cl.addWidget(expl)

            draft = BookingDraft(
                batch_id=str(batch["batch_id"]),
                name=product["name"],
                unit=product["unit"],
                available=to_decimal(batch["quantity_available"]),
            )
            if role == "seller":
                action_btn = QPushButton("Сатып алушы ретінде кіру")
                action_btn.clicked.connect(lambda _=False, d=draft: (self.accept(), self.on_switch_to_buyer(d)))
            else:
                action_btn = QPushButton("Брондау")
                action_btn.setProperty("variant", "primary")
                action_btn.clicked.connect(lambda _=False, d=draft: (self.accept(), self.on_book(d)))
            cl.addWidget(action_btn, alignment=Qt.AlignmentFlag.AlignLeft)

            self.results_layout.addWidget(card)

        return result
