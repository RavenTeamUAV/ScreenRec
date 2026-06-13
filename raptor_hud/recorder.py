"""Запис відео на ПК: композит «відео + HUD-оверлей» у MP4-файл.

Кадри захоплюються в GUI-потоці за таймером (рендер віджетів відео+оверлею у
QImage), а кодуються у фоновому потоці через OpenCV `VideoWriter`, щоб не
гальмувати інтерфейс. Якщо черга кодувальника переповнюється (диск/CPU не
встигають) — найстаріші кадри відкидаються, UI лишається плавним.

Записується саме те, що бачить оператор: відеопотік із накладеною телеметрією
(час, координати цілі, АКБ, кути гімбала). Кнопки керування та індикатори
статусу в кадр НЕ потрапляють — захоплюються лише шари відео й HUD.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, QStandardPaths, Signal
from PySide6.QtGui import QImage


def default_output_dir() -> str:
    """Тека за замовчуванням: <Відео>/RaptorHUD (з фолбеком на домашню)."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.MoviesLocation)
    if not base:
        base = os.path.expanduser("~")
    out = os.path.join(base, "RaptorHUD")
    os.makedirs(out, exist_ok=True)
    return out


def qimage_to_bgr(img: QImage):
    """QImage → numpy-масив BGR (для OpenCV), з урахуванням вирівнювання рядка."""
    import numpy as np
    import cv2

    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    ptr = img.constBits()
    try:
        arr = np.frombuffer(ptr, np.uint8)
    except TypeError:               # деякі версії віддають не buffer-об'єкт
        arr = np.frombuffer(bytes(ptr), np.uint8)
    arr = arr.reshape(h, bpl)[:, : w * 3].reshape(h, w, 3)   # відкинути паддинг
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


class Recorder(QObject):
    """Запис композитного кадру (відео+HUD) у MP4.

    Параметри:
        grab_fn  — callable() -> QImage: повертає поточний композитний кадр.
        fps      — частота запису.
        out_dir  — тека для файлів (типово `default_output_dir()`).
    """
    state_changed = Signal(bool)    # увімкнено/вимкнено запис
    error = Signal(str)             # текст помилки для UI

    def __init__(self, grab_fn, fps: int = 25, out_dir: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._grab = grab_fn
        self._fps = max(1, int(fps))
        self._out_dir = out_dir or default_output_dir()

        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self._fps))
        self._timer.timeout.connect(self._on_tick)

        self._writer = None
        self._queue: queue.Queue | None = None
        self._worker: threading.Thread | None = None
        self._size: tuple[int, int] | None = None
        self._started_at = 0.0
        self._path: str | None = None
        self._dropped = 0

    # ------------------------------------------------------------------ #
    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    @property
    def elapsed_s(self) -> float:
        return (time.monotonic() - self._started_at) if self.is_recording else 0.0

    @property
    def path(self) -> str | None:
        return self._path

    @property
    def dropped(self) -> int:
        return self._dropped

    # ------------------------------------------------------------------ #
    def toggle(self) -> bool:
        if self.is_recording:
            self.stop()
        else:
            self.start()
        return self.is_recording

    def start(self) -> None:
        if self.is_recording:
            return
        img = self._grab()
        if img is None or img.isNull():
            self.error.emit("Немає кадру для запису.")
            return

        import cv2
        w, h = img.width(), img.height()
        w -= w % 2                  # парні розміри — вимога більшості кодеків
        h -= h % 2
        if w <= 0 or h <= 0:
            self.error.emit("Некоректний розмір вікна для запису.")
            return
        self._size = (w, h)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(self._out_dir, f"raptor_{ts}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self._path, fourcc, float(self._fps), (w, h))
        if not writer.isOpened():
            self.error.emit("Не вдалося відкрити файл для запису (кодек mp4v).")
            self._path = None
            self._size = None
            return

        self._writer = writer
        self._queue = queue.Queue(maxsize=self._fps * 2)
        self._dropped = 0
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()
        self._started_at = time.monotonic()
        self._timer.start()
        self.state_changed.emit(True)

    def stop(self) -> str | None:
        if not self.is_recording:
            return None
        self._timer.stop()
        path = self._path

        if self._queue is not None:
            self._queue.put(None)               # сигнал зупинки кодувальнику
        if self._worker is not None:
            self._worker.join(timeout=10.0)
        self._writer.release()

        self._writer = None
        self._queue = None
        self._worker = None
        self._size = None
        self.state_changed.emit(False)
        return path

    # ------------------------------------------------------------------ #
    def _on_tick(self) -> None:
        if self._queue is None:
            return
        img = self._grab()
        if img is None or img.isNull():
            return
        try:
            bgr = qimage_to_bgr(img)
        except Exception as e:                  # noqa: BLE001 — не валимо UI
            self.error.emit(f"Помилка обробки кадру: {e}")
            return
        try:
            self._queue.put_nowait(bgr)
        except queue.Full:
            self._dropped += 1                  # відкинути кадр, UI важливіший

    def _drain(self) -> None:
        import cv2
        q, writer, size = self._queue, self._writer, self._size
        while True:
            frame = q.get()
            if frame is None:
                break
            if (frame.shape[1], frame.shape[0]) != size:
                frame = cv2.resize(frame, size)
            writer.write(frame)
