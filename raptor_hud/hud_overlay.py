"""Прозорий оверлей HUD у стилі NextVision OmniViewerHD."""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QPen, QColor, QPolygonF, QFontMetricsF,
                           QLinearGradient)
from PySide6.QtWidgets import QWidget

from . import theme
from .telemetry import TelemetryState

BAR_H    = 68
VALUE_PX = 22
SUB_PX   = 14
LABEL_PX = 11
UNIT_GAP = 6
LABEL_DY = 16
VALUE_DY = 9


def fmt_time(total_s: int) -> str:
    m, s = divmod(int(total_s), 60)
    return f"{m:02d}:{s:02d}"


@staticmethod
def _adv(font, text: str) -> float:
    return QFontMetricsF(font).horizontalAdvance(text)


class HudOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.state = TelemetryState()
        self.coord_fmt = "DD"

    def set_state(self, state: TelemetryState) -> None:
        self.state = state
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        self._draw_datetime(p)
        self._draw_bottom_bar(p)
        p.end()

    # ------------------------------------------------------------------ #
    #  Date / time — top left                                             #
    # ------------------------------------------------------------------ #
    def _draw_datetime(self, p: QPainter) -> None:
        now = datetime.now()
        date_txt = now.strftime("%Y-%m-%d")
        time_txt = now.strftime("%H:%M:%S")
        x, y   = 14.0, 14.0
        time_f = theme.value_font(22)
        date_f = theme.label_font(11)
        w = max(_adv(time_f, time_txt), _adv(date_f, date_txt)) + 20
        p.setBrush(QColor(8, 8, 8, 150))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(QRectF(x, y, w, 46), 4, 4)
        p.setFont(date_f); p.setPen(theme.LABEL)
        p.drawText(QPointF(x + 10, y + 17), date_txt)
        p.setFont(time_f); p.setPen(theme.VALUE)
        p.drawText(QPointF(x + 10, y + 39), time_txt)

    # ------------------------------------------------------------------ #
    #  Bottom bar — stretched cells                                        #
    # ------------------------------------------------------------------ #
    def _draw_bottom_bar(self, p: QPainter) -> None:
        total_w = self.width()
        h       = self.height()
        bar_top = h - BAR_H
        cy      = bar_top + BAR_H / 2

        # background
        grad = QLinearGradient(0, bar_top - 14, 0, bar_top + 6)
        grad.setColorAt(0.0, QColor(8, 8, 8, 0))
        grad.setColorAt(1.0, theme.BAR_BG)
        p.fillRect(QRectF(0, bar_top - 14, total_w, 20), grad)
        p.fillRect(QRectF(0, bar_top, total_w, BAR_H), theme.BAR_BG)

        s = self.state

        # ── Fixed left block: logo + compass ─────────────────────────── #
        x = 14.0
        x = self._draw_logo(p, x, cy)
        x += 12
        x = self._draw_compass(p, x, cy, s.heading)
        x += 8
        left_end = x   # де закінчується фіксована ліва частина

        # ── Fixed right block: LINK ───────────────────────────────────── #
        link_txt  = "ONLINE" if s.link_online else "OFFLINE"
        link_col  = theme.ACCENT if s.link_online else theme.DANGER
        lf_link   = theme.label_font(LABEL_PX)
        vf_link   = theme.value_font(VALUE_PX - 2)
        link_lbl_w = _adv(lf_link, "LINK")
        link_val_w = _adv(vf_link, link_txt)
        link_block = max(link_lbl_w, link_val_w) + 14 + 18  # dot+gap+right margin
        right_end  = total_w - 18  # правий край останнього роздільника

        # ── Cell specs ───────────────────────────────────────────────── #
        arm_txt = "ARMED" if s.armed else "DISARMED"
        arm_col = theme.ACCENT if s.armed else theme.LABEL

        vf  = theme.value_font(VALUE_PX)
        vf1 = theme.value_font(VALUE_PX - 1)
        uf  = theme.label_font(10)
        lf  = theme.label_font(LABEL_PX)
        sf  = theme.value_font(SUB_PX)
        bf  = theme.value_font(VALUE_PX)
        uf9 = theme.label_font(9)
        pf  = theme.label_font(9)

        bat_col = theme.VALUE
        if s.battery_remaining <= 20:   bat_col = theme.DANGER
        elif s.battery_remaining <= 35: bat_col = theme.WARN
        pct  = f"{s.battery_remaining}%"
        volt = f"{s.voltage:.1f}"

        # ALT sub-rows
        alt_rows = [("ASL", f"{s.alt_asl:.0f}"), ("WGS", f"{s.alt_wgs:.0f}")]
        def alt_row_w(pr, v):
            return _adv(pf, pr) + 6 + _adv(sf, v) + 2 + _adv(pf, "m")
        alt_cw = max(_adv(lf, "ALT"), *[alt_row_w(*r) for r in alt_rows])

        cells = [
            # (natural_content_w, draw_fn)
            (alt_cw, lambda cx, _cy=cy: self._cell_alt(p, cx, _cy, alt_rows, pf, sf, lf)),
            (max(_adv(vf, f"{s.groundspeed:.1f}") + UNIT_GAP + _adv(uf, "m/s"), _adv(lf, "GND SPD")),
             lambda cx, _cy=cy, v=f"{s.groundspeed:.1f}": self._cell_simple(p, cx, _cy, "GND SPD", v, "m/s", theme.VALUE, vf, uf, lf)),
            (max(_adv(vf, f"{s.airspeed:.1f}") + UNIT_GAP + _adv(uf, "m/s"), _adv(lf, "AIR SPD")),
             lambda cx, _cy=cy, v=f"{s.airspeed:.1f}": self._cell_simple(p, cx, _cy, "AIR SPD", v, "m/s", theme.VALUE, vf, uf, lf)),
            (max(_adv(vf, f"{s.current:.1f}") + UNIT_GAP + _adv(uf, "A"), _adv(lf, "CURR")),
             lambda cx, _cy=cy, v=f"{s.current:.1f}": self._cell_simple(p, cx, _cy, "CURR", v, "A", theme.VALUE, vf, uf, lf)),
            (max(_adv(vf, f"{s.dist_wp:.0f}") + UNIT_GAP + _adv(uf, "m"), _adv(lf, "DIST WP")),
             lambda cx, _cy=cy, v=f"{s.dist_wp:.0f}": self._cell_simple(p, cx, _cy, "DIST WP", v, "m", theme.VALUE, vf, uf, lf)),
            (max(_adv(vf, f"{s.dist_home:.0f}") + UNIT_GAP + _adv(uf, "m"), _adv(lf, "DIST HOME")),
             lambda cx, _cy=cy, v=f"{s.dist_home:.0f}": self._cell_simple(p, cx, _cy, "DIST HOME", v, "m", theme.VALUE, vf, uf, lf)),
            (max(_adv(vf1, fmt_time(s.flight_time_s)), _adv(lf, "FLIGHT TIME")),
             lambda cx, _cy=cy, v=fmt_time(s.flight_time_s): self._cell_simple(p, cx, _cy, "FLIGHT TIME", v, "", theme.VALUE, vf1, uf, lf)),
            (max(_adv(vf1, arm_txt), _adv(lf, "STATUS")),
             lambda cx, _cy=cy, t=arm_txt, c=arm_col: self._cell_simple(p, cx, _cy, "STATUS", t, "", c, vf1, uf, lf)),
            (max(_adv(vf1, s.flight_mode), _adv(lf, "MODE")),
             lambda cx, _cy=cy, v=s.flight_mode: self._cell_simple(p, cx, _cy, "MODE", v, "", theme.VALUE, vf1, uf, lf)),
            (max(_adv(lf, "BATT"), _adv(bf, pct), _adv(sf, volt) + 3 + _adv(uf9, "V")),
             lambda cx, _cy=cy: self._cell_batt(p, cx, _cy, pct, volt, bat_col, bf, sf, uf9, lf)),
        ]

        n = len(cells)
        natural_total = sum(cw for cw, _ in cells)
        # доступна ширина між кінцем лого+компасу і початком LINK
        avail = (right_end - link_block) - left_end
        # extra padding per side per cell
        extra = max(0.0, (avail - natural_total - n * 28) / (n * 2))
        pad   = 14 + extra

        # Draw cells
        x = left_end
        for cw, draw_fn in cells:
            # роздільник
            p.setPen(QPen(theme.DIVIDER, 1))
            p.drawLine(QPointF(x, bar_top + 8), QPointF(x, bar_top + BAR_H - 8))
            draw_fn(x + pad)
            x += pad + cw + pad

        # LINK (правий блок)
        p.setPen(QPen(theme.DIVIDER, 1))
        p.drawLine(QPointF(x, bar_top + 8), QPointF(x, bar_top + BAR_H - 8))
        p.setFont(lf_link); p.setPen(theme.LABEL)
        p.drawText(QPointF(right_end - link_lbl_w, cy - LABEL_DY), "LINK")
        tw = link_val_w
        tx = right_end - tw
        p.setFont(vf_link); p.setPen(link_col)
        p.drawText(QPointF(tx, cy + VALUE_DY), link_txt)
        p.setBrush(link_col); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(tx - 11, cy + VALUE_DY - 5), 3.5, 3.5)

    # ------------------------------------------------------------------ #
    #  Cell draw helpers                                                   #
    # ------------------------------------------------------------------ #
    def _cell_simple(self, p, cx, cy, label, value, unit, col, vf, uf, lf) -> None:
        p.setFont(lf); p.setPen(theme.LABEL)
        p.drawText(QPointF(cx, cy - LABEL_DY), label)
        p.setFont(vf); p.setPen(col)
        p.drawText(QPointF(cx, cy + VALUE_DY), value)
        if unit:
            vw = _adv(vf, value)
            p.setFont(uf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx + vw + UNIT_GAP, cy + VALUE_DY), unit)

    def _cell_alt(self, p, cx, cy, rows, pf, sf, lf) -> None:
        p.setFont(lf); p.setPen(theme.LABEL)
        p.drawText(QPointF(cx, cy - LABEL_DY), "ALT")
        ry = cy - 1
        for prefix, val in rows:
            xx = cx
            p.setFont(pf); p.setPen(theme.LABEL)
            p.drawText(QPointF(xx, ry), prefix)
            xx += _adv(pf, prefix) + 6
            p.setFont(sf); p.setPen(theme.VALUE)
            p.drawText(QPointF(xx, ry), val)
            xx += _adv(sf, val) + 2
            p.setFont(pf); p.setPen(theme.LABEL)
            p.drawText(QPointF(xx, ry), "m")
            ry += 14

    def _cell_batt(self, p, cx, cy, pct, volt, col, bf, sf, uf9, lf) -> None:
        p.setFont(lf); p.setPen(theme.LABEL)
        p.drawText(QPointF(cx, cy - LABEL_DY), "BATT")
        p.setFont(bf); p.setPen(col)
        p.drawText(QPointF(cx, cy + 2), pct)
        vw = _adv(sf, volt)
        p.setFont(sf); p.setPen(theme.VALUE)
        p.drawText(QPointF(cx, cy + 16), volt)
        p.setFont(uf9); p.setPen(theme.LABEL)
        p.drawText(QPointF(cx + vw + 3, cy + 16), "V")

    # ------------------------------------------------------------------ #
    #  Logo                                                               #
    # ------------------------------------------------------------------ #
    def _draw_logo(self, p, x, cy) -> float:
        pen = QPen(theme.ACCENT, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        for off in (0.0, 7.0):
            p.drawPolyline(QPolygonF([
                QPointF(x + off,     cy - 7),
                QPointF(x + off + 7, cy),
                QPointF(x + off,     cy + 7),
            ]))
        tx = x + 22
        snake_f = theme.logo_font(16)
        group_f = theme.logo_font(16)
        p.setFont(snake_f); p.setPen(QColor(238, 238, 238))
        p.drawText(QPointF(tx, cy + 6), "SNAKE")
        sw = QFontMetricsF(snake_f).horizontalAdvance("SNAKE")
        p.setFont(group_f); p.setPen(theme.LABEL)
        p.drawText(QPointF(tx + sw + 8, cy + 6), "GROUP")
        gw = QFontMetricsF(group_f).horizontalAdvance("GROUP")
        return tx + sw + 8 + gw + 6

    # ------------------------------------------------------------------ #
    #  Compass                                                            #
    # ------------------------------------------------------------------ #
    def _draw_compass(self, p, x, cy, heading) -> float:
        r = 14.0
        c = QPointF(x + r, cy)
        p.setPen(QPen(theme.COMPASS_LINE, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)
        ang    = math.radians(heading - 90)
        tip    = QPointF(c.x() + (r - 3) * math.cos(ang), c.y() + (r - 3) * math.sin(ang))
        back_l = QPointF(c.x() + 5 * math.cos(ang + 2.5), c.y() + 5 * math.sin(ang + 2.5))
        back_r = QPointF(c.x() + 5 * math.cos(ang - 2.5), c.y() + 5 * math.sin(ang - 2.5))
        p.setBrush(theme.ACCENT); p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([tip, back_l, c, back_r]))
        f = theme.value_font(11)
        p.setFont(f); p.setPen(theme.VALUE)
        htxt = f"{int(heading):03d}°"
        fm   = p.fontMetrics()
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(htxt) / 2, cy + r + 11), htxt)
        return x + 2 * r
