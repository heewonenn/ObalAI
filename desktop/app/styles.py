APP_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #f7f5ee;
    color: #1c241b;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}

QWidget {
    color: #1c241b;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QFrame#headerBar {
    background-color: #fffefa;
    border-bottom: 1px solid #d7dccb;
}

QLabel#brandTitle {
    font-size: 22px;
    font-weight: 700;
    color: #1f4b2c;
}

QLabel#sessionBadge {
    color: #4f5b4d;
    background-color: #eef1e5;
    border: 1px solid #d7dccb;
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 13px;
}

QLabel#pageTitle {
    font-size: 28px;
    font-weight: 700;
    color: #1a2c1e;
}

QLabel#sectionTitle {
    font-size: 20px;
    font-weight: 700;
    color: #1a2c1e;
}

QLabel#stepLabel {
    color: #1f4b2c;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#mutedText {
    color: #5b6558;
    font-size: 13px;
}

QLabel#productTitle {
    font-size: 19px;
    font-weight: 700;
    color: #1a2c1e;
}

QLabel#priceLabel {
    font-size: 20px;
    font-weight: 700;
    color: #1f4b2c;
}

QLabel#oldPriceLabel {
    font-size: 13px;
    color: #778074;
    text-decoration: line-through;
}

QLabel#discountBadge {
    background-color: #d9ecbe;
    color: #1f4b2c;
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#unitBadge {
    color: #1f4b2c;
    font-size: 12px;
    font-weight: 700;
}

QFrame#surfaceCard {
    background-color: #fffefa;
    border: 1px solid #d7dccb;
    border-radius: 14px;
}

QFrame#storeSummary {
    background-color: #edf1e3;
    border: 1px solid #d2dac4;
    border-radius: 12px;
}

QFrame#productCard {
    background-color: #fffefa;
    border: 1px solid #d7dccb;
    border-radius: 14px;
}

QFrame#productCardHeader {
    background-color: #e8edda;
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
    border-bottom: 1px solid #d7dccb;
}

QFrame#orderCard {
    background-color: #fffefa;
    border: 1px solid #d7dccb;
    border-radius: 12px;
}

QFrame#feedbackBanner {
    background-color: #eef1e5;
    border: 1px solid #d7dccb;
    border-radius: 10px;
}

QFrame#feedbackBanner[tone="success"] {
    background-color: #e8f1dc;
    border-color: #bad39c;
}

QFrame#feedbackBanner[tone="error"] {
    background-color: #f9eae6;
    border-color: #dfb0a3;
}

QLabel#feedbackLabel {
    color: #3f4a3d;
    font-size: 13px;
}

QLabel#feedbackLabel[tone="success"] {
    color: #1b5028;
    font-weight: 600;
}

QLabel#feedbackLabel[tone="error"] {
    color: #a62b1c;
    font-weight: 600;
}

QLabel#statusPill {
    background-color: #eef1e5;
    color: #4f5b4d;
    border-radius: 11px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#statusPill[orderStatus="reserved"] {
    background-color: #efe9c9;
    color: #5c4c1c;
}

QLabel#statusPill[orderStatus="accepted"] {
    background-color: #dff0d5;
    color: #1f532b;
}

QLabel#sellerBookingHint {
    background-color: #f3f4ec;
    border: 1px solid #dbe0cf;
    border-radius: 8px;
    color: #4d584b;
    padding: 7px 10px;
    font-size: 12px;
}

QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QDateTimeEdit {
    background-color: #fffefa;
    border: 1px solid #c5ccb9;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 22px;
    selection-background-color: #1f4b2c;
}

QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {
    border: 2px solid #1f4b2c;
}

QPushButton {
    border-radius: 9px;
    padding: 8px 15px;
    font-weight: 600;
    border: 1px solid #c5ccb9;
    background-color: #fffefa;
    color: #1f4b2c;
}

QPushButton:hover {
    background-color: #eef2e5;
}

QPushButton:disabled {
    opacity: 0.5;
    color: #8b9488;
    background-color: #efefe9;
    border-color: #d8ddd0;
}

QPushButton[variant="primary"] {
    background-color: #1f4b2c;
    border-color: #1f4b2c;
    color: #ffffff;
}

QPushButton[variant="primary"]:hover {
    background-color: #173a21;
}

QPushButton[variant="primary"]:disabled {
    background-color: #8da292;
    border-color: #8da292;
    color: #f4f6f2;
}

QPushButton[variant="dark"] {
    background-color: #263128;
    border-color: #263128;
    color: #ffffff;
}

QPushButton[variant="dark"]:hover {
    background-color: #1b241d;
}

QPushButton[variant="nav"] {
    background-color: transparent;
    border: none;
    color: #4a5749;
    padding: 8px 14px;
    border-radius: 8px;
}

QPushButton[variant="nav"]:hover {
    background-color: #eef2e5;
    color: #1f4b2c;
}

QPushButton[variant="nav"][active="true"] {
    background-color: #e4edd7;
    color: #1f4b2c;
    font-weight: 700;
}

QPushButton[variant="link"] {
    background-color: transparent;
    border: none;
    color: #1f4b2c;
    text-decoration: underline;
    padding: 6px 8px;
}

QPushButton[variant="link"]:hover {
    color: #15341e;
    background-color: transparent;
}
"""
