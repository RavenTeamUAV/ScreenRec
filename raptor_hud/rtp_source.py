"""RTP/MPEG-TS (H.265) відеоджерело для NextVision Raptor / TRIP.

TRIP передає відео як **H.265 у MPEG-TS поверх RTP** (RTP payload type 33) на
UDP-порт. OpenCV `VideoCapture` цей конкретний потік не декодує стабільно
(`PPS id out of range`), тож тут використовуємо **PyAV (libav)**, який декодує
його коректно.

Конвеєр:
    UDP:port → депакетизація RTP (відкидаємо заголовок + RTP-паддинг)
             → чистий MPEG-TS (кожен payload починається з 0x47)
             → PyAV (формат mpegts) → кадри QImage.

Сигнали (як у `RtspFrameSource`):
    frame_ready(QImage), status(str: "connecting"/"online"/"offline").
"""
from __future__ import annotations

import math
import socket
import threading
import time
from copy import copy

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from . import klv as _klv
from .telemetry import TelemetryState


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Початковий пеленг (great-circle) з точки 1 на точку 2, градуси 0..360."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def klv_to_state(d: dict, s: TelemetryState) -> None:
    """Оновлює TelemetryState з декодованого KLV ST 0601 (місцями частково)."""
    if 5 in d:
        s.heading = d[5]
    if 6 in d:
        s.pitch = d[6]
    if 7 in d:
        s.roll = d[7]
    if 13 in d and 14 in d:
        s.lat, s.lon = d[13], d[14]
    if 15 in d:
        s.alt_asl = s.alt_wgs = d[15]
    if 18 in d:                                  # відносний азимут гімбала
        s.cam_pan = d[18] - 360.0 if d[18] > 180.0 else d[18]
    if 19 in d:                                  # відносна елевація гімбала
        s.cam_tilt = d[19]
    if 16 in d:
        s.fov = d[16]
    if 79 in d or 80 in d:                       # шв. землі з N/E складових
        s.groundspeed = math.hypot(d.get(79, 0.0), d.get(80, 0.0))
    # --- ціль = центр кадру ---
    if 23 in d and 24 in d and (d[23] or d[24]):
        s.target_valid = True
        s.target_lat, s.target_lon = d[23], d[24]
        s.target_alt = d.get(25, 0.0)
        s.target_dist = d.get(21, 0.0)
        if 13 in d and 14 in d:
            s.target_hdg = _bearing(d[13], d[14], d[23], d[24])
    else:
        s.target_valid = False
    # --- пропрієтарні теги NextVision ---
    if 101 in d:
        s.sensor_ch = _klv.VIDEO_CHANNEL.get(d[101], "")
    if 104 in d:
        s.cam_mode = _klv.CAMERA_MODE.get(d[104], "")
    if 106 in d:
        s.tracker = _klv.TRACKER_STATE.get(d[106], "")
        s.track_active = d[106] in (2, 4, 5)     # активне стеження
    s.link_online = True


class _RtpTsStream:
    """File-like: приймає RTP на UDP-порту, віддає чистий MPEG-TS через read().

    libav викликає read(n) для читання потоку. Метод блокується, доки є дані,
    і повертає b"" (EOF) лише коли джерело зупиняють.
    """

    def __init__(self, port: int, mcast_group: str | None = None):
        self._port = port
        self._mcast_group = mcast_group  # напр. "225.1.2.3" або None
        self._sock: socket.socket | None = None
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None
        self.packets = 0

    def start(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 21)  # 2 МБ
        except OSError:
            pass
        s.bind(("0.0.0.0", self._port))
        if self._mcast_group:
            import struct
            mreq = struct.pack("4sL", socket.inet_aton(self._mcast_group),
                               socket.INADDR_ANY)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(0.5)
        self._sock = s
        self._running = True
        self._thread = threading.Thread(target=self._rx, daemon=True)
        self._thread.start()

    def _rx(self) -> None:
        while self._running:
            try:
                d, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(d) < 12:
                continue
            # --- депакетизація RTP ---
            b0 = d[0]
            cc = b0 & 0x0F            # CSRC count
            ext = (b0 >> 4) & 1       # extension
            pad = (b0 >> 5) & 1       # padding
            hdr = 12 + cc * 4
            if ext and len(d) >= hdr + 4:
                hdr += 4 + int.from_bytes(d[hdr + 2:hdr + 4], "big") * 4
            end = len(d)
            if pad and end > hdr:
                end -= d[-1]          # останній байт = довжина паддингу
            payload = d[hdr:end]
            if not payload:
                continue
            with self._cv:
                self._buf += payload
                self.packets += 1
                self._cv.notify()

    def read(self, n: int = -1) -> bytes:
        with self._cv:
            while not self._buf and self._running:
                self._cv.wait(0.5)
            if not self._buf:
                return b""           # зупинено → EOF для libav
            if n is None or n < 0:
                n = len(self._buf)
            chunk = bytes(self._buf[:n])
            del self._buf[:n]
            return chunk

    # libav може звертатись до цих атрибутів файло-подібного об'єкта
    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self.stop()

    def stop(self) -> None:
        self._running = False
        with self._cv:
            self._cv.notify_all()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


class RtpH265FrameSource(QObject):
    """Відеоджерело H.265/MPEG-TS-over-RTP на UDP-порту (PyAV)."""

    frame_ready = Signal(object)       # QImage
    telemetry_ready = Signal(object)   # TelemetryState (з KLV-метаданих)
    status = Signal(str)

    def __init__(self, port: int = 11025, mcast_group: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._port = port
        self._mcast_group = mcast_group
        self._running = False
        self._thread: threading.Thread | None = None
        self._stream: _RtpTsStream | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            self._stream.stop()

    def _loop(self) -> None:
        import av
        av.logging.set_level(av.logging.PANIC)   # потік шумить попередженнями
        while self._running:
            self.status.emit("connecting")
            self._stream = _RtpTsStream(self._port, self._mcast_group)
            self._stream.start()
            try:
                container = av.open(
                    self._stream, format="mpegts", mode="r",
                    options={"fflags": "nobuffer", "flags": "low_delay"},
                )
            except Exception:
                self._stream.stop()
                if self._running:
                    self.status.emit("offline")
                    time.sleep(1.0)
                continue

            online = False
            data_idx = {s.index for s in container.streams if s.type == "data"}
            state = TelemetryState()
            try:
                for packet in container.demux():
                    if not self._running:
                        break
                    stype = packet.stream.type
                    if stype == "video":
                        for frame in packet.decode():
                            if not online:
                                self.status.emit("online")
                                online = True
                            arr = frame.to_ndarray(format="rgb24")
                            h, w, _ = arr.shape
                            img = QImage(arr.data, w, h, 3 * w,
                                         QImage.Format.Format_RGB888).copy()
                            self.frame_ready.emit(img)
                    elif packet.stream.index in data_idx:
                        d = _klv.parse_0601(bytes(packet))
                        if d:
                            klv_to_state(d, state)
                            self.telemetry_ready.emit(copy(state))
            except Exception:
                pass
            finally:
                try:
                    container.close()
                except Exception:
                    pass
                self._stream.stop()

            if self._running:
                self.status.emit("offline")
                time.sleep(0.5)
