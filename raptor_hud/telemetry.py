"""Модель телеметрії та джерела даних.

`TelemetryState` — єдина структура, яку споживає HUD.
`MavlinkSource` — реальне MavLink UDP/Serial підключення (Raptor 360 / ArduPlane).

Усі джерела успадковують `TelemetrySource(QObject)` і випромінюють сигнал
`updated(TelemetryState)` приблизно 5 разів на секунду.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Відстань між двома точками (м), WGS-84 сфера."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    # --- Сенсор NextVision (з KLV ST 0601 / NextVision-тегів) ---
    fov: float = 0.0             # горизонтальний кут поля зору, градуси
    sensor_ch: str = ""          # активний канал: "EO" / "IR"
    cam_mode: str = ""           # режим спостереження (LOCAL POS / TRACK / …)
    tracker: str = ""            # стан трекера (IDLE / TRACKING / …)
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
    # --- Дистанції ---
    dist_home: float = 0.0       # м до точки зльоту (HOME_POSITION)
    dist_gcs: float = 0.0        # м до GCS (GLOBAL_POSITION_INT від sysid GCS)
    home_lat: float = 0.0
    home_lon: float = 0.0
    gcs_lat: float = 0.0
    gcs_lon: float = 0.0


class TelemetrySource(QObject):
    updated = Signal(object)  # TelemetryState

    def start(self) -> None:  # перевизначається
        raise NotImplementedError

    def stop(self) -> None:
        pass


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
        self._arm_time: float | None = None   # monotonic час моменту ARMED
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
        while self._running:
            try:
                self._master = mavutil.mavlink_connection(self._conn_str)
                hb = self._master.wait_heartbeat(timeout=10)
                if hb is None:
                    self.state.link_online = False
                    continue
            except Exception:
                self.state.link_online = False
                time.sleep(2.0)
                continue
            last_msg = time.monotonic()
            while self._running:
                msg = self._master.recv_match(blocking=True, timeout=1.0)
                now = time.monotonic()
                if msg is None:
                    self.state.link_online = (now - last_msg) < 3.0
                    if not self.state.link_online:
                        break   # перепідключитись
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
            now = time.monotonic()
            newly_armed = bool(msg.base_mode & 0x80)
            if newly_armed and not s.armed:
                self._arm_time = now
            elif not newly_armed:
                self._arm_time = None
            s.armed = newly_armed
            if s.armed and self._arm_time is not None:
                s.flight_time_s = int(now - self._arm_time)
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
            if msg.get_srcSystem() == 1:                    # літак
                s.lat = msg.lat / 1e7
                s.lon = msg.lon / 1e7
                s.alt_rel = msg.relative_alt / 1000.0       # mm -> m
                if s.home_lat or s.home_lon:
                    s.dist_home = _haversine(s.lat, s.lon, s.home_lat, s.home_lon)
                if s.gcs_lat or s.gcs_lon:
                    s.dist_gcs = _haversine(s.lat, s.lon, s.gcs_lat, s.gcs_lon)
            else:                                           # GCS (sysid != 1)
                s.gcs_lat = msg.lat / 1e7
                s.gcs_lon = msg.lon / 1e7
                if s.lat or s.lon:
                    s.dist_gcs = _haversine(s.lat, s.lon, s.gcs_lat, s.gcs_lon)
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
        elif t == "HOME_POSITION":
            s.home_lat = msg.latitude / 1e7
            s.home_lon = msg.longitude / 1e7
            if s.lat or s.lon:
                s.dist_home = _haversine(s.lat, s.lon, s.home_lat, s.home_lon)
        elif t == "CAMERA_TRACKING_GEO_STATUS":
            # Геолокація цілі TRIP 5: координати + похила дальність + пеленг.
            s.target_valid = msg.tracking_status == 1 and msg.lat != 0
            if s.target_valid:
                s.target_lat = msg.lat / 1e7
                s.target_lon = msg.lon / 1e7
                s.target_alt = msg.alt
                s.target_dist = 0.0 if math.isnan(msg.dist) else msg.dist
                s.target_hdg = 0.0 if math.isnan(msg.hdg) else math.degrees(msg.hdg) % 360
