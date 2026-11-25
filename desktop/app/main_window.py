from __future__ import annotations

import sys

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

from .api_client import ObalApiClient
from .catalog_view import CatalogView
from .dialogs import AuthDialog, BookingAttempt, BookingDraft, BookingDialog
from .formatting import format_money, format_quantity, role_label, to_decimal, unit_label
from .seller_view import SellerView
from .styles import APP_STYLESHEET
from .widgets import BrandLogo, load_app_icon, repolish


class MainWindow(QMainWindow):
    """Main ObalAi PySide6 application window."""

    def __init__(self, api: ObalApiClient | None = None) -> None:
        super().__init__()
        self.api = api or ObalApiClient()
        self.api.on_unauthorized = self._handle_unauthorized

        self.current_view = "catalog"
        self.deferred_booking: BookingDraft | None = None
        self.pending_bookings: dict[str, BookingAttempt] = {}

        self.setWindowTitle("ObalAi — Азық-түлік каталогы")
        self.setWindowIcon(load_app_icon())
        self.resize(1200, 820)
        self.setMinimumSize(640, 620)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header matching the site's 3-column layout
        header = QFrame()
        header.setObjectName("headerBar")
        header_outer = QHBoxLayout(header)
        header_outer.setContentsMargins(32, 0, 32, 0)

        header_inner = QWidget()
        header_inner.setMaximumWidth(1160)
        header_layout = QHBoxLayout(header_inner)
        header_layout.setContentsMargins(0, 8, 0, 8)
        header_layout.setSpacing(24)

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

        # Stacked views
        self.stack = QStackedWidget()
        self.catalog_view = CatalogView(
            self.api,
            on_book=self.open_booking,
            on_switch_to_buyer=self._start_buyer_switch_for_booking,
            on_retry_pending=self._retry_pending_booking,
            on_open_seller=lambda: self.show_view("seller"),
        )
        self.seller_view = SellerView(
            self.api,
            on_request_auth=lambda mode, role: self.open_auth(mode, default_role=role),
            on_view_published=self._view_published_product,
            on_back_to_catalog=lambda: self.show_view("catalog"),
        )
        self.stack.addWidget(self.catalog_view)
        self.stack.addWidget(self.seller_view)
        layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)
        self._render_session()
        self.show_view("catalog")

    def closeEvent(self, event) -> None:
        self.api.close()
        super().closeEvent(event)

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

    def _handle_unauthorized(self) -> None:
        self.deferred_booking = None
        self.seller_view.reset_state()
        self._render_session()
        if self.current_view == "seller":
            self.seller_view.refresh()
        else:
            self.catalog_view.refresh_card_actions()

    def logout(self) -> None:
        self.api.clear_session()
        self.deferred_booking = None
        self.seller_view.reset_state()
        self.catalog_view.set_booking_feedback()
        self._render_session()
        self.show_view("catalog")

    def show_view(self, view_name: str) -> None:
        self.current_view = "seller" if view_name == "seller" else "catalog"
        is_seller_tab = self.current_view == "seller"
        self.stack.setCurrentWidget(self.seller_view if is_seller_tab else self.catalog_view)

        self.nav_catalog_btn.setProperty("active", "false" if is_seller_tab else "true")
        self.nav_seller_btn.setProperty("active", "true" if is_seller_tab else "false")
        repolish(self.nav_catalog_btn)
        repolish(self.nav_seller_btn)

        if is_seller_tab:
            self.seller_view.refresh()
        else:
            self.catalog_view.load_catalog(append=False)

    def _view_published_product(self, product_name: str) -> None:
        self.catalog_view.set_search_query(product_name)
        self.show_view("catalog")

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
            return False

        self.seller_view.reset_state()
        self.catalog_view.set_booking_feedback()
        self._render_session()

        if self.deferred_booking is not None:
            self._resume_deferred_booking()
            return True

        if self.current_view == "seller":
            self.seller_view.refresh()
        else:
            self.catalog_view.load_catalog(append=False)
        return True

    def _start_buyer_switch_for_booking(self, draft: BookingDraft) -> None:
        self.deferred_booking = draft
        context = (
            f"«{draft.name}» өнімін брондау үшін сатып алушы аккаунтына кіріңіз немесе тіркеліңіз. "
            "Таңдалған өнім сақталады."
        )
        self.open_auth("login", default_role="buyer", context_message=context, preserve_deferred=True)

    def _resume_deferred_booking(self) -> None:
        draft = self.deferred_booking
        self.deferred_booking = None
        if draft is None:
            return

        self.show_view("catalog")
        user = self.api.user
        if not user or user.get("role") != "buyer":
            self.catalog_view.set_booking_feedback(
                "Сіз сатушы аккаунтымен кірдіңіз. Брондау тек сатып алушы аккаунтына қолжетімді.",
                "error",
            )
            return

        if self._current_pending_attempt() is not None:
            self.catalog_view.set_booking_feedback(
                "Алдымен нәтижесі белгісіз алдыңғы броньды тексеріңіз.",
                "error",
            )
            return

        fresh = self.catalog_view.find_batch(draft.batch_id)
        if fresh is None:
            # Also check unfiltered catalog if a search query is active
            all_batches = self.api.list_catalog(q="", limit=100, offset=0)
            fresh = next((b for b in all_batches if str(b["batch_id"]) == draft.batch_id), None)

        if fresh is None:
            self.catalog_view.set_booking_feedback("Бұл партия қазір қолжетімсіз.", "error")
            return

        fresh_available = to_decimal(fresh["quantity_available"])
        updated_draft = BookingDraft(
            batch_id=draft.batch_id,
            name=fresh["product"]["name"],
            unit=fresh["product"]["unit"],
            available=fresh_available,
            quantity=draft.quantity,
        )
        self.open_booking(updated_draft)

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

        if result == BookingDialog.RESULT_AUTH_REQUESTED:
            saved_qty = dialog.selected_quantity
            self.deferred_booking = BookingDraft(
                batch_id=draft.batch_id,
                name=draft.name,
                unit=draft.unit,
                available=draft.available,
                quantity=saved_qty,
            )
            qty_str = format_quantity(saved_qty)
            unit_str = unit_label(draft.unit)
            context = (
                f"«{draft.name}» ({qty_str} {unit_str}) броньдауды жалғастыру үшін "
                "сатып алушы ретінде кіріңіз немесе тіркеліңіз."
            )
            self.open_auth(
                dialog.requested_auth_mode or "login",
                default_role="buyer",
                context_message=context,
                preserve_deferred=True,
            )
            return

        if result == BookingDialog.DialogCode.Accepted and dialog.completed_order is not None:
            order = dialog.completed_order
            unit_str = unit_label(draft.unit)
            receipt = (
                f"«{draft.name}» брондалды. №{str(order['id'])[:8]} · "
                f"{format_quantity(order['quantity'])} {unit_str} · "
                f"{format_money(order['total_amount'], order.get('currency', 'KZT'))}."
            )
            self.catalog_view.set_booking_feedback(receipt, "success")
            self.catalog_view.load_catalog(append=False)
            return

        if dialog.rejected_error_message:
            self.catalog_view.set_booking_feedback(dialog.rejected_error_message, "error")
            self.catalog_view.load_catalog(append=False)


def run_app(base_url: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    api = ObalApiClient(base_url=base_url)
    window = MainWindow(api=api)
    window.show()
    return app.exec()
