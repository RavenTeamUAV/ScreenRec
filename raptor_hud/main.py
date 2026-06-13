"""Точка входу: інтерфейс камери NextVision Raptor 360 з HUD-оверлеєм.

Демо-режим (за замовчуванням):
    python -m raptor_hud.main

Реальні джерела (RTSP + MavLink UDP):
    python -m raptor_hud.main --rtsp rtsp://192.168.1.10:554/stream \
                              --mavlink udpin:0.0.0.0:14550

Підключення також можна задати у вікні через кнопку ⚙ (зберігається між
запусками). Поля з аргументів командного рядка мають пріоритет при старті.
"""
from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (QApplication, QWidget, QStackedLayout,
                               QPushButton)

from .hud_overlay import HudOverlay
from .video_view import VideoView, RtspFrameSource
from .telemetry import MockSource, MavlinkSource
from .settings_dialog import SettingsDialog
from .conn_status import ConnStatus

ASSETS = os.path.join(os.path.dirname(__file__), "assets")

_GEAR_QSS = """
QPushButton {
    background: rgba(8,8,8,150); color: #eaeaea;
    border: 1px solid rgba(255,255,255,40); border-radius: 5px;
    font-size: 18px;
}
QPushButton:hover { border: 1px solid #00c878; }
"""


class MainWindow(QWidget):
    def __init__(self, rtsp: str | None, mavlink: str | None):
        super().__init__()
        self.setWindowTitle("NextVision Raptor 360 — OmniViewer")
        self.resize(1280, 720)
        self.setStyleSheet("background:#0c0c0c;")

        # Відео (фон) + оверлей HUD у стеку, що накладаються
        self.video = VideoView(self)
        self.overlay = HudOverlay(self)

        stack = QStackedLayout(self)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.overlay)   # зверху
        stack.addWidget(self.video)     # знизу
        self.overlay.raise_()

        # Поточні параметри підключення (аргументи > збережені налаштування)
        self._settings = QSettings()
        self._rtsp = rtsp if rtsp is not None else self._settings.value("rtsp", "", str)
        self._mavlink = mavlink if mavlink is not None else self._settings.value("mavlink", "", str)
        self._coord_fmt = self._settings.value("coord_fmt", "DD", str)
        self.overlay.coord_fmt = self._coord_fmt

        self.video_src = None
        self.tlm = None
        self._is_mock = True

        # Індикатор статусу зв'язку (відео + MavLink)
        self.conn = ConnStatus(self)

        # Кнопка налаштувань (⚙) — правий верхній кут
        self.gear = QPushButton("⚙", self)
        self.gear.setObjectName("gear")
        self.gear.setStyleSheet(_GEAR_QSS)
        self.gear.setFixedSize(40, 34)
        self.gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear.setToolTip("Налаштування підключення")
        self.gear.clicked.connect(self._open_settings)
        self.gear.raise_()

        self._apply_sources()

    # ------------------------------------------------------------------ #
    #  Керування джерелами                                                #
    # ------------------------------------------------------------------ #
    def _apply_sources(self) -> None:
        # --- Відео ---
        if self.video_src is not None:
            self.video_src.stop()
            self.video_src = None
        if self._rtsp:
            self.video_src = RtspFrameSource(self._rtsp)
            self.video_src.frame_ready.connect(self.video.set_image)
            self.video_src.status.connect(self.conn.set_video)
            self.conn.set_video("connecting")
            self.video_src.start()
        else:
            self.video.load_static(os.path.join(ASSETS, "sample_feed.png"))
            self.conn.set_video("demo")

        # --- Телеметрія ---
        if self.tlm is not None:
            self.tlm.stop()
            try:
                self.tlm.updated.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.tlm = None
        self._is_mock = not self._mavlink
        self.tlm = MockSource() if self._is_mock else MavlinkSource(self._mavlink)
        self.tlm.updated.connect(self.overlay.set_state)
        self.tlm.updated.connect(self._on_telemetry)
        self.conn.set_tlm("demo" if self._is_mock else "connecting")
        self.tlm.start()

    def _on_telemetry(self, state) -> None:
        if not self._is_mock:
            self.conn.set_tlm("online" if state.link_online else "offline")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._rtsp, self._mavlink, self._coord_fmt, self)
        if dlg.exec():
            self._rtsp, self._mavlink, self._coord_fmt = dlg.values()
            self._settings.setValue("rtsp", self._rtsp)
            self._settings.setValue("mavlink", self._mavlink)
            self._settings.setValue("coord_fmt", self._coord_fmt)
            self.overlay.coord_fmt = self._coord_fmt
            self.overlay.update()
            self._apply_sources()

    # ------------------------------------------------------------------ #
    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        gx = self.width() - self.gear.width() - 14
        self.gear.move(gx, 14)
        self.conn.move(gx - self.conn.width() - 8, 14)
        self.conn.raise_()
        self.gear.raise_()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        elif e.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtsp", default=None, help="RTSP URL відеопотоку Raptor 360")
    ap.add_argument("--mavlink", default=None,
                    help="MavLink-підключення, напр. udpin:0.0.0.0:14550")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setOrganizationName("SnakeGroup")
    app.setApplicationName("RaptorHUD")
    win = MainWindow(args.rtsp, args.mavlink)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
