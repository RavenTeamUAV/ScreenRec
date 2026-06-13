"""Прозорий оверлей HUD у стилі NextVision OmniViewerHD.

Малюється поверх відеопотоку: нижня телеметрична панель, фірмовий логотип,
компас курсу, дата/час (ліворуч зверху) та кут камери (ліворуч по центру).
"""
from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QPen, QColor, QPolygonF, QFontMetricsF,
                           QLinearGradient)
from PySide6.QtWidgets import QWidget

from . import theme
from . import coords
from .telemetry import TelemetryState

BAR_H    = 54         # висота нижньої панелі (px)
PAD      = 17         # відступ обабіч вмісту клітинки (px)
VALUE_PX = 19         # кегль значення
SUB_PX   = 13         # кегль підзначень (ASL/WGS, напруга)
LABEL_PX = 8          # кегль підпису
UNIT_GAP = 3          # відступ перед одиницями виміру
LABEL_DY = 12         # підпис вище центру
VALUE_DY = 7          # значення нижче центру


def fmt_time(total_s: int) -> str:
    m, s = divmod(int(total_s), 60)
    return f"{m:02d}:{s:02d}"


class HudOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.state = TelemetryState()
        self.coord_fmt = "DD"   # система координат для панелі цілі

    def set_state(self, state: TelemetryState) -> None:
        self.state = state
        self.update()

    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing |
                         QPainter.RenderHint.TextAntialiasing)
        self._draw_tracking(p)
        self._draw_bottom_bar(p)
        self._draw_datetime(p)
        self._draw_camera(p)
        self._draw_target(p)
        p.end()

    # ------------------------------------------------------------------ #
    #  Нижня панель                                                       #
    # ------------------------------------------------------------------ #
    def _draw_bottom_bar(self, p: QPainter) -> None:
        w = self.width()
        h = self.height()
        bar_top = h - BAR_H
        bar = QRectF(0, bar_top, w, BAR_H)

        # м'який градієнт угорі + щільна заливка нижче (без різкої лінії)
        grad = QLinearGradient(0, bar_top - 14, 0, bar_top + 6)
        grad.setColorAt(0.0, QColor(8, 8, 8, 0))
        grad.setColorAt(1.0, theme.BAR_BG)
        p.fillRect(QRectF(0, bar_top - 14, w, 20), grad)
        p.fillRect(bar, theme.BAR_BG)

        s = self.state
        x = 14.0
        cy = bar_top + BAR_H / 2

        # --- Логотип + компас ---
        x = self._draw_logo(p, x, cy)
        x += 12
        x = self._draw_compass(p, x, cy, s.heading)
        x += 8

        # --- Телеметричні клітинки (українські підписи, як у референсі) ---
        x = self._draw_alt(p, x, bar_top, cy, s.alt_asl, s.alt_wgs)
        x = self._draw_cell(p, x, bar_top, cy, "ШВ. ЗЕМЛІ", f"{s.groundspeed:.1f}", "м/с")
        x = self._draw_cell(p, x, bar_top, cy, "ШВ. ПОЛЬОТ.", f"{s.airspeed:.1f}", "м/с")
        x = self._draw_cell(p, x, bar_top, cy, "СТРУМ", f"{s.current:.1f}", "А")
        x = self._draw_cell(p, x, bar_top, cy, "ДИСТ. ДО", f"{s.dist_wp:.0f}", "м")
        x = self._draw_cell(p, x, bar_top, cy, "ЧАС ПОЛЬОТУ", fmt_time(s.flight_time_s), "")

        # СТАТУС
        arm_txt = "ARMED" if s.armed else "DISARMED"
        arm_col = theme.ACCENT if s.armed else theme.LABEL
        x = self._draw_status(p, x, bar_top, cy, "СТАТУС", arm_txt, arm_col)

        # РЕЖИМ
        x = self._draw_status(p, x, bar_top, cy, "РЕЖИМ", s.flight_mode, theme.VALUE)

        # АКБ (% великим + напруга дрібним)
        x = self._draw_battery(p, x, bar_top, cy, s.voltage, s.battery_remaining)

        # ЗВ'ЯЗОК (правий край)
        self._draw_link(p, w - 18, cy, s.link_online)

    # ------------------------------------------------------------------ #
    #  Базові примітиви розкладки                                         #
    # ------------------------------------------------------------------ #
    def _divider(self, p: QPainter, x: float, bar_top: float) -> None:
        p.setPen(QPen(theme.DIVIDER, 1))
        p.drawLine(QPointF(x, bar_top + 10), QPointF(x, bar_top + BAR_H - 10))

    @staticmethod
    def _adv(font, text) -> float:
        return QFontMetricsF(font).horizontalAdvance(text)

    def _column(self, p, x, bar_top, content_w, draw_fn) -> float:
        """Малює роздільник, відступ, вміст (через draw_fn(content_x)) і
        повертає x наступного роздільника. Ширина клітинки = content_w."""
        self._divider(p, x, bar_top)
        content_x = x + PAD
        draw_fn(content_x)
        return content_x + content_w + PAD

    # ------------------------------------------------------------------ #
    #  Клітинки                                                           #
    # ------------------------------------------------------------------ #
    def _draw_cell(self, p, x, bar_top, cy, label, value, unit, color=None) -> float:
        color = color or theme.VALUE
        vf = theme.value_font(VALUE_PX)
        uf = theme.label_font(10)
        lf = theme.label_font(LABEL_PX)
        value_w = self._adv(vf, value)
        unit_w = (UNIT_GAP + self._adv(uf, unit)) if unit else 0.0
        content_w = max(value_w + unit_w, self._adv(lf, label))

        def draw(cx):
            p.setFont(lf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx, cy - LABEL_DY), label)
            p.setFont(vf); p.setPen(color)
            p.drawText(QPointF(cx, cy + VALUE_DY), value)
            if unit:
                p.setFont(uf); p.setPen(theme.LABEL)
                p.drawText(QPointF(cx + value_w + UNIT_GAP, cy + VALUE_DY), unit)

        return self._column(p, x, bar_top, content_w, draw)

    def _draw_alt(self, p, x, bar_top, cy, asl, wgs) -> float:
        """Висота у два рядки: ASL (барометрична) та WGS (GPS)."""
        lf = theme.label_font(LABEL_PX)
        pf = theme.label_font(9)
        sf = theme.value_font(SUB_PX)
        rows = [("ASL", f"{asl:.0f}"), ("WGS", f"{wgs:.0f}")]

        def row_w(prefix, val):
            return (self._adv(pf, prefix) + 6 + self._adv(sf, val)
                    + 2 + self._adv(pf, "м"))
        content_w = max(self._adv(lf, "ВИСОТА"), *(row_w(*r) for r in rows))

        def draw(cx):
            p.setFont(lf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx, cy - LABEL_DY), "ВИСОТА")
            ry = cy - 1
            for prefix, val in rows:
                xx = cx
                p.setFont(pf); p.setPen(theme.LABEL)
                p.drawText(QPointF(xx, ry), prefix)
                xx += self._adv(pf, prefix) + 6
                p.setFont(sf); p.setPen(theme.VALUE)
                p.drawText(QPointF(xx, ry), val)
                xx += self._adv(sf, val) + 2
                p.setFont(pf); p.setPen(theme.LABEL)
                p.drawText(QPointF(xx, ry), "м")
                ry += 14

        return self._column(p, x, bar_top, content_w, draw)

    def _draw_status(self, p, x, bar_top, cy, label, text, color) -> float:
        vf = theme.value_font(VALUE_PX - 1)
        lf = theme.label_font(LABEL_PX)
        content_w = max(self._adv(vf, text), self._adv(lf, label))

        def draw(cx):
            p.setFont(lf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx, cy - LABEL_DY), label)
            p.setFont(vf); p.setPen(color)
            p.drawText(QPointF(cx, cy + VALUE_DY), text)

        return self._column(p, x, bar_top, content_w, draw)

    def _draw_battery(self, p, x, bar_top, cy, voltage, remaining) -> float:
        """АКБ: відсоток великим, напруга дрібним під ним."""
        lf = theme.label_font(LABEL_PX)
        bf = theme.value_font(VALUE_PX)
        sf = theme.value_font(SUB_PX)
        uf = theme.label_font(9)
        col = theme.VALUE
        if remaining <= 20:
            col = theme.DANGER
        elif remaining <= 35:
            col = theme.WARN
        pct = f"{remaining}%"
        volt = f"{voltage:.1f}"
        volt_w = self._adv(sf, volt) + 3 + self._adv(uf, "В")
        content_w = max(self._adv(lf, "АКБ"), self._adv(bf, pct), volt_w)

        def draw(cx):
            p.setFont(lf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx, cy - LABEL_DY), "АКБ")
            p.setFont(bf); p.setPen(col)
            p.drawText(QPointF(cx, cy + 2), pct)
            vw = self._adv(sf, volt)
            p.setFont(sf); p.setPen(theme.VALUE)
            p.drawText(QPointF(cx, cy + 16), volt)
            p.setFont(uf); p.setPen(theme.LABEL)
            p.drawText(QPointF(cx + vw + 3, cy + 16), "В")

        return self._column(p, x, bar_top, content_w, draw)

    def _draw_link(self, p, x_right, cy, online) -> float:
        txt = "ONLINE" if online else "OFFLINE"
        col = theme.ACCENT if online else theme.DANGER
        lf = theme.label_font(LABEL_PX)
        vf = theme.value_font(VALUE_PX - 2)
        # підпис ЗВ'ЯЗОК над статусом
        p.setFont(lf); p.setPen(theme.LABEL)
        lbl = "ЗВ'ЯЗОК"
        p.drawText(QPointF(x_right - self._adv(lf, lbl), cy - LABEL_DY), lbl)
        # статус + крапка
        p.setFont(vf)
        tw = self._adv(vf, txt)
        tx = x_right - tw
        p.setPen(col)
        p.drawText(QPointF(tx, cy + VALUE_DY), txt)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(tx - 11, cy + VALUE_DY - 5), 3.5, 3.5)
        return tx

    # ------------------------------------------------------------------ #
    #  Логотип Snake Group                                                #
    # ------------------------------------------------------------------ #
    def _draw_logo(self, p, x, cy) -> float:
        # емблема — подвійний шеврон (стилізована «змійка»)
        pen = QPen(theme.ACCENT, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for off in (0.0, 7.0):
            p.drawPolyline(QPolygonF([
                QPointF(x + off, cy - 7),
                QPointF(x + off + 7, cy),
                QPointF(x + off, cy + 7),
            ]))
        tx = x + 22

        # «SNAKE» — біле, «GROUP» — сіре, з міжлітерним інтервалом
        snake_f = theme.logo_font(16)
        group_f = theme.logo_font(16)
        p.setFont(snake_f)
        p.setPen(QColor(238, 238, 238))
        p.drawText(QPointF(tx, cy + 6), "SNAKE")
        sw = QFontMetricsF(snake_f).horizontalAdvance("SNAKE")
        p.setFont(group_f)
        p.setPen(theme.LABEL)
        p.drawText(QPointF(tx + sw + 8, cy + 6), "GROUP")
        gw = QFontMetricsF(group_f).horizontalAdvance("GROUP")
        return tx + sw + 8 + gw + 6

    # ------------------------------------------------------------------ #
    #  Компас курсу                                                       #
    # ------------------------------------------------------------------ #
    def _draw_compass(self, p, x, cy, heading) -> float:
        r = 14.0
        c = QPointF(x + r, cy)
        p.setPen(QPen(theme.COMPASS_LINE, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)

        # стрілка курсу
        ang = math.radians(heading - 90)
        tip = QPointF(c.x() + (r - 3) * math.cos(ang),
                      c.y() + (r - 3) * math.sin(ang))
        back_l = QPointF(c.x() + 5 * math.cos(ang + 2.5),
                         c.y() + 5 * math.sin(ang + 2.5))
        back_r = QPointF(c.x() + 5 * math.cos(ang - 2.5),
                         c.y() + 5 * math.sin(ang - 2.5))
        p.setBrush(theme.ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([tip, back_l, c, back_r]))

        # числове значення курсу під колом
        f = theme.value_font(11)
        p.setFont(f)
        p.setPen(theme.VALUE)
        htxt = f"{int(heading):03d}°"
        fm = p.fontMetrics()
        p.drawText(QPointF(c.x() - fm.horizontalAdvance(htxt) / 2, cy + r + 11), htxt)
        return x + 2 * r

    # ------------------------------------------------------------------ #
    #  Рамка автотрекінгу (TRIP 5)                                        #
    # ------------------------------------------------------------------ #
    def _draw_tracking(self, p: QPainter) -> None:
        s = self.state
        if not s.track_active or s.track_w <= 0 or s.track_h <= 0:
            return
        w, h = self.width(), self.height()
        bw, bh = s.track_w * w, s.track_h * h
        bx = s.track_cx * w - bw / 2
        by = s.track_cy * h - bh / 2
        rect = QRectF(bx, by, bw, bh)

        # кутові «дужки» рамки
        seg = max(8.0, min(bw, bh) * 0.22)
        pen = QPen(theme.ACCENT, 2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        corners = [
            (rect.topLeft(),     (1, 0),  (0, 1)),
            (rect.topRight(),    (-1, 0), (0, 1)),
            (rect.bottomLeft(),  (1, 0),  (0, -1)),
            (rect.bottomRight(), (-1, 0), (0, -1)),
        ]
        for c, (dx1, dy1), (dx2, dy2) in corners:
            p.drawPolyline(QPolygonF([
                QPointF(c.x() + dx1 * seg, c.y() + dy1 * seg),
                c,
                QPointF(c.x() + dx2 * seg, c.y() + dy2 * seg),
            ]))

        # центральне перехрестя
        cx, cy = rect.center().x(), rect.center().y()
        p.setPen(QPen(theme.ACCENT, 1.2))
        p.drawLine(QPointF(cx - 7, cy), QPointF(cx + 7, cy))
        p.drawLine(QPointF(cx, cy - 7), QPointF(cx, cy + 7))

        # підпис над рамкою
        f = theme.label_font(10)
        p.setFont(f)
        p.setPen(theme.ACCENT)
        p.drawText(QPointF(bx, by - 6), "ЦІЛЬ • TRACK")

    # ------------------------------------------------------------------ #
    #  Напівпрозора підкладка під текст (для читабельності над відео)     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _panel(p: QPainter, rect: QRectF) -> None:
        p.setBrush(QColor(8, 8, 8, 150))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(rect, 4, 4)

    # ------------------------------------------------------------------ #
    #  Дата/час — лівий верхній кут                                       #
    # ------------------------------------------------------------------ #
    def _draw_datetime(self, p: QPainter) -> None:
        now = datetime.now()
        date_txt = now.strftime("%Y-%m-%d")
        time_txt = now.strftime("%H:%M:%S")

        x, y = 14.0, 14.0
        time_f = theme.value_font(22)
        date_f = theme.label_font(11)
        time_w = QFontMetricsF(time_f).horizontalAdvance(time_txt)
        date_w = QFontMetricsF(date_f).horizontalAdvance(date_txt)
        w = max(time_w, date_w) + 20
        self._panel(p, QRectF(x, y, w, 46))

        p.setFont(date_f)
        p.setPen(theme.LABEL)
        p.drawText(QPointF(x + 10, y + 17), date_txt)
        p.setFont(time_f)
        p.setPen(theme.VALUE)
        p.drawText(QPointF(x + 10, y + 39), time_txt)

    # ------------------------------------------------------------------ #
    #  Кут та нахил камери (gimbal) — лівий край по центру                #
    # ------------------------------------------------------------------ #
    def _draw_camera(self, p: QPainter) -> None:
        s = self.state
        x = 14.0
        pw, ph = 162.0, 156.0
        y = (self.height() - ph) / 2
        self._panel(p, QRectF(x, y, pw, ph))

        # заголовок
        p.setFont(theme.label_font(10))
        p.setPen(theme.LABEL)
        p.drawText(QPointF(x + 12, y + 18), "КАМЕРА")
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(x + 12, y + 24), QPointF(x + pw - 12, y + 24))

        # дві схеми: азимут (вид зверху) + нахил (вид збоку)
        self._gimbal_azimuth(p, x + 42, y + 62, 25, s.cam_pan)
        self._gimbal_tilt(p, x + 42, y + 120, 24, s.cam_tilt)

        # числові значення поряд
        for label, val, ry in (("PAN", s.cam_pan, y + 62), ("TILT", s.cam_tilt, y + 120)):
            p.setFont(theme.label_font(9))
            p.setPen(theme.LABEL)
            p.drawText(QPointF(x + 84, ry - 8), label)
            p.setFont(theme.value_font(20))
            p.setPen(theme.VALUE)
            p.drawText(QPointF(x + 84, ry + 12), f"{val:+.0f}°")

    def _gimbal_azimuth(self, p, cx, cy, r, pan) -> None:
        """Вид зверху: коло, ніс апарата (верх) і конус огляду камери по азимуту."""
        c = QPointF(cx, cy)
        # коло + хрест сторін
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r, r)
        for a in (0, 90, 180, 270):
            rad = math.radians(a)
            o = QPointF(cx + (r - 4) * math.cos(rad), cy - (r - 4) * math.sin(rad))
            i = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
            p.drawLine(o, i)
        # ніс апарата (вгору) — білий трикутник
        p.setBrush(QColor(230, 230, 230))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(cx, cy - r - 5), QPointF(cx - 4, cy - r + 1),
            QPointF(cx + 4, cy - r + 1)]))
        # конус огляду камери (pan: 0=вперед, за год. стрілкою)
        fov = 38.0
        center_deg = 90 - pan
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.setBrush(QColor(0, 200, 120, 70))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPie(box, int((center_deg - fov / 2) * 16), int(fov * 16))
        # промінь напрямку
        rad = math.radians(center_deg)
        tip = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
        p.setPen(QPen(theme.ACCENT, 1.8))
        p.drawLine(c, tip)
        p.setBrush(theme.ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c, 2.2, 2.2)

    def _gimbal_tilt(self, p, cx, cy, r, tilt) -> None:
        """Вид збоку: горизонт, сектор -90..+30 і промінь візування камери."""
        c = QPointF(cx, cy)
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        # сектор діапазону (вперед: від +30 вгору до -90 вниз)
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(box, int(-90 * 16), int(120 * 16))
        # лінія горизонту (вперед = праворуч) пунктиром
        pen = QPen(QColor(255, 255, 255, 70), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(c, QPointF(cx + r, cy))
        # силует апарата збоку (ніс праворуч)
        p.setBrush(QColor(230, 230, 230))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(cx - 6, cy - 3), QPointF(cx + 6, cy),
            QPointF(cx - 6, cy + 3)]))
        # промінь візування під кутом tilt (вниз = негативний)
        rad = math.radians(tilt)
        tip = QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad))
        p.setPen(QPen(theme.ACCENT, 1.8))
        p.drawLine(c, tip)
        # стрілка на кінці
        p.setBrush(theme.ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        a1 = rad + math.radians(150)
        a2 = rad - math.radians(150)
        p.drawPolygon(QPolygonF([
            tip,
            QPointF(tip.x() + 6 * math.cos(a1), tip.y() - 6 * math.sin(a1)),
            QPointF(tip.x() + 6 * math.cos(a2), tip.y() - 6 * math.sin(a2))]))

    # ------------------------------------------------------------------ #
    #  Геолокація цілі (TRIP 5) — правий край по центру                   #
    # ------------------------------------------------------------------ #
    def _draw_target(self, p: QPainter) -> None:
        s = self.state
        if not s.target_valid:
            return

        # координати у вибраній системі + решта рядків
        coord_rows = [(lbl, val, theme.VALUE)
                      for lbl, val in coords.format_coord(
                          s.target_lat, s.target_lon, self.coord_fmt)]
        rows = coord_rows + [
            ("ВИСОТА",  f"{s.target_alt:.0f} м", theme.VALUE),
            ("ДАЛЬН.",  f"{s.target_dist:.0f} м", theme.ACCENT),
            ("ПЕЛЕНГ",  f"{s.target_hdg:.0f}°", theme.VALUE),
        ]

        pw = 230.0 if self.coord_fmt in ("MGRS", "UTM") else 192.0
        ph = 36.0 + len(rows) * 21
        x = self.width() - pw - 14
        y = (self.height() - ph) / 2
        self._panel(p, QRectF(x, y, pw, ph))

        # заголовок з міткою-перехрестям
        p.setFont(theme.label_font(10))
        p.setPen(theme.ACCENT)
        p.drawText(QPointF(x + 26, y + 18), "ЦІЛЬ • TARGET")
        tcx, tcy = x + 15, y + 14
        p.setPen(QPen(theme.ACCENT, 1.4))
        p.drawEllipse(QPointF(tcx, tcy), 5, 5)
        p.drawLine(QPointF(tcx - 8, tcy), QPointF(tcx + 8, tcy))
        p.drawLine(QPointF(tcx, tcy - 8), QPointF(tcx, tcy + 8))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(x + 12, y + 26), QPointF(x + pw - 12, y + 26))

        ry = y + 44
        lf = theme.label_font(9)
        vf = theme.value_font(14)
        for label, value, col in rows:
            p.setFont(lf); p.setPen(theme.LABEL)
            p.drawText(QPointF(x + 12, ry), label)
            p.setFont(vf); p.setPen(col)
            vw = self._adv(vf, value)
            p.drawText(QPointF(x + pw - 12 - vw, ry), value)
            ry += 21
