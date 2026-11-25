APP_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #f7f5ee;
    color: #232e23;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 14px;
}

QWidget {
    color: #232e23;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* Header */
QFrame#headerBar {
    background-color: #f7f5ee;
    border-bottom: 1px solid #d9dacb;
}

QLabel#sessionBadge {
    color: #565f52;
    background-color: #efede0;
    border: 1px solid #d9dacb;
    border-radius: 16px;
    padding: 5px 13px;
    font-size: 13px;
}

/* Hero Banner */
QFrame#heroCard {
    background-color: #ecefdf;
    border: 1px solid #d8dac9;
    border-radius: 22px;
}

QLabel#eyebrowLabel {
    color: #244a31;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

QLabel#eyebrowDot {
    background-color: #54723e;
    border-radius: 4px;
}

QLabel#heroTitle {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 40px;
    color: #232e23;
}

QLabel#heroDescription {
    color: #565f52;
    font-size: 15px;
}

/* Section & Card Typography */
QLabel#pageTitle {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 34px;
    color: #232e23;
}

QLabel#sectionTitle {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 24px;
    color: #232e23;
}

QLabel#dialogTitle {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 30px;
    color: #232e23;
}

QLabel#stepLabel {
    color: #244a31;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.2px;
}

QLabel#mutedText {
    color: #565f52;
    font-size: 13px;
}

QLabel#productTitle {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 22px;
    color: #232e23;
}

QLabel#priceLabel {
    font-size: 22px;
    font-weight: 700;
    color: #244a31;
}

QLabel#oldPriceLabel {
    font-size: 14px;
    color: #565f52;
    text-decoration: line-through;
}

QLabel#discountBadge {
    background-color: #ddeb9b;
    color: #2e4829;
    border-radius: 11px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#unitBadge {
    color: #244a31;
    font-size: 13px;
    font-weight: 700;
}

QLabel#formSymbol {
    background-color: #ddeb9b;
    color: #244a31;
    border-radius: 10px;
    font-size: 19px;
    font-weight: 700;
}

/* Surfaces */
QFrame#surfaceCard {
    background-color: #fdfcf8;
    border: 1px solid #d9dacb;
    border-radius: 18px;
}

QFrame#storeSummary {
    background-color: #edf0e3;
    border: 1px solid #d5dbc7;
    border-radius: 12px;
}

QFrame#productCard {
    background-color: #fdfcf8;
    border: 1px solid #d9dacb;
    border-radius: 16px;
}

QFrame#productCardHeader {
    background-color: #e8edda;
    border-top-left-radius: 15px;
    border-top-right-radius: 15px;
    border-bottom: 1px solid #d9dacb;
}

QFrame#emptyStateCard {
    background-color: #f0f1e7;
    border: 1px dashed #c7cdbb;
    border-radius: 17px;
}

QFrame#orderCard {
    background-color: #fdfcf8;
    border: 1px solid #d9dacb;
    border-radius: 14px;
}

QFrame#siteFooter {
    border-top: 1px solid #d9dacb;
    background-color: transparent;
}

/* Feedback Banners */
QFrame#feedbackBanner {
    background-color: #eef0e5;
    border: 1px solid #d9dacb;
    border-radius: 10px;
}

QFrame#feedbackBanner[tone="success"] {
    background-color: #e9efdd;
    border-color: #c2d4a5;
}

QFrame#feedbackBanner[tone="error"] {
    background-color: #f7eae5;
    border-color: #dfb0a3;
}

QLabel#feedbackLabel {
    color: #565f52;
    font-size: 14px;
}

QLabel#feedbackLabel[tone="success"] {
    color: #183a25;
    font-weight: 600;
}

QLabel#feedbackLabel[tone="error"] {
    color: #8e372d;
    font-weight: 600;
}

QLabel#statusPill {
    background-color: #efede0;
    color: #565f52;
    border-radius: 12px;
    padding: 4px 11px;
    font-size: 13px;
    font-weight: 700;
}

QLabel#statusPill[orderStatus="reserved"] {
    background-color: #ece8cd;
    color: #544822;
}

QLabel#statusPill[orderStatus="accepted"] {
    background-color: #e2ebd7;
    color: #183a25;
}

QLabel#sellerBookingHint {
    background-color: #f0f1e7;
    border: 1px solid #d9dacb;
    border-radius: 10px;
    color: #565f52;
    padding: 8px 10px;
    font-size: 12px;
}

/* Form Inputs */
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QDateTimeEdit {
    background-color: #fffefa;
    border: 1px solid #cbd0bf;
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 24px;
    selection-background-color: #244a31;
}

QLineEdit#searchInput {
    border-radius: 20px;
    padding: 8px 16px;
    min-height: 24px;
    background-color: #fdfcf8;
    border: 1px solid #c6cbb9;
}

QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {
    border: 2px solid #244a31;
}

/* Pill Buttons */
QPushButton {
    border-radius: 19px;
    padding: 9px 18px;
    font-size: 14px;
    font-weight: 700;
    border: 1px solid #adb9a9;
    background-color: transparent;
    color: #244a31;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #e9eddf;
    border-color: #244a31;
}

QPushButton:disabled {
    color: #8b9488;
    background-color: #efefe9;
    border-color: #d8ddd0;
}

QPushButton[variant="primary"] {
    background-color: #244a31;
    border-color: #244a31;
    color: #ffffff;
}

QPushButton[variant="primary"]:hover {
    background-color: #183a25;
    border-color: #183a25;
}

QPushButton[variant="primary"]:disabled {
    background-color: #8da292;
    border-color: #8da292;
    color: #f4f6f2;
}

QPushButton[variant="dark"] {
    background-color: #232e23;
    border-color: #232e23;
    color: #ffffff;
}

QPushButton[variant="dark"]:hover {
    background-color: #244a31;
    border-color: #244a31;
}

QPushButton[variant="nav"] {
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    color: #565f52;
    padding: 14px 4px;
    font-weight: 600;
}

QPushButton[variant="nav"]:hover {
    color: #244a31;
    border-bottom: 2px solid #244a31;
    background-color: transparent;
}

QPushButton[variant="nav"][active="true"] {
    color: #244a31;
    border-bottom: 2px solid #244a31;
    font-weight: 700;
}

QPushButton[variant="link"] {
    background-color: transparent;
    border: none;
    color: #244a31;
    padding: 8px 10px;
    font-weight: 700;
}

QPushButton[variant="link"]:hover {
    color: #183a25;
    text-decoration: underline;
    background-color: transparent;
}

QPushButton#iconPillButton {
    border-radius: 20px;
    padding: 0px;
    font-size: 18px;
    font-weight: 700;
}

QFrame#filterBar {
    background-color: #fdfcf8;
    border: 1px solid #d9dacb;
    border-radius: 16px;
}

QFrame#compareBar {
    background-color: #e8edda;
    border: 1px solid #c3d0b0;
    border-radius: 14px;
}

QPushButton#favButton {
    border-radius: 14px;
    padding: 2px 8px;
    min-height: 24px;
    border: 1px solid #c3cdb9;
    background-color: #fdfcf8;
    color: #565f52;
    font-size: 14px;
}

QPushButton#favButton[saved="true"] {
    background-color: #244a31;
    border-color: #244a31;
    color: #ddeb9b;
}

QPushButton#cardSecondaryBtn {
    border-radius: 14px;
    padding: 6px 12px;
    min-height: 18px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid #c6cdb9;
    background-color: #f7f5ee;
    color: #244a31;
}

QPushButton#cardSecondaryBtn:hover {
    background-color: #e8edda;
    border-color: #244a31;
}

QPushButton#cardSecondaryBtn[selected="true"] {
    background-color: #ddeb9b;
    border-color: #244a31;
    color: #183a25;
}

QPushButton#favoritesFilterBtn[checked="true"] {
    background-color: #244a31;
    border-color: #244a31;
    color: #ddeb9b;
}

QLabel#wsmRankBadge {
    background-color: #e8edda;
    color: #244a31;
    border-radius: 11px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#wsmRankBadge[top="true"] {
    background-color: #244a31;
    color: #ddeb9b;
}

QLabel#wsmScoreLabel {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 24px;
    color: #244a31;
    font-weight: 700;
}

/* Scrollbar polish */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
}

QScrollBar::handle:vertical {
    background: #c8cebd;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #a5b19b;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
