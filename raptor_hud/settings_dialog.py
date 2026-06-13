"""Діалог налаштувань підключення до камери NextVision TRIP 5.

Поля:
- RTSP URL відеопотоку (H.264/H.265);
- рядок MavLink-підключення (udpin:/udp:/serial).
Порожнє поле = демо-режим (статичний кадр / мок-телеметрія).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QFrame, QComboBox)

from . import coords

_QSS = """
QDialog { background: #141414; }
QLabel { color: #cfcfcf; font-size: 13px; }
QLabel#hint { color: #8a8a8a; font-size: 11px; }
QLineEdit {
    background: #0d0d0d; color: #eaeaea; border: 1px solid #3a3a3a;
    border-radius: 4px; padding: 6px 8px; font-size: 13px;
    selection-background-color: #00c878;
}
QLineEdit:focus { border: 1px solid #00c878; }
QPushButton {
    background: #1f1f1f; color: #eaeaea; border: 1px solid #3a3a3a;
    border-radius: 4px; padding: 7px 16px; font-size: 13px;
}
QPushButton:hover { border: 1px solid #00c878; }
QPushButton#primary { background: #006b40; border: 1px solid #00c878; }
QPushButton#primary:hover { background: #00824e; }
QComboBox {
    background: #0d0d0d; color: #eaeaea; border: 1px solid #3a3a3a;
    border-radius: 4px; padding: 6px 8px; font-size: 13px;
}
QComboBox:focus { border: 1px solid #00c878; }
QComboBox QAbstractItemView {
    background: #0d0d0d; color: #eaeaea; selection-background-color: #006b40;
}
"""


class SettingsDialog(QDialog):
    def __init__(self, rtsp: str, mavlink: str, coord_fmt: str = "DD", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Налаштування")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(_QSS)

        self._rtsp = QLineEdit(rtsp)
        self._rtsp.setPlaceholderText("rtsp://192.168.1.10:554/stream")
        self._mavlink = QLineEdit(mavlink)
        self._mavlink.setPlaceholderText("udpin:0.0.0.0:14550")

        self._coords = QComboBox()
        for f in coords.FORMATS:
            self._coords.addItem(coords.FORMAT_NAMES[f], f)
        idx = coords.FORMATS.index(coord_fmt) if coord_fmt in coords.FORMATS else 0
        self._coords.setCurrentIndex(idx)

        form = QFormLayout()
        form.setSpacing(8)
        form.addRow(QLabel("RTSP-потік (відео):"), self._rtsp)
        form.addRow(QLabel("MavLink (телеметрія):"), self._mavlink)
        form.addRow(QLabel("Система координат:"), self._coords)

        hint = QLabel("Порожнє поле → демо-режим (тестовий кадр / мок-телеметрія).\n"
                      "MavLink: udpin:0.0.0.0:14550 · udp:127.0.0.1:14550 · "
                      "/dev/tty.usbserial,57600")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#2a2a2a;")

        btn_cancel = QPushButton("Скасувати")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Зберегти")
        btn_ok.setObjectName("primary")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        root.addLayout(form)
        root.addWidget(hint)
        root.addWidget(line)
        root.addLayout(btns)

    def values(self) -> tuple[str, str, str]:
        """Повертає (rtsp_url, mavlink_conn, coord_fmt)."""
        return (self._rtsp.text().strip(), self._mavlink.text().strip(),
                self._coords.currentData())
