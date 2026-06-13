"""Перевірка парсингу MavLink-повідомлень у MavlinkSource._apply_message.

Будує реальні повідомлення дайалекту ardupilotmega через pymavlink і
прогоняє їх через логіку оновлення стану — без живого з'єднання.

Запуск:  python -m raptor_hud.test_mavlink
"""
import math

from pymavlink.dialects.v20 import ardupilotmega as mav

from raptor_hud.telemetry import MavlinkSource


def _euler_to_quat(roll, pitch, yaw):
    """(roll, pitch, yaw) у радіанах -> кватерніон [w, x, y, z]."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def main() -> int:
    src = MavlinkSource()  # не стартуємо потік — лише тестуємо _apply_message

    msgs = [
        mav.MAVLink_heartbeat_message(
            type=mav.MAV_TYPE_FIXED_WING,
            autopilot=mav.MAV_AUTOPILOT_ARDUPILOTMEGA,
            base_mode=mav.MAV_MODE_FLAG_SAFETY_ARMED | mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            custom_mode=6,  # FBWB
            system_status=mav.MAV_STATE_ACTIVE, mavlink_version=3),
        mav.MAVLink_vfr_hud_message(
            airspeed=21.3, groundspeed=15.4, heading=275,
            throttle=68, alt=1042.0, climb=1.2),
        mav.MAVLink_sys_status_message(
            onboard_control_sensors_present=0, onboard_control_sensors_enabled=0,
            onboard_control_sensors_health=0, load=300,
            voltage_battery=50400, current_battery=4560, battery_remaining=78,
            drop_rate_comm=0, errors_comm=0,
            errors_count1=0, errors_count2=0, errors_count3=0, errors_count4=0),
        mav.MAVLink_global_position_int_message(
            time_boot_ms=1000, lat=485132000, lon=376680000,
            alt=1042000, relative_alt=320000, vx=0, vy=0, vz=0, hdg=27500),
        mav.MAVLink_gps_raw_int_message(
            time_usec=1, fix_type=3, lat=485132000, lon=376680000,
            alt=1042000, eph=80, epv=120, vel=1540, cog=27500,
            satellites_visible=14),
        mav.MAVLink_attitude_message(
            time_boot_ms=1000, roll=0.1396, pitch=0.0698, yaw=0.0,
            rollspeed=0, pitchspeed=0, yawspeed=0),
        # Gimbal Protocol v2: tilt=-30°, pan=20°
        mav.MAVLink_gimbal_device_attitude_status_message(
            target_system=1, target_component=1, time_boot_ms=1000, flags=0,
            q=_euler_to_quat(0.0, math.radians(-30), math.radians(20)),
            angular_velocity_x=0, angular_velocity_y=0, angular_velocity_z=0,
            failure_flags=0),
        # Автотрекінг: прямокутник 0.4..0.6 / 0.3..0.7
        mav.MAVLink_camera_tracking_image_status_message(
            tracking_status=1, tracking_mode=2, target_data=0,
            point_x=float("nan"), point_y=float("nan"), radius=float("nan"),
            rec_top_x=0.4, rec_top_y=0.3, rec_bottom_x=0.6, rec_bottom_y=0.7),
        # Геолокація цілі
        mav.MAVLink_camera_tracking_geo_status_message(
            tracking_status=1, lat=485172000, lon=376720000, alt=185.0,
            h_acc=5.0, v_acc=8.0, vel_n=0, vel_e=0, vel_d=0, vel_acc=2.0,
            dist=1500.0, hdg=math.radians(80), hdg_acc=0.1),
    ]

    for m in msgs:
        src._apply_message(m)

    s = src.state
    checks = [
        ("armed", s.armed, True),
        ("flight_mode", s.flight_mode, "FBWB"),
        ("airspeed", round(s.airspeed, 1), 21.3),
        ("groundspeed", round(s.groundspeed, 1), 15.4),
        ("alt_asl", round(s.alt_asl), 1042),
        ("climb", round(s.climb, 1), 1.2),
        ("heading", round(s.heading), 275),
        ("voltage", round(s.voltage, 1), 50.4),
        ("current", round(s.current, 1), 45.6),
        ("battery_remaining", s.battery_remaining, 78),
        ("alt_rel", round(s.alt_rel), 320),
        ("lat", round(s.lat, 4), 48.5132),
        ("lon", round(s.lon, 4), 37.6680),
        ("gps_sats", s.gps_sats, 14),
        ("roll", round(s.roll), 8),
        ("pitch", round(s.pitch), 4),
        ("cam_tilt", round(s.cam_tilt), -30),
        ("cam_pan", round(s.cam_pan), 20),
        ("track_active", s.track_active, True),
        ("track_cx", round(s.track_cx, 2), 0.5),
        ("track_cy", round(s.track_cy, 2), 0.5),
        ("track_w", round(s.track_w, 2), 0.2),
        ("track_h", round(s.track_h, 2), 0.4),
        ("target_valid", s.target_valid, True),
        ("target_lat", round(s.target_lat, 4), 48.5172),
        ("target_lon", round(s.target_lon, 4), 37.6720),
        ("target_alt", round(s.target_alt), 185),
        ("target_dist", round(s.target_dist), 1500),
        ("target_hdg", round(s.target_hdg), 80),
    ]

    ok = True
    for name, got, exp in checks:
        status = "OK " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print(f"  [{status}] {name:18s} got={got!r:12} expected={exp!r}")

    print("\nРЕЗУЛЬТАТ:", "усі поля коректні ✅" if ok else "Є РОЗБІЖНОСТІ ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
