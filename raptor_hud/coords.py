"""Конвертація географічних координат у різні системи відображення.

Підтримує: DD (десяткові градуси), DMS (градуси-хвилини-секунди),
DDM (градуси-десяткові хвилини), UTM та MGRS (військова сітка НАТО).
Реалізація суто на Python (WGS84), без зовнішніх залежностей —
працює офлайн на ноутбуці оператора.

Головна функція `format_coord(lat, lon, fmt)` повертає список рядків
(label, value) для відображення в HUD.
"""
from __future__ import annotations

import math

FORMATS = ["DD", "DMS", "DDM", "MGRS", "UTM"]
FORMAT_NAMES = {
    "DD":   "Десяткові градуси (DD)",
    "DMS":  "Градуси-хвилини-секунди (DMS)",
    "DDM":  "Градуси-десяткові хвилини (DDM)",
    "MGRS": "MGRS (військова сітка НАТО)",
    "UTM":  "UTM",
}

# --- WGS84 ---
_A = 6378137.0
_E = 0.00669438        # e²
_K0 = 0.9996
_E_P2 = _E / (1 - _E)


def _lat_band(lat: float) -> str:
    """Літера широтної зони UTM (C..X, без I/O)."""
    bands = "CDEFGHJKLMNPQRSTUVWX"
    lat = max(-80.0, min(83.9, lat))
    return bands[int((lat + 80) / 8)]


def latlon_to_utm(lat: float, lon: float):
    """(lat, lon) -> (zone, band, easting, northing) для WGS84."""
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    zone = int((lon + 180) / 6) + 1
    lon_origin = math.radians((zone - 1) * 6 - 180 + 3)

    n = _A / math.sqrt(1 - _E * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = _E_P2 * math.cos(lat_r) ** 2
    a = math.cos(lat_r) * (lon_r - lon_origin)
    e2, e3 = _E * _E, _E * _E * _E
    m = _A * ((1 - _E / 4 - 3 * e2 / 64 - 5 * e3 / 256) * lat_r
              - (3 * _E / 8 + 3 * e2 / 32 + 45 * e3 / 1024) * math.sin(2 * lat_r)
              + (15 * e2 / 256 + 45 * e3 / 1024) * math.sin(4 * lat_r)
              - (35 * e3 / 3072) * math.sin(6 * lat_r))

    easting = (_K0 * n * (a + (1 - t + c) * a ** 3 / 6
               + (5 - 18 * t + t * t + 72 * c - 58 * _E_P2) * a ** 5 / 120) + 500000.0)
    northing = (_K0 * (m + n * math.tan(lat_r) * (a * a / 2
                + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                + (61 - 58 * t + t * t + 600 * c - 330 * _E_P2) * a ** 6 / 720)))
    if lat < 0:
        northing += 10000000.0
    return zone, _lat_band(lat), easting, northing


def latlon_to_mgrs(lat: float, lon: float, precision: int = 5) -> str:
    zone, band, easting, northing = latlon_to_utm(lat, lon)
    col_set = ["ABCDEFGH", "JKLMNPQR", "STUVWXYZ"][(zone - 1) % 3]
    col = col_set[int(easting // 100000) - 1]
    row_letters = "ABCDEFGHJKLMNPQRSTUV"
    row_idx = int(northing // 100000) % 20
    if zone % 2 == 0:
        row_idx = (row_idx + 5) % 20
    row = row_letters[row_idx]
    div = 10 ** (5 - precision)
    e = int(easting % 100000) // div
    n = int(northing % 100000) // div
    return f"{zone}{band} {col}{row} {e:0{precision}d} {n:0{precision}d}"


def _dms(value: float, pos: str, neg: str):
    hemi = pos if value >= 0 else neg
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = (value - d - m / 60) * 3600
    return f"{d}°{m:02d}'{s:04.1f}\"{hemi}"


def _ddm(value: float, pos: str, neg: str):
    hemi = pos if value >= 0 else neg
    value = abs(value)
    d = int(value)
    m = (value - d) * 60
    return f"{d}°{m:06.3f}'{hemi}"


def format_coord(lat: float, lon: float, fmt: str) -> list[tuple[str, str]]:
    """Повертає рядки (підпис, значення) для панелі цілі."""
    if fmt == "DMS":
        return [("ШИР", _dms(lat, "Пн", "Пд")), ("ДОВ", _dms(lon, "Сх", "Зх"))]
    if fmt == "DDM":
        return [("ШИР", _ddm(lat, "Пн", "Пд")), ("ДОВ", _ddm(lon, "Сх", "Зх"))]
    if fmt == "MGRS":
        return [("MGRS", latlon_to_mgrs(lat, lon))]
    if fmt == "UTM":
        zone, band, e, n = latlon_to_utm(lat, lon)
        return [("UTM", f"{zone}{band} {int(e)} {int(n)}")]
    # DD за замовчуванням
    return [("ШИР", f"{lat:.5f}°"), ("ДОВ", f"{lon:.5f}°")]


if __name__ == "__main__":  # самоперевірка проти відомої точки
    # Монумент Вашингтона: 38.8895, -77.0353 -> 18S UJ 23487 06483
    got = latlon_to_mgrs(38.8895, -77.0353)
    print("MGRS test:", got)
    assert got.startswith("18S UJ 234") and " 064" in got, got
    # Україна (зона 37U)
    print("UA  test :", latlon_to_mgrs(48.5172, 37.6720))
    assert latlon_to_mgrs(48.5172, 37.6720).startswith("37U"), "zone"
    print("OK")
