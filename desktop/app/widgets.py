from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class FeedbackBanner(QFrame):
    """Inline status/error/success banner with QSS tone styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("feedbackBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        self.label = QLabel()
        self.label.setObjectName("feedbackLabel")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.clear()

    def set_message(self, message: str, tone: str = "") -> None:
        self.label.setText(message)
        self.setProperty("tone", tone)
        self.label.setProperty("tone", tone)
        repolish(self)
        repolish(self.label)
        self.setVisible(bool(message))

    def clear(self) -> None:
        self.set_message("", "")
