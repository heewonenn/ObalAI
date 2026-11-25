from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_SVG_PATH = ASSETS_DIR / "logo.svg"
HERO_WEBP_PATH = ASSETS_DIR / "hero.webp"


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def load_logo_pixmap(size: int = 36) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    if LOGO_SVG_PATH.exists():
        renderer = QSvgRenderer(str(LOGO_SVG_PATH))
        if renderer.isValid():
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
    return pixmap


def load_app_icon() -> QIcon:
    return QIcon(load_logo_pixmap(64))


class BrandLogo(QWidget):
    """ObalAi brand mark with SVG leaf icon and two-tone title."""

    def __init__(self, *, icon_size: int = 36, font_size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(load_logo_pixmap(icon_size))
        icon_label.setFixedSize(icon_size, icon_size)
        layout.addWidget(icon_label)

        title = QLabel(
            f'<span style="color:#232e23;font-weight:800;font-size:{font_size}px;">Obal</span>'
            f'<span style="color:#244a31;font-weight:800;font-size:{font_size}px;">Ai</span>'
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)


class FormSymbol(QLabel):
    """Small lime square symbol matching the site's card icons."""

    def __init__(self, symbol: str, parent: QWidget | None = None) -> None:
        super().__init__(symbol, parent)
        self.setObjectName("formSymbol")
        self.setFixedSize(38, 38)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class HeroImageWidget(QWidget):
    """Cover-fit rounded image widget for the ObalAi hero banner."""

    def __init__(self, image_path: Path = HERO_WEBP_PATH, radius: float = 21.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap(str(image_path)) if image_path.exists() else QPixmap()
        self._radius = radius
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w = float(self.width())
        h = float(self.height())
        r = min(self._radius, w / 2.0, h / 2.0)

        # Round right corners to match the outer hero card
        path = QPainterPath()
        path.moveTo(0.0, 0.0)
        path.lineTo(w - r, 0.0)
        path.quadTo(w, 0.0, w, r)
        path.lineTo(w, h - r)
        path.quadTo(w, h, w - r, h)
        path.lineTo(0.0, h)
        path.closeSubpath()
        painter.setClipPath(path)

        if self._pixmap.isNull():
            painter.fillRect(self.rect(), Qt.GlobalColor.lightGray)
            painter.end()
            return

        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


class SiteFooter(QFrame):
    """Subtle footer matching the web demo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("siteFooter")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 18, 0, 10)
        layout.setSpacing(12)
        layout.addWidget(BrandLogo(icon_size=26, font_size=18))
        layout.addStretch(1)
        note = QLabel("Азық-түлік ысырабын азайтуға арналған университеттік жоба.")
        note.setObjectName("mutedText")
        layout.addWidget(note)


class FeedbackBanner(QFrame):
    """Inline status/error/success banner with QSS tone styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("feedbackBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
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
