from __future__ import annotations

from decimal import Decimal
import sys
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .catalog_view import CatalogView
from .checkout_views import CheckoutView, OrderConfirmationView, ProductDetailView
from .compare_dialogs import WsmCompareDialog
from .dialogs import AuthDialog, BookingAttempt, BookingDraft, BookingDialog
from .formatting import format_money, format_quantity, role_label, to_decimal, unit_label
from .seller_view import SellerView
from .styles import APP_STYLESHEET
from .widgets import BrandLogo, load_app_icon, repolish


class MainWindow(QMainWindow):
    """Main ObalAi PySide6 multi-screen desktop application."""

    def __init__(self, api: ObalApiClient | None = None) -> None:
        super().__init__()
        self.api = api or ObalApiClient()
        self.api.on_unauthorized = self._handle_unauthorized

        self.current_view = "catalog"
        self.deferred_booking: BookingDraft | None = None
        self.return_to_checkout_after_auth = False
        self.pending_bookings: dict[str, BookingAttempt] = {}

        self.setWindowTitle("ObalAi — Азық-түлік каталогы")
        self.setWindowIcon(load_app_icon())
        self.resize(1220, 840)
        self.setMinimumSize(680, 620)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("headerBar")
        header_outer = QHBoxLayout(header)
        header_outer.setContentsMargins(32, 0, 32, 0)

        header_inner = QWidget()
        header_inner.setMaximumWidth(1160)
        header_layout = QHBoxLayout(header_inner)
        header_layout.setContentsMargins(0, 8, 0, 8)
        header_layout.setSpacing(20)

        header_layout.addWidget(BrandLogo(icon_size=36, font_size=23))
        header_layout.addStretch(1)

        self.nav_catalog_btn = QPushButton("Каталог")
        self.nav_catalog_btn.setProperty("variant", "nav")
        self.nav_catalog_btn.clicked.connect(lambda: self.show_view("catalog"))
        header_layout.addWidget(self.nav_catalog_btn)

        self.nav_seller_btn = QPushButton("Сатушыға")
        self.nav_seller_btn.setProperty("variant", "nav")
        self.nav_seller_btn.clicked.connect(lambda: self.show_view("seller"))
        header_layout.addWidget(self.nav_seller_btn)

        header_layout.addStretch(1)

        self.nav_cart_btn = QPushButton("Себет (0)")
        self.nav_cart_btn.setObjectName("cartNavButton")
        self.nav_cart_btn.setProperty("active", "false")
        self.nav_cart_btn.clicked.connect(lambda: self.show_view("checkout"))
        header_layout.addWidget(self.nav_cart_btn)

        self.session_label = QLabel()
        self.session_label.setObjectName("sessionBadge")
        self.session_label.setVisible(False)
        header_layout.addWidget(self.session_label)

        self.sign_in_btn = QPushButton("Кіру  ↗")
        self.sign_in_btn.clicked.connect(lambda: self.open_auth("login"))
        header_layout.addWidget(self.sign_in_btn)

        self.sign_out_btn = QPushButton("Шығу")
        self.sign_out_btn.setVisible(False)
        self.sign_out_btn.clicked.connect(self.logout)
        header_layout.addWidget(self.sign_out_btn)

        header_outer.addStretch(1)
        header_outer.addWidget(header_inner, stretch=100)
        header_outer.addStretch(1)

        layout.addWidget(header)

        # Stacked views: Catalog, Product Detail, Cart & Checkout, Order Confirmation, Seller
        self.stack = QStackedWidget()
        self.catalog_view = CatalogView(
            self.api,
            on_book=self._add_batch_from_catalog,
            on_switch_to_buyer=self._start_buyer_switch_for_booking,
            on_retry_pending=self._retry_pending_booking,
            on_open_seller=lambda: self.show_view("seller"),
            on_open_detail=self.open_product_detail,
            on_open_compare=self.open_wsm_compare,
            on_toggle_favorite=self.toggle_favorite,
        )
        self.detail_view = ProductDetailView(
            self.api,
            on_back=lambda: self.show_view("catalog"),
            on_add_to_cart=self._add_to_cart,
            on_switch_to_buyer=self._start_buyer_switch_for_batch,
            on_toggle_favorite=self._toggle_favorite_from_detail,
        )
        self.checkout_view = CheckoutView(
            self.api,
            on_back_to_catalog=lambda: self.show_view("catalog"),
            on_request_buyer_auth=self._start_auth_from_checkout,
            on_order_confirmed=self._handle_order_confirmed,
            on_cart_changed=self._update_cart_badge,
        )
        self.confirmation_view = OrderConfirmationView(
            on_back_to_catalog=lambda: self.show_view("catalog"),
        )
        self.seller_view = SellerView(
            self.api,
            on_request_auth=lambda mode, role: self.open_auth(mode, default_role=role),
            on_view_published=self._view_published_product,
            on_back_to_catalog=lambda: self.show_view("catalog"),
        )

        self.stack.addWidget(self.catalog_view)
        self.stack.addWidget(self.detail_view)
        self.stack.addWidget(self.checkout_view)
        self.stack.addWidget(self.confirmation_view)
        self.stack.addWidget(self.seller_view)
        layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)
        self._render_session()
        self._update_cart_badge()
        self.show_view("catalog")

    def closeEvent(self, event) -> None:
        self.api.close()
        super().closeEvent(event)

    def _update_cart_badge(self) -> None:
        count = self.checkout_view.item_count()
        self.nav_cart_btn.setText(f"Себет ({count})")

    def _current_pending_attempt(self) -> BookingAttempt | None:
        user = self.api.user
        if not user or user.get("role") != "buyer":
            return None
        return self.pending_bookings.get(str(user["id"]))

    def _set_current_pending_attempt(self, attempt: BookingAttempt | None) -> None:
        user = self.api.user
        if not user:
            return
        buyer_id = str(user["id"])
        if attempt is None:
            self.pending_bookings.pop(buyer_id, None)
        else:
            self.pending_bookings[buyer_id] = attempt
        self.catalog_view.set_pending_attempt(attempt)

    def _render_session(self) -> None:
        user = self.api.user
        signed_in = user is not None
        self.sign_in_btn.setVisible(not signed_in)
        self.sign_out_btn.setVisible(signed_in)
        self.session_label.setVisible(signed_in)
        if signed_in:
            self.session_label.setText(f"{role_label(user.get('role'))} · {user.get('email', '')}")
        else:
            self.session_label.clear()
        self.catalog_view.set_pending_attempt(self._current_pending_attempt())
        self.checkout_view._sync_auth_controls()
        self._sync_favorites()

    def _sync_favorites(self) -> None:
        user = self.api.user
        if not user or user.get("role") != "buyer" or not self.api.token:
            self.catalog_view.set_favorites(set())
            self.catalog_view.load_ai_recommendations()
            return
        try:
            items = self.api.list_favorites()
            fav_ids = {str(item["batch"]["batch_id"]) for item in items}
        except ApiError:
            fav_ids = set()
        self.catalog_view.set_favorites(fav_ids)
        self.catalog_view.load_ai_recommendations()

    def toggle_favorite(self, batch_id: str) -> bool:
        user = self.api.user
        if not user or user.get("role") != "buyer" or not self.api.token:
            return False
        currently_saved = batch_id in self.catalog_view.favorite_ids
        try:
            if currently_saved:
                self.api.remove_favorite(batch_id)
                self.catalog_view.load_ai_recommendations()
                return False
            self.api.add_favorite(batch_id)
            self.catalog_view.load_ai_recommendations()
            return True
        except ApiError as exc:
            self.catalog_view.set_booking_feedback(translate_api_error(exc), "error")
            return currently_saved

    def open_product_detail(self, batch: dict[str, Any]) -> None:
        bid = str(batch["batch_id"])
        fresh = batch
        try:
            fresh = self.api.get_catalog_batch(bid)
        except ApiError:
            pass
        if self.api.user and self.api.user.get("role") == "buyer" and self.api.token:
            try:
                self.api.record_batch_view(bid)
                self.catalog_view.load_ai_recommendations()
            except ApiError:
                pass
        self.detail_view.set_batch(fresh, is_favorite=bid in self.catalog_view.favorite_ids)
        self.show_view("detail")

    def _toggle_favorite_from_detail(self, batch_id: str) -> bool:
        saved = self.toggle_favorite(batch_id)
        if saved:
            self.catalog_view.favorite_ids.add(batch_id)
        else:
            self.catalog_view.favorite_ids.discard(batch_id)
        self.catalog_view.refresh_card_actions()
        return saved

    def _add_batch_from_catalog(self, batch: dict[str, Any]) -> None:
        self._add_to_cart(batch, None, False)

    def _add_to_cart(self, batch: dict[str, Any], quantity: Decimal | None, go_checkout: bool) -> None:
        ok, message = self.checkout_view.add_batch(batch, quantity=quantity)
        if not ok:
            if self.current_view == "detail":
                self.detail_view.feedback.set_message(message, "error")
            else:
                self.catalog_view.set_booking_feedback(message, "error")
            return
        if go_checkout:
            self.show_view("checkout")
        elif self.current_view == "catalog":
            self.catalog_view.set_booking_feedback(
                f"{message} Рәсімдеу үшін жоғарыдағы «Себет ({self.checkout_view.item_count()})» түймесін басыңыз.",
                "success",
            )

    def _add_draft_and_checkout(self, draft: BookingDraft) -> None:
        fresh = self.catalog_view.find_batch(draft.batch_id)
        if fresh is None:
            try:
                fresh = self.api.get_catalog_batch(draft.batch_id)
            except ApiError as exc:
                self.catalog_view.set_booking_feedback(translate_api_error(exc), "error")
                return
        self._add_to_cart(fresh, draft.quantity, True)

    def open_wsm_compare(self, batch_ids: list[str]) -> None:
        dialog = WsmCompareDialog(
            self.api,
            batch_ids=batch_ids,
            on_book=self._add_draft_and_checkout,
            on_switch_to_buyer=self._start_buyer_switch_for_booking,
            parent=self,
        )
        dialog.exec()

    def _handle_order_confirmed(self, order: dict[str, Any]) -> None:
        self.confirmation_view.set_order(order)
        self.show_view("confirmation")
        self.catalog_view.load_catalog(append=False)
        self.catalog_view.load_ai_recommendations()

    def _handle_unauthorized(self) -> None:
        self.deferred_booking = None
        self.return_to_checkout_after_auth = False
        self.seller_view.reset_state()
        self._render_session()
        if self.current_view == "seller":
            self.seller_view.refresh()
        else:
            self.catalog_view.refresh_card_actions()

    def logout(self) -> None:
        self.api.clear_session()
        self.deferred_booking = None
        self.return_to_checkout_after_auth = False
        self.seller_view.reset_state()
        self.catalog_view.set_booking_feedback()
        self._render_session()
        self.show_view("catalog")

    def show_view(self, view_name: str) -> None:
        valid = {"catalog", "detail", "checkout", "confirmation", "seller"}
        self.current_view = view_name if view_name in valid else "catalog"
        view_map = {
            "catalog": self.catalog_view,
            "detail": self.detail_view,
            "checkout": self.checkout_view,
            "confirmation": self.confirmation_view,
            "seller": self.seller_view,
        }
        self.stack.setCurrentWidget(view_map[self.current_view])

        self.nav_catalog_btn.setProperty("active", "true" if self.current_view in {"catalog", "detail"} else "false")
        self.nav_seller_btn.setProperty("active", "true" if self.current_view == "seller" else "false")
        self.nav_cart_btn.setProperty("active", "true" if self.current_view in {"checkout", "confirmation"} else "false")
        repolish(self.nav_catalog_btn)
        repolish(self.nav_seller_btn)
        repolish(self.nav_cart_btn)

        if self.current_view == "seller":
            self.seller_view.refresh()
        elif self.current_view == "catalog":
            self.catalog_view.load_catalog(append=False)
        elif self.current_view == "checkout":
            self.checkout_view.render_cart()

    def _view_published_product(self, product_name: str) -> None:
        self.catalog_view.set_search_query(product_name)
        self.show_view("catalog")

    def _start_auth_from_checkout(self, mode: str) -> None:
        self.return_to_checkout_after_auth = True
        context = (
            "Себеттегі тапсырысты рәсімдеуді жалғастыру үшін сатып алушы ретінде кіріңіз немесе тіркеліңіз. "
            "Таңдалған өнімдер сақталады."
        )
        self.open_auth(mode, default_role="buyer", context_message=context, preserve_deferred=True)

    def open_auth(
        self,
        mode: str = "login",
        *,
        default_role: str | None = None,
        context_message: str = "",
        preserve_deferred: bool = False,
    ) -> bool:
        if not preserve_deferred:
            self.deferred_booking = None
            self.return_to_checkout_after_auth = False
        role = default_role or ("seller" if self.current_view == "seller" else "buyer")
        dialog = AuthDialog(
            self.api,
            mode=mode,
            default_role=role,
            context_message=context_message,
            parent=self,
        )
        accepted = dialog.exec() == AuthDialog.DialogCode.Accepted
        if not accepted:
            if preserve_deferred:
                self.deferred_booking = None
                self.return_to_checkout_after_auth = False
            return False

        self.seller_view.reset_state()
        self.catalog_view.set_booking_feedback()
        self._render_session()

        if self.return_to_checkout_after_auth:
            self.return_to_checkout_after_auth = False
            self.show_view("checkout")
            return True

        if self.deferred_booking is not None:
            self._resume_deferred_booking()
            return True

        if self.current_view == "seller":
            self.seller_view.refresh()
        elif self.current_view == "detail" and self.detail_view.batch is not None:
            bid = str(self.detail_view.batch["batch_id"])
            self.detail_view.set_batch(self.detail_view.batch, is_favorite=bid in self.catalog_view.favorite_ids)
        elif self.current_view == "checkout":
            self.checkout_view.render_cart()
        else:
            self.catalog_view.load_catalog(append=False)
        return True

    def _start_buyer_switch_for_batch(self, batch: dict[str, Any]) -> None:
        draft = BookingDraft(
            batch_id=str(batch["batch_id"]),
            name=batch["product"]["name"],
            unit=batch["product"]["unit"],
            available=to_decimal(batch["quantity_available"]),
        )
        self._start_buyer_switch_for_booking(draft)

    def _start_buyer_switch_for_booking(self, draft: BookingDraft) -> None:
        self.deferred_booking = draft
        context = (
            f"«{draft.name}» өнімін себетке қосу үшін сатып алушы аккаунтына кіріңіз немесе тіркеліңіз. "
            "Таңдалған өнім сақталады."
        )
        self.open_auth("login", default_role="buyer", context_message=context, preserve_deferred=True)

    def _resume_deferred_booking(self) -> None:
        draft = self.deferred_booking
        self.deferred_booking = None
        if draft is None:
            return

        user = self.api.user
        if not user or user.get("role") != "buyer":
            self.show_view("catalog")
            self.catalog_view.set_booking_feedback(
                "Сіз сатушы аккаунтымен кірдіңіз. Брондау тек сатып алушы аккаунтына қолжетімді.",
                "error",
            )
            return

        self._add_draft_and_checkout(draft)

    def _retry_pending_booking(self) -> None:
        attempt = self._current_pending_attempt()
        if attempt is None:
            return
        draft = BookingDraft(
            batch_id=attempt.batch_id,
            name=attempt.name,
            unit=attempt.unit,
            available=to_decimal(attempt.quantity),
            quantity=to_decimal(attempt.quantity),
        )
        self.open_booking(draft)

    def open_booking(self, draft: BookingDraft) -> None:
        pending = self._current_pending_attempt()
        if pending is not None and pending.batch_id != draft.batch_id:
            self.catalog_view.set_booking_feedback(
                "Алдымен нәтижесі белгісіз алдыңғы броньды тексеріңіз.",
                "error",
            )
            return

        dialog = BookingDialog(
            self.api,
            draft=draft,
            pending_attempt=pending,
            on_attempt_changed=self._set_current_pending_attempt,
            parent=self,
        )
        result = dialog.exec()
        if result == BookingDialog.DialogCode.Accepted and dialog.completed_order is not None:
            self._handle_order_confirmed(dialog.completed_order)


def run_app(base_url: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    api = ObalApiClient(base_url=base_url)
    window = MainWindow(api=api)
    window.show()
    return app.exec()
