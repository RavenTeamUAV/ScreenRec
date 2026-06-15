"""Точка входу: інтерфейс камери NextVision Raptor 360 з HUD-оверлеєм.

При запуску одразу відкривається діалог підключення. Реальні джерела:
    python -m raptor_hud.main --rtsp rtsp://192.168.1.10:554/stream \
                              --mavlink udpin:0.0.0.0:14550
"""
from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import Qt, QSettings, QTimer, QPoint
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import (QApplication, QWidget,
                               QPushButton, QLabel, QMessageBox)

from .hud_overlay import HudOverlay
from .video_view import VideoView, RtspFrameSource
from .rtp_source import RtpH265FrameSource
from .telemetry import MavlinkSource
from .settings_dialog import SettingsDialog
from .conn_status import ConnStatus
from .recorder import Recorder

_GEAR_QSS = """
QPushButton {
    background: rgba(8,8,8,150); color: #eaeaea;
    border: 1px solid rgba(255,255,255,40); border-radius: 5px;
    font-size: 18px;
}
QPushButton:hover { border: 1px solid #00c878; }
"""

_REC_QSS = """
QPushButton {
    background: rgba(8,8,8,150); color: #ff5555;
    border: 1px solid rgba(255,255,255,40); border-radius: 5px;
    font-size: 16px;
}
QPushButton:hover { border: 1px solid #ff5555; }
"""
_REC_ON_QSS = """
QPushButton {
    background: rgba(200,40,40,200); color: #ffffff;
    border: 1px solid #ff5555; border-radius: 5px;
    font-size: 16px;
}
"""

_REC_LABEL_QSS = """
QLabel {
    color: #ff4040; background: rgba(8,8,8,170);
    border: 1px solid rgba(255,64,64,120); border-radius: 4px;
    padding: 3px 9px; font-size: 13px; font-weight: bold;
}
"""


class MainWindow(QWidget):
    def __init__(self, rtsp: str | None, mavlink: str | None):
        super().__init__()
        self.setWindowTitle("NextVision Raptor 360 — OmniViewer")
        self.resize(1280, 720)
        self.setStyleSheet("background:#0c0c0c;")

        self.video = VideoView(self)
        self.overlay = HudOverlay(self)
        self.overlay.raise_()   # overlay завжди поверх video

        self._settings = QSettings()
        self._rtsp     = rtsp     if rtsp     is not None else self._settings.value("rtsp",      "", str)
        self._mavlink  = mavlink  if mavlink  is not None else self._settings.value("mavlink",   "", str)
        self._coord_fmt = self._settings.value("coord_fmt", "DD", str)
        self._rec_hud   = self._settings.value("rec_hud",  True, bool)
        self.overlay.coord_fmt = self._coord_fmt

        self.video_src = None
        self.tlm       = None

        self.conn = ConnStatus(self)

        self.gear = QPushButton("⚙", self)
        self.gear.setStyleSheet(_GEAR_QSS)
        self.gear.setFixedSize(40, 34)
        self.gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear.setToolTip("Налаштування підключення")
        self.gear.clicked.connect(self._open_settings)
        self.gear.raise_()

        self.rec_btn = QPushButton("⏺", self)
        self.rec_btn.setStyleSheet(_REC_QSS)
        self.rec_btn.setFixedSize(40, 34)
        self.rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_btn.setToolTip("Запис відео на ПК (R)")
        self.rec_btn.clicked.connect(self._toggle_record)
        self.rec_btn.raise_()

        self.rec_label = QLabel("", self)
        self.rec_label.setStyleSheet(_REC_LABEL_QSS)
        self.rec_label.setVisible(False)
        self.rec_label.raise_()

        self.recorder = Recorder(self._grab_frame, fps=25)
        self.recorder.state_changed.connect(self._on_rec_state)
        self.recorder.error.connect(self._on_rec_error)

        self._rec_clock = QTimer(self)
        self._rec_clock.setInterval(500)
        self._rec_clock.timeout.connect(self._update_rec_label)

        # Таймер оновлення дати/часу в оверлеї (1 Гц)
        self._hud_timer = QTimer(self)
        self._hud_timer.setInterval(1000)
        self._hud_timer.timeout.connect(self.overlay.update)
        self._hud_timer.start()

        # Діалог підключення при старті — одразу після показу вікна
        QTimer.singleShot(0, self._startup_dialog)

    # ------------------------------------------------------------------ #
    def _startup_dialog(self) -> None:
        """Показати діалог при старті. Якщо закрити — вікно порожнє."""
        dlg = SettingsDialog(self._rtsp, self._mavlink, self._coord_fmt,
                             self._rec_hud, self)
        dlg.setWindowTitle("Підключення")
        if dlg.exec():
            (self._rtsp, self._mavlink, self._coord_fmt,
             self._rec_hud) = dlg.values()
            self._settings.setValue("rtsp",      self._rtsp)
            self._settings.setValue("mavlink",   self._mavlink)
            self._settings.setValue("coord_fmt", self._coord_fmt)
            self._settings.setValue("rec_hud",   self._rec_hud)
            self.overlay.coord_fmt = self._coord_fmt
            self._apply_sources()

    # ------------------------------------------------------------------ #
    def _apply_sources(self) -> None:
        if self.video_src is not None:
            self.video_src.stop()
            self.video_src = None
        if self.tlm is not None:
            self.tlm.stop()
            try:
                self.tlm.updated.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.tlm = None

        # --- Відео ---
        if self._rtsp:
            self.video_src = self._make_video_source(self._rtsp)
            self.video_src.frame_ready.connect(self.video.set_image)
            self.video_src.status.connect(self.conn.set_video)
            self.conn.set_video("connecting")
            self.video_src.start()
        else:
            self.conn.set_video("offline")

        # --- Телеметрія ---
        if self._mavlink:
            self.tlm = MavlinkSource(self._mavlink)
            self.tlm.updated.connect(self.overlay.set_state)
            self.tlm.updated.connect(self._on_telemetry)
            self.conn.set_tlm("connecting")
            self.tlm.start()
        elif isinstance(self.video_src, RtpH265FrameSource):
            self.video_src.telemetry_ready.connect(self.overlay.set_state)
            self.video_src.telemetry_ready.connect(lambda _: self.conn.set_tlm("online"))
            self.conn.set_tlm("connecting")
        else:
            self.conn.set_tlm("offline")

    def _make_video_source(self, url: str):
        u = url.strip()
        if u.lower().startswith("rtp://"):
            port  = 11025
            mcast = None
            tail  = u.split("//", 1)[1].split("/")[0]
            if ":" in tail:
                host, port_str = tail.rsplit(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    host = tail
            else:
                host = tail
            first = host.split(".")[0] if host else ""
            if first.isdigit() and 224 <= int(first) <= 239:
                mcast = host
            return RtpH265FrameSource(port, mcast)
        return RtspFrameSource(u)

    def _on_telemetry(self, state) -> None:
        self.conn.set_tlm("online" if state.link_online else "offline")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._rtsp, self._mavlink, self._coord_fmt,
                             self._rec_hud, self)
        if dlg.exec():
            (self._rtsp, self._mavlink, self._coord_fmt,
             self._rec_hud) = dlg.values()
            self._settings.setValue("rtsp",      self._rtsp)
            self._settings.setValue("mavlink",   self._mavlink)
            self._settings.setValue("coord_fmt", self._coord_fmt)
            self._settings.setValue("rec_hud",   self._rec_hud)
            self.overlay.coord_fmt = self._coord_fmt
            self.overlay.update()
            self._apply_sources()

    # ------------------------------------------------------------------ #
    def _grab_frame(self) -> QImage:
        size = self.video.size()
        if size.width() <= 0 or size.height() <= 0:
            return QImage()
        img = QImage(size, QImage.Format.Format_RGB888)
        img.fill(Qt.GlobalColor.black)
        self.video.render(img, QPoint(0, 0), QRegion(),
                          QWidget.RenderFlag.DrawChildren)
        if self._rec_hud:
            self.overlay.render(img, QPoint(0, 0), QRegion(),
                                QWidget.RenderFlag.DrawChildren)
        return img

    def _toggle_record(self) -> None:
        self.recorder.toggle()

    def _on_rec_state(self, recording: bool) -> None:
        self.rec_btn.setText("⏹" if recording else "⏺")
        self.rec_btn.setStyleSheet(_REC_ON_QSS if recording else _REC_QSS)
        self.rec_btn.setToolTip(
            "Зупинити запис (R)" if recording else "Запис відео на ПК (R)")
        self.rec_label.setVisible(recording)
        if recording:
            self._update_rec_label()
            self._rec_clock.start()
        else:
            self._rec_clock.stop()
        self._relayout_top()

    def _update_rec_label(self) -> None:
        secs = int(self.recorder.elapsed_s)
        m, s = divmod(secs, 60)
        self.rec_label.setText(f"● REC   {m:02d}:{s:02d}")
        self.rec_label.adjustSize()
        self._relayout_top()

    def _on_rec_error(self, msg: str) -> None:
        self._rec_clock.stop()
        self.rec_label.setVisible(False)
        self.rec_btn.setText("⏺")
        self.rec_btn.setStyleSheet(_REC_QSS)
        QMessageBox.warning(self, "Запис відео", msg)

    def _relayout_top(self) -> None:
        gx = self.width() - self.gear.width() - 14
        self.gear.move(gx, 14)
        rx = gx - self.rec_btn.width() - 8
        self.rec_btn.move(rx, 14)
        self.conn.move(rx - self.conn.width() - 8, 14)
        self.rec_label.move((self.width() - self.rec_label.width()) // 2, 14)
        self.conn.raise_()
        self.gear.raise_()
        self.rec_btn.raise_()
        self.rec_label.raise_()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.video.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())
        self._relayout_top()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        elif e.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif e.key() == Qt.Key.Key_R:
            self._toggle_record()

    def closeEvent(self, e) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
        super().closeEvent(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtsp",    default=None)
    ap.add_argument("--mavlink", default=None)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setOrganizationName("SnakeGroup")
    app.setApplicationName("RaptorHUD")
    win = MainWindow(args.rtsp, args.mavlink)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
