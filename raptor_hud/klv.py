"""Парсер KLV-метаданих MISB ST 0601 (UAS Datalink Local Set).

NextVision TRIP вбудовує KLV у MPEG-TS відеопотік (окремий data-PID). Кожен
пакет — Local Set: 16-байтовий Universal Label, BER-довжина, далі TLV-трійки
(tag, BER-довжина, value). Тут декодуються теги, потрібні HUD: положення й
орієнтація платформи, кути та FOV сенсора, похила дальність і геолокація центру
кадру (= ціль), а також пропрієтарні теги NextVision (канал, режим, трекер).

`parse_0601(payload) -> dict[int, Any]` повертає {tag: декодоване_значення}.
"""
from __future__ import annotations

import struct

# 16-байтовий ключ UAS Datalink Local Set (MISB ST 0601)
_UL = bytes([0x06, 0x0E, 0x2B, 0x34, 0x02, 0x0B, 0x01, 0x01,
             0x0E, 0x01, 0x03, 0x01, 0x01, 0x00, 0x00, 0x00])


def _ber_len(buf: memoryview, i: int) -> tuple[int, int]:
    """BER-довжина з позиції i. Повертає (значення, нова_позиція)."""
    b = buf[i]
    i += 1
    if b < 0x80:
        return b, i
    n = b & 0x7F
    val = 0
    for _ in range(n):
        val = (val << 8) | buf[i]
        i += 1
    return val, i


def _u(data: bytes) -> int:
    return int.from_bytes(data, "big", signed=False)


def _s(data: bytes) -> int:
    return int.from_bytes(data, "big", signed=True)


# Масштабні декодери для потрібних тегів (MISB ST 0601).
# Кожен: функція bytes -> значення у фізичних одиницях.
_U16 = 65535.0
_U32 = 4294967295.0
_S16 = 32767.0
_S32 = 2147483647.0

_DECODERS = {
    2:  lambda d: _u(d),                              # Unix μs since epoch
    5:  lambda d: _u(d) * 360.0 / _U16,               # heading 0..360
    6:  lambda d: _s(d) * 20.0 / _S16,                # pitch -20..20
    7:  lambda d: _s(d) * 50.0 / _S16,                # roll -50..50
    11: lambda d: d.decode("utf-8", "replace"),       # image source sensor
    12: lambda d: d.decode("utf-8", "replace"),       # image coord system
    13: lambda d: _s(d) * 90.0 / _S32,                # sensor lat
    14: lambda d: _s(d) * 180.0 / _S32,               # sensor lon
    15: lambda d: _u(d) * 19900.0 / _U16 - 900.0,     # sensor MSL alt
    16: lambda d: _u(d) * 180.0 / _U16,               # HFOV 0..180
    17: lambda d: _u(d) * 180.0 / _U16,               # VFOV 0..180
    18: lambda d: _u(d) * 360.0 / _U32,               # rel azimuth 0..360
    19: lambda d: _s(d) * 180.0 / _S32,               # rel elevation -180..180
    20: lambda d: _u(d) * 360.0 / _U32,               # rel roll 0..360
    21: lambda d: _u(d) * 5000000.0 / _U32,           # slant range m
    23: lambda d: _s(d) * 90.0 / _S32,                # frame center lat
    24: lambda d: _s(d) * 180.0 / _S32,               # frame center lon
    25: lambda d: _u(d) * 19900.0 / _U16 - 900.0,     # frame center MSL elev
    79: lambda d: _s(d) * 327.0 / _S16,               # north velocity m/s
    80: lambda d: _s(d) * 327.0 / _S16,               # east velocity m/s
    101: lambda d: _u(d),                             # video channel (0 EO/1 IR)
    104: lambda d: _u(d),                             # camera mode
    105: lambda d: _u(d),                             # recorder state
    106: lambda d: _u(d),                             # tracker state
    107: lambda d: _u(d),                             # gimbal mounting
}

# Розшифровки пропрієтарних тегів
VIDEO_CHANNEL = {0: "EO", 1: "IR"}
CAMERA_MODE = {
    0: "STOW", 1: "PILOT", 2: "RETRACT", 3: "RETRACT LOCK", 4: "OBSERVATION",
    5: "GRR", 6: "HOLD COORD", 7: "POINT COORD", 8: "LOCAL POS",
    9: "GLOBAL POS", 10: "TRACK",
}
TRACKER_STATE = {0: "IDLE", 1: "READY", 2: "TRACKING", 3: "RE-TRACK",
                 4: "TRACKING", 5: "TRACKING"}


def parse_0601(payload: bytes) -> dict:
    """Декодує один KLV Local Set ST 0601. Порожній dict, якщо це не 0601."""
    if len(payload) < 17 or bytes(payload[:16]) != _UL:
        return {}
    buf = memoryview(payload)
    i = 16
    total, i = _ber_len(buf, i)
    end = min(len(payload), i + total)
    out: dict = {}
    while i < end:
        tag = buf[i]; i += 1
        ln, i = _ber_len(buf, i)
        val = bytes(buf[i:i + ln]); i += ln
        dec = _DECODERS.get(tag)
        if dec is not None:
            try:
                out[tag] = dec(val)
            except Exception:
                pass
    return out
