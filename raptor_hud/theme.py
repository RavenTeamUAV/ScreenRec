"""Кольори, шрифти та геометрія HUD у стилі NextVision OmniViewerHD."""
from PySide6.QtGui import QColor, QFont, QFontDatabase

# --- Палітра -------------------------------------------------------------
BAR_BG        = QColor(8, 8, 8, 235)      # майже чорна напівпрозора панель
BAR_TOP_LINE  = QColor(255, 255, 255, 40) # тонка світла лінія зверху панелі
DIVIDER       = QColor(255, 255, 255, 35) # роздільники між полями
LABEL         = QColor(150, 150, 150)     # сірі підписи (m/s, ALT…)
VALUE         = QColor(235, 235, 235)     # білі значення
ACCENT        = QColor(0, 200, 120)       # зелений акцент (ARMED / ONLINE / курс)
WARN          = QColor(255, 138, 0)       # попередження (помаранчевий)
DANGER        = QColor(225, 55, 45)       # критично
COMPASS_LINE  = QColor(220, 220, 220)


def _pick_family(candidates: list[str]) -> str:
    available = set(QFontDatabase.families())
    for fam in candidates:
        if fam in available:
            return fam
    return "Arial"


_COND = ["Arial Narrow", "Roboto Condensed", "Helvetica Neue", "Arial"]


# Тонкий конденсований шрифт максимально близький до фірмового NextVision
def value_font(size: int, weight: int = QFont.Weight.Medium) -> QFont:
    f = QFont(_pick_family(_COND))
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 102)
    return f


def label_font(size: int) -> QFont:
    f = QFont(_pick_family(_COND))
    f.setPixelSize(size)
    f.setWeight(QFont.Weight.Normal)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 118)
    return f


def logo_font(size: int) -> QFont:
    f = QFont(_pick_family(["Helvetica Neue", "Arial"]))
    f.setPixelSize(size)
    f.setWeight(QFont.Weight.Light)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 230)
    return f
