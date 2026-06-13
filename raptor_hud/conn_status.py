"""Індикатор статусу зв'язку — окремо для відео (RTSP) і телеметрії (MavLink).

Стани: "demo" (сірий), "connecting" (амбер), "online" (зелений),
"offline" (червоний). Малюється у правому верхньому куті поряд із ⚙.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFontMetricsF
from PySide6.QtWidgets import QWidget

from . import theme

_COLORS = {
    "demo":       QColor(150, 150, 150),
    "connecting": QColor(255, 138, 0),
    "online":     QColor(0, 200, 120),
    "offline":    QColor(225, 55, 45),
}
_WORDS = {
    "demo": "ДЕМО", "connecting": "З'ЄДНАННЯ…",
    "online": "ONLINE", "offline": "OFFLINE",
}


class ConnStatus(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(186, 50)
        self._video = "demo"
        self._tlm = "demo"

    def set_video(self, state: str) -> None:
        self._video = state
        self.update()

    def set_tlm(self, state: str) -> None:
        self._tlm = state
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setBrush(QColor(8, 8, 8, 150))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(rect, 5, 5)

        self._row(p, 18, "ВІДЕО", self._video)
        self._row(p, 38, "MAVLINK", self._tlm)
        p.end()

    def _row(self, p: QPainter, cy: float, label: str, state: str) -> None:
        col = _COLORS.get(state, _COLORS["demo"])
        word = _WORDS.get(state, "—")

        p.setFont(theme.label_font(10))
        p.setPen(theme.LABEL)
        p.drawText(QPointF(12, cy), label)

        dot_x = self.width() - 14
        p.setFont(theme.value_font(12))
        p.setPen(col)
        ww = QFontMetricsF(theme.value_font(12)).horizontalAdvance(word)
        p.drawText(QPointF(dot_x - 12 - ww, cy), word)

        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(dot_x, cy - 4), 4, 4)
