"""Фон з відеопотоком.

`VideoView` показує поточний кадр (QImage), масштабований із заповненням вікна.
Для макета кадр статичний (із assets). Для реального потоку підключіть
`RtspFrameSource`, який віддає кадри з RTSP (Raptor 360) через OpenCV/GStreamer.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QWidget


class VideoView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: QImage | None = None
        self.setAutoFillBackground(True)

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def load_static(self, path: str) -> None:
        img = QImage(path)
        if not img.isNull():
            self._image = img
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 12, 12))
        if self._image is not None and not self._image.isNull():
            scaled = self._image.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
        p.end()


class RtspFrameSource(QObject):
    """Заготовка: тягне кадри з RTSP та віддає їх як QImage.

    Потребує OpenCV із підтримкою FFmpeg/GStreamer. Працює у фоновому потоці.
    Приклад URL для NextVision Raptor: rtsp://192.168.1.x:554/stream
    Сигнал `status` повідомляє стан з'єднання ("connecting"/"online"/"offline").
    """
    frame_ready = Signal(object)  # QImage
    status = Signal(str)

    def __init__(self, url: str, loop_file: bool = True, parent=None):
        super().__init__(parent)
        self._url = url
        self._loop_file = loop_file       # зациклювати, якщо джерело — файл
        self._running = False
        self._thread = None

    def start(self) -> None:
        import os
        import threading
        # low-latency RTSP: транспорт TCP, мінімальна буферизація.
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _open(self):
        import cv2
        cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # тримати лише найсвіжіший кадр
        except Exception:
            pass
        return cap

    def _loop(self) -> None:
        import time
        is_file = "://" not in str(self._url)
        while self._running:
            self.status.emit("connecting")
            cap = self._open()
            if not cap.isOpened():
                self.status.emit("offline")
                cap.release()
                time.sleep(2.0)
                continue
            self.status.emit("online")
            fail = 0
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    if is_file and self._loop_file:
                        import cv2
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # зациклити файл
                        continue
                    fail += 1
                    if fail > 30:
                        break                # потік розірвано — перепідключитись
                    time.sleep(0.02)
                    continue
                fail = 0
                self._emit(frame)
                if is_file:
                    time.sleep(1 / 30)       # відтворення файлу в реальному темпі
            cap.release()
            if self._running:
                self.status.emit("offline")
                time.sleep(1.0)

    def _emit(self, frame) -> None:
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        self.frame_ready.emit(img)
