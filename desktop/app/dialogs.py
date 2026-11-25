from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiError, ObalApiClient, translate_api_error
from .formatting import format_decimal_api, format_quantity, to_decimal, unit_label
from .widgets import FeedbackBanner, FormSymbol, load_logo_pixmap


@dataclass
class BookingDraft:
    batch_id: str
    name: str
    unit: str
    available: Decimal
    quantity: Decimal | None = None


@dataclass
class BookingAttempt:
    batch_id: str
    name: str
    unit: str
    quantity: str
    idempotency_key: str


class AuthDialog(QDialog):
    """Login and registration dialog communicating with FastAPI /api/auth/*."""

    def __init__(
        self,
        api: ObalApiClient,
        *,
        mode: str = "login",
        default_role: str = "buyer",
        context_message: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.mode = "register" if mode == "register" else "login"
        self.default_role = default_role if default_role in {"buyer", "seller"} else "buyer"
        self.setWindowTitle("ObalAi — Жүйеге кіру")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        logo_label = QLabel()
        logo_label.setPixmap(load_logo_pixmap(40))
        logo_label.setFixedSize(40, 40)
        root.addWidget(logo_label)

        self.title_label = QLabel()
        self.title_label.setObjectName("dialogTitle")
        root.addWidget(self.title_label)

        self.context_banner = FeedbackBanner()
        root.addWidget(self.context_banner)
        if context_message:
            self.context_banner.set_message(context_message, "")

        email_label = QLabel("Электрондық пошта")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("email@example.com")
        root.addWidget(email_label)
        root.addWidget(self.email_input)

        password_label = QLabel("Құпиясөз")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMaxLength(128)
        self.password_input.setPlaceholderText("Кемінде 8 таңба")
        root.addWidget(password_label)
        root.addWidget(self.password_input)

        self.role_box = QFrame()
        role_layout = QVBoxLayout(self.role_box)
        role_layout.setContentsMargins(0, 4, 0, 4)
        role_layout.setSpacing(6)
        role_layout.addWidget(QLabel("Аккаунт түрі"))
        radio_row = QHBoxLayout()
        self.buyer_radio = QRadioButton("Сатып алушы")
        self.seller_radio = QRadioButton("Сатушы")
        self.role_group = QButtonGroup(self)
        self.role_group.addButton(self.buyer_radio)
        self.role_group.addButton(self.seller_radio)
        if self.default_role == "seller":
            self.seller_radio.setChecked(True)
        else:
            self.buyer_radio.setChecked(True)
        radio_row.addWidget(self.buyer_radio)
        radio_row.addWidget(self.seller_radio)
        radio_row.addStretch(1)
        role_layout.addLayout(radio_row)
        root.addWidget(self.role_box)

        self.feedback = FeedbackBanner()
        root.addWidget(self.feedback)

        self.submit_button = QPushButton()
        self.submit_button.setProperty("variant", "primary")
        self.submit_button.clicked.connect(self._submit)
        root.addWidget(self.submit_button)

        footer = QHBoxLayout()
        self.toggle_button = QPushButton()
        self.toggle_button.setProperty("variant", "link")
        self.toggle_button.clicked.connect(self._toggle_mode)
        self.cancel_button = QPushButton("Жабу")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.toggle_button)
        footer.addStretch(1)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)

        self.password_input.returnPressed.connect(self._submit)
        self.email_input.returnPressed.connect(self._submit)

        self._apply_mode()
        self.email_input.setFocus()

    def _apply_mode(self) -> None:
        registering = self.mode == "register"
        self.setWindowTitle("ObalAi — Аккаунт ашу" if registering else "ObalAi — Кіру")
        self.title_label.setText("Аккаунт ашу" if registering else "Кіру")
        self.role_box.setVisible(registering)
        self.submit_button.setText("Тіркелу" if registering else "Кіру")
        self.toggle_button.setText("Аккаунтым бар" if registering else "Аккаунт ашу")
        self.password_input.setPlaceholderText("Кемінде 8 таңба" if registering else "Құпиясөз")

    def _toggle_mode(self) -> None:
        self.mode = "login" if self.mode == "register" else "register"
        self.feedback.clear()
        self._apply_mode()

    def _set_busy(self, busy: bool) -> None:
        self.submit_button.setDisabled(busy)
        self.toggle_button.setDisabled(busy)
        self.cancel_button.setDisabled(busy)
        self.email_input.setDisabled(busy)
        self.password_input.setDisabled(busy)
        self.buyer_radio.setDisabled(busy)
        self.seller_radio.setDisabled(busy)

    def _submit(self) -> None:
        email = self.email_input.text().strip()
        password = self.password_input.text()
        if not email or "@" not in email:
            self.feedback.set_message("Дұрыс email мекенжайын енгізіңіз.", "error")
            self.email_input.setFocus()
            return
        if self.mode == "register" and len(password) < 8:
            self.feedback.set_message("Құпиясөз кемінде 8 таңбадан тұруы керек.", "error")
            self.password_input.setFocus()
            return
        if not password:
            self.feedback.set_message("Құпиясөзді енгізіңіз.", "error")
            self.password_input.setFocus()
            return

        role = "seller" if self.seller_radio.isChecked() else "buyer"
        self.feedback.clear()
        self._set_busy(True)
        registered = False
        try:
            if self.mode == "register":
                self.api.register(email=email, password=password, role=role)
                registered = True
            self.api.login(email=email, password=password)
        except ApiError as exc:
            if registered:
                self.mode = "login"
                self._apply_mode()
            self.feedback.set_message(translate_api_error(exc), "error")
            self._set_busy(False)
            return
        except Exception as exc:
            self.feedback.set_message(translate_api_error(exc), "error")
            self._set_busy(False)
            return

        self._set_busy(False)
        self.accept()


class BookingDialog(QDialog):
    """Reservation dialog supporting buyers, guest auth handoff, and idempotent retries."""

    RESULT_AUTH_REQUESTED = 100

    def __init__(
        self,
        api: ObalApiClient,
        *,
        draft: BookingDraft,
        pending_attempt: BookingAttempt | None = None,
        on_attempt_changed=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.draft = draft
        self.pending_attempt = pending_attempt
        self.on_attempt_changed = on_attempt_changed
        self.completed_order: dict[str, Any] | None = None
        self.rejected_error_message: str | None = None
        self.requested_auth_mode: str | None = None
        self.selected_quantity: Decimal = Decimal("1")

        self.setWindowTitle("ObalAi — Өнімді брондау")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        root.addWidget(FormSymbol("✓"))

        title = QLabel("Өнімді брондау")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        product_label = QLabel(draft.name)
        product_label.setObjectName("productTitle")
        product_label.setWordWrap(True)
        root.addWidget(product_label)

        unit_text = unit_label(draft.unit)
        self.available_label = QLabel()
        self.available_label.setObjectName("mutedText")
        self.available_label.setWordWrap(True)
        if pending_attempt is not None:
            self.available_label.setText("Алдыңғы сұрауды сол санмен қайталаңыз.")
        else:
            self.available_label.setText(f"Қалдығы: {format_quantity(draft.available)} {unit_text}")
        root.addWidget(self.available_label)

        qty_label = QLabel(f"Саны ({unit_text})")
        root.addWidget(qty_label)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setDecimals(3)
        self.quantity_input.setMinimum(0.001)
        self.quantity_input.setMaximum(999_999_999.999)
        self.quantity_input.setSingleStep(1.0 if draft.unit != "kg" else 0.5)

        if pending_attempt is not None:
            initial_qty = to_decimal(pending_attempt.quantity)
            self.quantity_input.setValue(float(initial_qty))
            self.quantity_input.setReadOnly(True)
            self.quantity_input.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        else:
            default_qty = draft.quantity
            if default_qty is None:
                default_qty = draft.available if draft.available < Decimal("1") else Decimal("1")
            if default_qty > draft.available and draft.available > 0:
                default_qty = draft.available
            self.quantity_input.setMaximum(max(float(draft.available), 0.001))
            self.quantity_input.setValue(float(default_qty))
        root.addWidget(self.quantity_input)

        self.feedback = FeedbackBanner()
        root.addWidget(self.feedback)

        is_buyer = self.api.user is not None and self.api.user.get("role") == "buyer"
        is_guest = self.api.user is None

        if is_buyer:
            self.submit_button = QPushButton(
                "Броньды тексеру" if pending_attempt is not None else "Брондау"
            )
            self.submit_button.setProperty("variant", "primary")
            self.submit_button.clicked.connect(self._submit_booking)
            root.addWidget(self.submit_button)
        elif is_guest:
            self.feedback.set_message(
                "Броньды аяқтау үшін сатып алушы ретінде кіріңіз немесе тіркеліңіз. "
                "Таңдалған өнім мен саны сақталады.",
                "",
            )
            auth_buttons = QHBoxLayout()
            auth_buttons.setSpacing(10)
            self.login_button = QPushButton("Кіру")
            self.login_button.setProperty("variant", "primary")
            self.login_button.clicked.connect(lambda: self._request_auth("login"))

            self.register_button = QPushButton("Сатып алушы болып тіркелу")
            self.register_button.clicked.connect(lambda: self._request_auth("register"))

            auth_buttons.addWidget(self.login_button)
            auth_buttons.addWidget(self.register_button)
            root.addLayout(auth_buttons)
        else:
            self.feedback.set_message(
                "Брондау тек сатып алушы аккаунтына қолжетімді.",
                "error",
            )
            self.switch_button = QPushButton("Сатып алушы ретінде кіру")
            self.switch_button.setProperty("variant", "primary")
            self.switch_button.clicked.connect(lambda: self._request_auth("login"))
            root.addWidget(self.switch_button)

        self.close_button = QPushButton("Жабу")
        self.close_button.clicked.connect(self.reject)
        root.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _current_quantity_decimal(self) -> Decimal:
        return to_decimal(f"{self.quantity_input.value():.3f}")

    def _request_auth(self, mode: str) -> None:
        self.requested_auth_mode = mode
        self.selected_quantity = self._current_quantity_decimal()
        self.done(self.RESULT_AUTH_REQUESTED)

    def _set_busy(self, busy: bool) -> None:
        if hasattr(self, "submit_button"):
            self.submit_button.setDisabled(busy)
        self.close_button.setDisabled(busy)
        if self.pending_attempt is None:
            self.quantity_input.setReadOnly(busy)

    def _submit_booking(self) -> None:
        if not self.api.token or not self.api.user or self.api.user.get("role") != "buyer":
            self.feedback.set_message("Брондау үшін сатып алушы ретінде кіріңіз.", "error")
            return

        if self.pending_attempt is None:
            qty_dec = self._current_quantity_decimal()
            if qty_dec <= 0:
                self.feedback.set_message("Өнім саны 0-ден үлкен болуы керек.", "error")
                return
            attempt = BookingAttempt(
                batch_id=self.draft.batch_id,
                name=self.draft.name,
                unit=self.draft.unit,
                quantity=format_decimal_api(qty_dec, places=3),
                idempotency_key=str(uuid.uuid4()),
            )
            self.pending_attempt = attempt
            if self.on_attempt_changed is not None:
                self.on_attempt_changed(attempt)
        else:
            attempt = self.pending_attempt

        self._set_busy(True)
        self.quantity_input.setReadOnly(True)
        self.feedback.set_message("Бронь жіберілуде…", "")

        try:
            order = self.api.create_reservation(
                batch_id=attempt.batch_id,
                quantity=attempt.quantity,
                idempotency_key=attempt.idempotency_key,
            )
        except ApiError as exc:
            self._set_busy(False)
            if exc.status_code in {400, 403, 404, 409, 422}:
                self.pending_attempt = None
                if self.on_attempt_changed is not None:
                    self.on_attempt_changed(None)
                self.rejected_error_message = translate_api_error(exc)
                self.reject()
                return
            if exc.status_code == 401:
                self.rejected_error_message = "Қайта кіріп, алдыңғы броньды тексеріңіз."
                self.reject()
                return
            self.submit_button.setText("Броньды тексеру")
            self.available_label.setText("Алдыңғы сұрауды сол санмен қайталаңыз.")
            self.feedback.set_message(
                "Бронь нәтижесі белгісіз. Осы сұрауды қайта жіберіп тексеріңіз.",
                "error",
            )
            return

        self.pending_attempt = None
        if self.on_attempt_changed is not None:
            self.on_attempt_changed(None)
        self.completed_order = order
        self._set_busy(False)
        self.accept()
