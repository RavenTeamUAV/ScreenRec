"""Легкий MavLink-симулятор ArduPlane для тестів без заліза.

Шле справжні MAVLink-пакети по UDP (за замовчуванням на 127.0.0.1:14550),
імітуючи літак у польоті з гімбалом NextVision TRIP 5 та активним
автотрекінгом. Призначений для перевірки `MavlinkSource` і всього HUD.

Запуск:
    python -m raptor_hud.sim_mavlink                       # -> udpout:127.0.0.1:14550
    python -m raptor_hud.sim_mavlink udpout:192.168.1.5:14550

Потім в іншому терміналі:
    python -m raptor_hud.main --mavlink udpin:0.0.0.0:14550
"""
from __future__ import annotations

import math
import os
import sys
import time

os.environ.setdefault("MAVLINK20", "1")  # MAVLink 2.0 — для Gimbal v2 / Camera v2

from pymavlink import mavutil


def _euler_to_quat(roll, pitch, yaw):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def main(conn: str = "udpout:127.0.0.1:14550") -> int:
    m = mavutil.mavlink_connection(conn, source_system=1, source_component=1,
                                   dialect="ardupilotmega")
    ml = mavutil.mavlink
    print(f"[SIM] ArduPlane симулятор шле MAVLink -> {conn}")
    print("[SIM] Ctrl+C щоб зупинити.")

    base_lat, base_lon = 48.5132, 37.6680
    t0 = time.monotonic()
    last_hb = 0.0
    try:
        while True:
            t = time.monotonic() - t0
            now = time.monotonic()
            boot_ms = int(t * 1000)

            airspeed = 21.0 + 1.5 * math.sin(t * 0.4)
            groundspeed = 15.0 + 1.2 * math.sin(t * 0.4 + 1.0)
            alt = 1040 + 12 * math.sin(t * 0.15)
            climb = 1.2 * math.cos(t * 0.15)
            heading = int((t * 6.0) % 360)
            voltage = 50.4 - 0.6 * math.sin(t * 0.05)
            current = 44.0 + 4.0 * math.sin(t * 0.8)
            batt = max(0, int(78 - t * 0.05))
            lat = int((base_lat + 0.0008 * math.sin(t * 0.05)) * 1e7)
            lon = int((base_lon + 0.0008 * math.cos(t * 0.05)) * 1e7)
            alt_mm = int(alt * 1000)
            rel_mm = int((320 + 12 * math.sin(t * 0.15)) * 1000)
            wp_dist = int(max(0, 1200 + 1200 * math.sin(t * 0.05)))
            roll = math.radians(8 * math.sin(t * 0.5))
            pitch = math.radians(4 * math.sin(t * 0.3))
            cam_pan = 45 * math.sin(t * 0.2)
            cam_tilt = -30 + 20 * math.sin(t * 0.12)

            # HEARTBEAT — 1 Гц (FBWB, armed)
            if now - last_hb >= 1.0:
                m.mav.heartbeat_send(
                    ml.MAV_TYPE_FIXED_WING, ml.MAV_AUTOPILOT_ARDUPILOTMEGA,
                    ml.MAV_MODE_FLAG_SAFETY_ARMED | ml.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    6, ml.MAV_STATE_ACTIVE)
                last_hb = now

            m.mav.vfr_hud_send(airspeed, groundspeed, heading, 68, alt, climb)
            m.mav.sys_status_send(0, 0, 0, 300, int(voltage * 1000),
                                  int(current * 100), batt, 0, 0, 0, 0, 0, 0)
            m.mav.global_position_int_send(boot_ms, lat, lon, alt_mm, rel_mm,
                                           0, 0, 0, heading * 100)
            m.mav.gps_raw_int_send(int(t * 1e6), 3, lat, lon, alt_mm,
                                   80, 120, int(groundspeed * 100),
                                   heading * 100, 14)
            m.mav.attitude_send(boot_ms, roll, pitch, 0.0, 0, 0, 0)
            m.mav.nav_controller_output_send(0, 0, heading, heading, wp_dist,
                                             0, 0, 0)
            # Gimbal Protocol v2 (TRIP 5)
            q = _euler_to_quat(0.0, math.radians(cam_tilt), math.radians(cam_pan))
            m.mav.gimbal_device_attitude_status_send(
                0, 0, boot_ms, 0, q, 0.0, 0.0, 0.0, 0)
            # Автотрекінг: невелика рамка, що «гуляє» кадром
            cx = 0.5 + 0.18 * math.sin(t * 0.35)
            cy = 0.45 + 0.10 * math.cos(t * 0.27)
            hw, hh = 0.025, 0.032
            m.mav.camera_tracking_image_status_send(
                1, 2, 0, float("nan"), float("nan"), float("nan"),
                cx - hw, cy - hh, cx + hw, cy + hh)
            # Геолокація цілі (зміщення від апарата + похила дальність)
            tdist = 1500 + 700 * math.sin(t * 0.08)
            tlat = int((base_lat + 0.0008 * math.sin(t * 0.05) + 0.004 * math.cos(t * 0.06)) * 1e7)
            tlon = int((base_lon + 0.0008 * math.cos(t * 0.05) + 0.004 * math.sin(t * 0.06)) * 1e7)
            thdg = math.radians((heading + 12 * math.sin(t * 0.3)) % 360)
            m.mav.camera_tracking_geo_status_send(
                1, tlat, tlon, 180 + 10 * math.sin(t * 0.1),
                5.0, 8.0, 0.0, 0.0, 0.0, 2.0, tdist, thdg, 0.1)

            time.sleep(0.1)  # 10 Гц
    except KeyboardInterrupt:
        print("\n[SIM] Зупинено.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "udpout:127.0.0.1:14550"))
