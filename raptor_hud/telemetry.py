"""Модель телеметрії та джерела даних.

`TelemetryState` — єдина структура, яку споживає HUD.
`MockSource` — генерує правдоподібні анімовані дані для макета.
`MavlinkSource` — заготовка під реальне MavLink UDP-підключення (Raptor 360).

Усі джерела успадковують `TelemetrySource(QObject)` і випромінюють сигнал
`updated(TelemetryState)` приблизно 5 разів на секунду.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal


def _quat_to_euler(q) -> tuple[float, float, float]:
    """Кватерніон [w, x, y, z] -> (roll, pitch, yaw) у радіанах."""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sp = 2 * (w * y - z * x)
    sp = max(-1.0, min(1.0, sp))
    pitch = math.asin(sp)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


@dataclass
class TelemetryState:
    airspeed: float = 0.0        # м/с
    groundspeed: float = 0.0     # м/с
    alt_asl: float = 0.0         # м (над рівнем моря, барометрична)
    alt_wgs: float = 0.0         # м (GPS, еліпсоїд WGS84)
    alt_rel: float = 0.0         # м (відносно точки зльоту)
    dist_wp: float = 0.0         # м (дистанція до точки маршруту)
    climb: float = 0.0           # м/с (вертикальна швидкість)
    current: float = 0.0         # А (струм споживання)
    voltage: float = 0.0         # В (напруга батареї)
    battery_remaining: int = 0   # %
    heading: float = 0.0         # градуси (0..360)
    roll: float = 0.0            # градуси
    pitch: float = 0.0           # градуси
    cam_pan: float = 0.0         # кут камери по азимуту (gimbal), градуси
    cam_tilt: float = 0.0        # нахил камери (gimbal), градуси
    # --- Автотрекінг TRIP 5 (CAMERA_TRACKING_IMAGE_STATUS) ---
    track_active: bool = False   # чи активне стеження за об'єктом
    track_cx: float = 0.5        # центр цілі X (нормовано 0..1 від кадру)
    track_cy: float = 0.5        # центр цілі Y (нормовано 0..1)
    track_w: float = 0.0         # ширина рамки (нормовано 0..1)
    track_h: float = 0.0         # висота рамки (нормовано 0..1)
    # --- Геолокація цілі TRIP 5 (CAMERA_TRACKING_GEO_STATUS) ---
    target_valid: bool = False   # чи є дійсна геолокація цілі
    target_lat: float = 0.0      # широта цілі, градуси
    target_lon: float = 0.0      # довгота цілі, градуси
    target_alt: float = 0.0      # висота цілі (MSL), м
    target_dist: float = 0.0     # похила дальність до цілі, м
    target_hdg: float = 0.0      # пеленг на ціль, градуси
    lat: float = 0.0
    lon: float = 0.0
    armed: bool = False
    flight_mode: str = "—"
    link_online: bool = False
    flight_time_s: int = 0       # секунди в польоті
    gps_sats: int = 0


class TelemetrySource(QObject):
    updated = Signal(object)  # TelemetryState

    def start(self) -> None:  # перевизначається
        raise NotImplementedError

    def stop(self) -> None:
        pass


class MockSource(TelemetrySource):
    """Анімовані тестові дані для візуального макета."""

    def __init__(self, hz: float = 5.0, parent=None):
        super().__init__(parent)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / hz))
        self._timer.timeout.connect(self._tick)
        self.state = TelemetryState(
            armed=True, flight_mode="FBWB", link_online=True,
            voltage=50.4, battery_remaining=78, gps_sats=14,
            lat=48.5132, lon=37.6680,
        )

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        t = time.monotonic() - self._t0
        s = self.state
        s.airspeed = 21.0 + 1.5 * math.sin(t * 0.4)
        s.groundspeed = 15.0 + 1.2 * math.sin(t * 0.4 + 1.0)
        s.alt_asl = 1040 + 12 * math.sin(t * 0.15)
        s.alt_wgs = s.alt_asl + 6
        s.alt_rel = 320 + 12 * math.sin(t * 0.15)
        s.dist_wp = max(0.0, 1200 + 1200 * math.sin(t * 0.05))
        s.climb = 1.2 * math.cos(t * 0.15)
        s.current = 44.0 + 4.0 * math.sin(t * 0.8)
        s.voltage = 50.4 - 0.6 * math.sin(t * 0.05)
        s.heading = (t * 6.0) % 360.0
        s.roll = 8 * math.sin(t * 0.5)
        s.pitch = 4 * math.sin(t * 0.3)
        s.cam_pan = 45 * math.sin(t * 0.2)
        s.cam_tilt = -30 + 20 * math.sin(t * 0.12)
        s.flight_time_s = 27 * 60 + int(t)
        # автотрекінг: ціль плавно «гуляє» кадром (демо)
        s.track_active = True
        s.track_cx = 0.5 + 0.18 * math.sin(t * 0.35)
        s.track_cy = 0.45 + 0.10 * math.cos(t * 0.27)
        s.track_w = 0.05 + 0.008 * math.sin(t * 0.9)
        s.track_h = 0.065 + 0.008 * math.cos(t * 0.9)
        # геолокація цілі (демо): зміщення від апарата + похила дальність
        s.target_valid = True
        s.target_dist = 1500 + 700 * math.sin(t * 0.08)
        s.target_hdg = (s.heading + 12 * math.sin(t * 0.3)) % 360
        s.target_lat = s.lat + 0.004 * math.cos(t * 0.06)
        s.target_lon = s.lon + 0.004 * math.sin(t * 0.06)
        s.target_alt = 180 + 10 * math.sin(t * 0.1)
        s.lat = 48.5132 + 0.0008 * math.sin(t * 0.05)
        s.lon = 37.6680 + 0.0008 * math.cos(t * 0.05)
        self.updated.emit(s)


class MavlinkSource(TelemetrySource):
    """Реальне джерело: MavLink через UDP (Raptor 360 / автопілот).

    Підключення: udpin:0.0.0.0:14550 (за замовчуванням QGC/MP).
    Потребує `pymavlink`. Працює у фоновому потоці, а сигнал `updated`
    випромінюється у головний потік через черговий QTimer-снапшот.
    """

    # Повна карта числових режимів ArduPlane -> назви.
    # (custom_mode із HEARTBEAT; джерело: ArduPilot Plane/mode.h)
    _PLANE_MODES = {
        0: "MANUAL", 1: "CIRCLE", 2: "STABILIZE", 3: "TRAINING", 4: "ACRO",
        5: "FBWA", 6: "FBWB", 7: "CRUISE", 8: "AUTOTUNE", 10: "AUTO",
        11: "RTL", 12: "LOITER", 13: "TAKEOFF", 14: "AVOID_ADSB", 15: "GUIDED",
        17: "QSTABILIZE", 18: "QHOVER", 19: "QLOITER", 20: "QLAND",
        21: "QRTL", 22: "QAUTOTUNE", 23: "QACRO", 24: "THERMAL",
        25: "LOITER2QLAND",
    }

    def __init__(self, connection: str = "udpin:0.0.0.0:14550",
                 hz: float = 5.0, parent=None):
        super().__init__(parent)
        self._conn_str = connection
        self.state = TelemetryState()
        self._master = None
        self._thread = None
        self._running = False
        self._emit_timer = QTimer(self)
        self._emit_timer.setInterval(int(1000 / hz))
        self._emit_timer.timeout.connect(lambda: self.updated.emit(self.state))

    def start(self) -> None:
        import threading
        self._running = True
        self._thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._thread.start()
        self._emit_timer.start()

    def stop(self) -> None:
        self._running = False
        self._emit_timer.stop()

    def _rx_loop(self) -> None:
        from pymavlink import mavutil
        self._master = mavutil.mavlink_connection(self._conn_str)
        self._master.wait_heartbeat(timeout=10)
        last_msg = time.monotonic()
        while self._running:
            msg = self._master.recv_match(blocking=True, timeout=1.0)
            now = time.monotonic()
            if msg is None:
                self.state.link_online = (now - last_msg) < 3.0
                continue
            last_msg = now
            self.state.link_online = True
            self._apply_message(msg)

    def _apply_message(self, msg) -> None:
        """Оновлює `self.state` з одного MavLink-повідомлення.

        Винесено окремо від циклу прийому, щоб логіку можна було тестувати
        без живого з'єднання. `msg` — об'єкт pymavlink (має .get_type()).
        """
        s = self.state
        t = msg.get_type()
        if t == "HEARTBEAT":
            # MAV_MODE_FLAG_SAFETY_ARMED = 128
            s.armed = bool(msg.base_mode & 0x80)
            s.flight_mode = self._PLANE_MODES.get(msg.custom_mode, f"M{msg.custom_mode}")
        elif t == "VFR_HUD":
            s.airspeed = msg.airspeed
            s.groundspeed = msg.groundspeed
            s.alt_asl = msg.alt
            s.climb = msg.climb
            s.heading = float(msg.heading)
        elif t == "ATTITUDE":
            s.roll = math.degrees(msg.roll)
            s.pitch = math.degrees(msg.pitch)
        elif t == "SYS_STATUS":
            s.voltage = msg.voltage_battery / 1000.0       # mV -> V
            s.current = msg.current_battery / 100.0         # cA -> A
            s.battery_remaining = msg.battery_remaining     # %
        elif t == "GLOBAL_POSITION_INT":
            s.lat = msg.lat / 1e7
            s.lon = msg.lon / 1e7
            s.alt_rel = msg.relative_alt / 1000.0           # mm -> m
        elif t == "GPS_RAW_INT":
            s.gps_sats = msg.satellites_visible
            s.alt_wgs = msg.alt / 1000.0                    # mm -> m (GPS)
        elif t == "NAV_CONTROLLER_OUTPUT":
            s.dist_wp = float(msg.wp_dist)                  # м до точки
        elif t == "MOUNT_STATUS":
            # старий протокол: кути гімбала в сантиградусах
            s.cam_tilt = msg.pointing_a / 100.0   # pitch (tilt)
            s.cam_pan = msg.pointing_c / 100.0    # yaw (pan)
        elif t == "GIMBAL_DEVICE_ATTITUDE_STATUS":
            # Gimbal Protocol v2 (TRIP 5): орієнтація кватерніоном q=[w,x,y,z]
            roll, pitch, yaw = _quat_to_euler(msg.q)
            s.cam_tilt = math.degrees(pitch)
            s.cam_pan = math.degrees(yaw)
        elif t == "CAMERA_TRACKING_IMAGE_STATUS":
            # Автотрекінг TRIP 5. Координати нормовані 0..1 (NaN якщо немає).
            active = msg.tracking_status == 1  # 1 = ACTIVE
            s.track_active = active
            if active and msg.tracking_mode == 2:           # RECTANGLE
                tx, ty = msg.rec_top_x, msg.rec_top_y
                bx, by = msg.rec_bottom_x, msg.rec_bottom_y
                if not any(math.isnan(v) for v in (tx, ty, bx, by)):
                    s.track_cx = (tx + bx) / 2.0
                    s.track_cy = (ty + by) / 2.0
                    s.track_w = abs(bx - tx)
                    s.track_h = abs(by - ty)
            elif active and msg.tracking_mode == 1:         # POINT
                if not (math.isnan(msg.point_x) or math.isnan(msg.point_y)):
                    s.track_cx = msg.point_x
                    s.track_cy = msg.point_y
                    r = 0.0 if math.isnan(msg.radius) else msg.radius
                    s.track_w = s.track_h = max(0.02, 2 * r)
        elif t == "CAMERA_TRACKING_GEO_STATUS":
            # Геолокація цілі TRIP 5: координати + похила дальність + пеленг.
            s.target_valid = msg.tracking_status == 1 and msg.lat != 0
            if s.target_valid:
                s.target_lat = msg.lat / 1e7
                s.target_lon = msg.lon / 1e7
                s.target_alt = msg.alt
                s.target_dist = 0.0 if math.isnan(msg.dist) else msg.dist
                s.target_hdg = 0.0 if math.isnan(msg.hdg) else math.degrees(msg.hdg) % 360
