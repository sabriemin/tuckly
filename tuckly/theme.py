"""Görünüm: temalar, stiller, renk hesabı (Look), stil sayfaları ve simgeler."""

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap

from .i18n import mark
from .config import DEFAULT_FONT, ICON_FONT, THEMES, resource
from .winapi import wallpaper_key, windows_accent

# Kart stilleri: (anahtar, görünen ad)
STYLES = (("flat", mark("Düz")), ("frosted", mark("Buzlu Cam")), ("liquid", mark("Sıvı Cam")), ("material", mark("Material You")))
ACCENT_MODES = (("theme", mark("Tema")), ("mono", mark("Tek renk")), ("system", mark("Windows")),
                ("wallpaper", mark("Duvar kâğıdı")), ("custom", mark("Özel")))

DEFAULT_APPEARANCE = {
    "style": "frosted",        # STYLES anahtarlarından biri
    "mode": "dark",            # "dark" | "light"
    "theme": "graphite",       # THEMES anahtarı ya da "#rrggbb" özel renk
    "custom_colors": [],       # kullanıcının eklediği renkler
    "accent": "theme",         # ACCENT_MODES anahtarlarından biri
    "accent_color": "#0a84ff",
    "opacity": 80,             # arka plan opaklığı, %
    "saturation": 60,          # renk doygunluğu, %
    "brightness": 40,          # arka plan parlaklığı, %
    "radius": 18,              # köşe yuvarlaklığı, piksel (0-20)
    "border": 50,              # kenarlık belirginliği, % (0: kenarlık yok)
    "tiles": True,             # dosya simgelerinin arkasında karo çizilsin mi
    "animations": True,        # geçiş ve vurgu animasyonları
    "font_family": "",         # boş: varsayılan (Segoe UI)
    "font_size": 9,            # punto
    "font_bold": False,
    "font_italic": False,
}


def appearance(config: dict) -> dict:
    """Ayarlardaki görünüm bölümünü döndürür; eksik anahtarları varsayılanla doldurur."""
    ap = config.setdefault("appearance", {})
    for k, v in DEFAULT_APPEARANCE.items():
        ap.setdefault(k, list(v) if isinstance(v, list) else v)
    return ap


def theme(key):
    for t in THEMES:
        if t[0] == key:
            return t
    return THEMES[0]


def seed_of(key: str):
    """Tema anahtarı ya da "#rrggbb" -> (tohum rengi, doygunluk katsayısı, vurgu rengi)."""
    if key and key.startswith("#"):
        c = QColor(key)
        sat = c.hslSaturationF()
        hue = max(0.0, c.hslHueF())
        accent = QColor.fromHslF(hue, max(0.55, sat), 0.68) if sat > 0.08 else QColor("#d0d0d6")
        return c, max(0.04, sat * 0.45), accent
    t = theme(key)
    return QColor(t[2]), t[3], QColor(t[4])


def rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{int(max(0, min(1, a)) * 255)})"


@dataclass
class Look:
    """Bir kartın ya da panelin çizilmesi için hesaplanmış tüm görsel değerler."""
    style: str
    light: bool
    bg: QColor
    accent: QColor
    seed: QColor
    opacity: int
    font_family: str
    font_size: float
    font_bold: bool
    font_italic: bool
    radius: int = 18
    border: int = 50
    tiles: bool = True

    @property
    def fg(self) -> str:  # ön plan (yazı ve cam katmanları) rengi, "r,g,b"
        return "20,20,26" if self.light else "255,255,255"

    @property
    def fg_color(self) -> QColor:
        return QColor(20, 20, 26) if self.light else QColor(255, 255, 255)

    @property
    def on_accent(self) -> str:  # vurgu renginin üstündeki yazı
        c = self.accent
        return "#0b0b0f" if (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 150 else "#ffffff"

    @property
    def wants_blur(self) -> bool:
        return self.style in ("frosted", "liquid")

    def font(self, delta: float = 0.0, bold=None) -> QFont:
        f = QFont(self.font_family or DEFAULT_FONT)
        f.setPointSizeF(self.font_size + delta)
        f.setBold(self.font_bold if bold is None else bold)
        f.setItalic(self.font_italic)
        return f

    def font_css(self, delta: float = 0.0, weight=None) -> str:
        w = weight if weight is not None else (700 if self.font_bold else 400)
        style = "italic" if self.font_italic else "normal"
        return (f'font-family: "{self.font_family or DEFAULT_FONT}"; font-size: {self.font_size + delta:g}pt; '
                f"font-weight: {w}; font-style: {style};")


def mix(c: QColor, other: QColor, t: float) -> QColor:
    """c rengini other rengine doğru t (0-1) kadar karıştırır."""
    return QColor(int(c.red() + (other.red() - c.red()) * t), int(c.green() + (other.green() - c.green()) * t),
                  int(c.blue() + (other.blue() - c.blue()) * t))


_wallpaper_cache = {}


def wallpaper_accent():
    """Duvar kâğıdındaki baskın canlı renk (QColor); bulunamazsa None. Sonuç dosya değişene kadar saklanır."""
    key = wallpaper_key()
    if key is None:
        return None
    if key not in _wallpaper_cache:
        _wallpaper_cache.clear()
        color = None
        img = QImage(key[0])
        if not img.isNull():
            img = img.scaled(48, 48, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB32)
            buckets = {}
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    h, s, lum = c.hslHueF(), c.hslSaturationF(), c.lightnessF()
                    if h < 0 or s < 0.25 or not 0.15 < lum < 0.85:
                        continue  # gri, çok koyu ya da çok açık pikseller vurgu rengi olmaz
                    b = buckets.setdefault(int(h * 24) % 24, [0.0, 0.0, 0.0])
                    weight = s * (1 - abs(lum - 0.5))
                    b[0] += weight
                    b[1] += h * weight
                    b[2] += s * weight
            if buckets:
                total, hue, sat = max(buckets.values(), key=lambda b: b[0])
                color = QColor.fromHslF(hue / total, min(0.9, max(0.55, sat / total)), 0.62)
        _wallpaper_cache[key] = color
    return _wallpaper_cache[key]


def make_look(ap: dict, card_theme=None, card_opacity=None) -> Look:
    """Genel görünüm ayarlarından (ve varsa kartın kendi renginden/opaklığından) Look üretir."""
    seed, satf, theme_accent = seed_of(card_theme or ap["theme"])
    light = ap["mode"] == "light"
    hue = max(0.0, seed.hslHueF())
    # Kaydırıcının tamamı etkili olsun: en doygun temada (0.45) %100 -> 0.95
    s = min(0.95, satf / 0.45 * 0.95 * ap["saturation"] / 100)
    b = ap["brightness"] / 100
    if ap["style"] == "material":
        s = min(0.95, s * 1.35)
    if light:
        bg = QColor.fromHslF(hue, s * 0.75, 0.78 + 0.18 * b)
    else:
        bg = QColor.fromHslF(hue, s, 0.05 + 0.30 * b)

    mode = ap["accent"]
    if mode == "mono":
        accent = QColor(40, 40, 48) if light else QColor(255, 255, 255)
    elif mode == "custom":
        accent = QColor(ap["accent_color"])
    elif mode == "system":
        accent = QColor(windows_accent() or "#0a84ff")
    elif mode == "wallpaper":
        accent = wallpaper_accent() or theme_accent
        if light:
            accent = accent.darker(135)
    else:
        accent = theme_accent.darker(135) if light else theme_accent
    opacity = ap["opacity"] if card_opacity is None else card_opacity
    return Look(ap["style"], light, bg, accent, seed, opacity, ap["font_family"], ap["font_size"],
                ap["font_bold"], ap["font_italic"], min(20, int(ap["radius"])), int(ap["border"]), bool(ap["tiles"]))


# ---------------------------------------------------------------- Stil sayfaları
def base_style(look: Look) -> str:
    """Kartlarda ve panelde ortak olan kontrol stilleri. Renkler ön plan rengine göre üretilir,
    böylece aynı kurallar koyu ve açık modda çalışır."""
    fg, acc, on = look.fg, look.accent.name(), look.on_accent
    hint = 150 if look.light else 120
    return f"""
* {{ font-family: "{DEFAULT_FONT}"; }}
QLabel {{ color: rgba({fg},235); font-size: 9.5pt; }}
#groupLabel {{ color: rgba({fg},{hint}); font-size: 8.5pt; font-weight: 600; padding: 0 4px; }}
#rowLabel {{ color: rgba({fg},242); font-size: 10pt; font-weight: 500; }}
#rowDesc, #hint {{ color: rgba({fg},{hint}); font-size: 8.5pt; }}
#rowValue {{ color: rgba({fg},{hint + 20}); font-size: 9pt; }}
#group {{ background: rgba({fg},10); border: 1px solid rgba({fg},16); border-radius: 12px; }}
#divider {{ background: rgba({fg},16); border: none; }}
#row {{ background: transparent; border-radius: 10px; }}
#row[flash="true"] {{ background: {rgba(look.accent, 0.28)}; }}
#rowIcon {{ font-family: {ICON_FONT}; font-size: 12pt; color: rgba({fg},{hint + 40});
           min-width: 22px; max-width: 22px; padding-top: 2px; }}
QLineEdit, QComboBox {{ background: rgba({fg},16); color: rgb({fg}); border: 1px solid rgba({fg},22);
             border-radius: 8px; padding: 6px 9px; font-size: 9.5pt;
             selection-background-color: {acc}; selection-color: {on}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {acc}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {"rgb(248,248,250)" if look.light else "rgb(24,24,30)"};
             color: rgb({fg}); border: 1px solid rgba({fg},40); selection-background-color: {acc};
             selection-color: {on}; outline: 0; }}
QPushButton {{ background: rgba({fg},40); color: rgb({fg}); border: 1px solid rgba({fg},40);
               border-radius: 8px; padding: 6px 12px; font-size: 9.5pt; font-weight: 500; }}
QPushButton:hover {{ background: rgba({fg},62); }}
QPushButton:pressed {{ background: rgba({fg},24); }}
QPushButton:disabled {{ color: rgba({fg},80); background: rgba({fg},10); }}
QPushButton#primary {{ background: {acc}; color: {on}; border: none; }}
QPushButton#primary:hover {{ background: {look.accent.lighter(112).name()}; }}
QPushButton#danger {{ background: rgb(122,34,34); color: #ffffff; border: 1px solid rgb(196,64,60); }}
QPushButton#danger:hover {{ background: rgb(170,46,44); }}
#segbox {{ background: rgba({fg},20); border: 1px solid rgba({fg},16); border-radius: 8px; }}
QPushButton#seg {{ background: transparent; border: none; border-radius: 6px; padding: 5px 8px;
                   color: rgba({fg},{hint + 20}); font-size: 9pt; font-weight: 600; }}
QPushButton#seg:hover {{ color: rgb({fg}); }}
QPushButton#seg:checked {{ background: {acc}; color: {on}; }}
QPushButton#swatch {{ min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px; padding: 0;
                      border-radius: 12px; border: 2px solid transparent; }}
QPushButton#swatch:checked {{ border: 2px solid rgb({fg}); }}
QPushButton#pill {{ padding: 3px 10px; border-radius: 11px; font-size: 8.5pt; }}
QPushButton#pill:checked {{ background: {acc}; color: {on}; border-color: {acc}; }}
QPushButton#emoji {{ padding: 0; border-radius: 8px; }}
QPushButton#emoji:checked {{ border: 2px solid {acc}; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba({fg},34); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {acc}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 1px solid rgba(0,0,0,40); width: 16px;
                             margin: -7px 0; border-radius: 9px; }}
QScrollArea {{ background: transparent; border: none; }}
#vp, #cardSettings, #page {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 3px 1px; }}
QScrollBar::handle:vertical {{ background: rgba({fg},34); border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: rgba({fg},70); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {"rgb(248,248,250)" if look.light else "rgb(24,24,30)"}; color: rgba({fg},235);
         border: 1px solid rgba({fg},36); border-radius: 10px; padding: 5px; font-size: 9.5pt; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba({fg},28); }}
QMenu::separator {{ height: 1px; background: rgba({fg},24); margin: 4px 8px; }}
QToolTip {{ background: rgb(24,24,30); color: #ffffff; border: 1px solid rgba(255,255,255,30);
            border-radius: 6px; padding: 4px 8px; }}
"""


def card_style(look: Look, blur: bool, solid: bool = False) -> str:
    """Bir kartın stil sayfası. blur: arka plan bulanıklığı etkin; solid: ayarlar açık, zemin opak.

    Renk ve opaklık her stilde burada boyanır (bulanıklık katmanı yalnızca bulanıklaştırır), böylece
    opaklık, doygunluk ve parlaklık kaydırıcıları dört stilde de aynı şekilde çalışır."""
    fg, fgc, bg, a = look.fg, look.fg_color, look.bg, look.opacity / 100
    radius = look.radius
    edge = {"flat": 0.30, "frosted": 0.45, "liquid": 0.70, "material": 0.0}[look.style]
    if solid:
        body = f"stop:0 {rgba(bg.lighter(118), 1)}, stop:0.25 {rgba(bg, 1)}, stop:1 {rgba(bg.darker(108), 1)}"
    elif look.style == "material":  # dolu, tonlu yüzey: düşük opaklıkta bile kaybolmaz
        tone = bg.darker(104) if look.light else bg.lighter(128)
        am = 0.55 + 0.45 * a
        body = f"stop:0 {rgba(tone, am)}, stop:1 {rgba(tone, am)}"
    elif look.style == "frosted":  # süt gibi pus + üstte ince parlama
        af = a * 0.92
        body = (f"stop:0 {rgba(mix(bg, fgc, 0.30), af)}, stop:0.07 {rgba(mix(bg, fgc, 0.13), af)}, "
                f"stop:1 {rgba(mix(bg, fgc, 0.08), af)}")
    elif look.style == "liquid":  # berrak gövde, üstte ve altta ışık
        al = a * 0.62
        body = (f"stop:0 {rgba(mix(bg, fgc, 0.50), min(1.0, al + 0.15))}, stop:0.05 {rgba(bg, al)}, "
                f"stop:0.82 {rgba(bg, al * 0.75)}, stop:1 {rgba(mix(bg, fgc, 0.22), al)}")
    else:  # düz
        body = f"stop:0 {rgba(bg, a)}, stop:1 {rgba(bg, a)}"
    border = f"rgba({fg},{int(look.border / 100 * edge * 255)})" if edge and look.border else "transparent"
    return base_style(look) + f"""
#fence {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, {body});
          border: 1px solid {border}; border-radius: {radius}px; }}
#fence[drop="true"] {{ border: 2px solid {look.accent.name()}; }}
#titleLock {{ font: 8pt "Segoe MDL2 Assets"; color: rgba({fg},170); }}
#titleEdit {{ padding: 2px 6px; border-radius: 6px; {look.font_css(1, 600)} }}
#title {{ background: transparent; }}
#titleText {{ color: rgb({fg}); {look.font_css(1, 600)} }}
#titleCount {{ color: {look.accent.name()}; {look.font_css(0, 700)} }}
#title QToolButton {{ color: rgba({fg},210); background: rgba({fg},24); border: none;
                      border-radius: 8px; font: 9pt "Segoe MDL2 Assets"; min-width: 26px; max-width: 26px;
                      min-height: 26px; max-height: 26px; }}
#title QToolButton:hover {{ background: rgba({fg},52); color: rgb({fg}); }}
#title QToolButton:checked {{ background: {look.accent.name()}; color: {look.on_accent}; }}
#title QToolButton#titlePencil {{ background: transparent; color: rgba({fg},120); font: 8pt "Segoe MDL2 Assets";
                                 min-width: 20px; max-width: 20px; min-height: 22px; max-height: 22px; }}
#title QToolButton#titlePencil:hover {{ background: rgba({fg},40); color: rgb({fg}); }}
FenceList {{ background: transparent; border: none; outline: 0; }}
FenceList QLineEdit {{ padding: 2px 4px; border-radius: 5px; font-size: 8.5pt;
                      background: {"rgb(250,250,252)" if look.light else "rgb(20,20,26)"}; }}
#emptyHint {{ color: rgba({fg},110); {look.font_css(0, 400)} }}
#tabs, #pathBar {{ background: transparent; }}
#pathText {{ color: rgba({fg},190); {look.font_css(-0.5, 500)} }}
#pathBar QToolButton {{ color: rgba({fg},200); background: rgba({fg},22); border: none; border-radius: 7px;
                        font: 8pt "Segoe MDL2 Assets"; min-width: 24px; max-width: 24px;
                        min-height: 22px; max-height: 22px; }}
#pathBar QToolButton:hover {{ background: rgba({fg},50); color: rgb({fg}); }}
QPushButton#tab {{ padding: 3px 8px; border: none; border-radius: 8px; background: rgba({fg},20);
                  color: rgba({fg},200); {look.font_css(-0.5, 500)} }}
QPushButton#tab:hover {{ background: rgba({fg},44); }}
QPushButton#tab:checked {{ background: {look.accent.name()}; color: {look.on_accent}; }}
QTextEdit#note {{ background: transparent; border: none; color: rgb({fg}); padding: 2px 10px 6px 12px;
                       selection-background-color: {look.accent.name()}; selection-color: {look.on_accent};
                       {look.font_css(1, 400)} }}
#noteBar {{ background: transparent; }}
#noteBar QToolButton {{ color: rgba({fg},170); background: transparent; border: none; border-radius: 6px;
                        font: 9pt "Segoe MDL2 Assets"; min-width: 24px; max-width: 24px;
                        min-height: 22px; max-height: 22px; }}
#noteBar QToolButton:hover {{ background: rgba({fg},40); color: rgb({fg}); }}
#noteBar QToolButton:checked {{ background: rgba({fg},60); color: rgb({fg}); }}
"""


def popup_style(look: Look) -> str:
    """Kart ayarları penceresinin stil sayfası: her zaman opak, okunaklı bir zemin."""
    fg = look.fg
    bg = look.bg.darker(104) if look.light else look.bg.lighter(112)
    return base_style(look) + f"""
#popup {{ background: {bg.name()}; border: 1px solid rgba({fg},56); border-radius: 14px; }}
#popupTitle {{ color: rgb({fg}); font-size: 11pt; font-weight: 600; }}
#popupSub {{ color: rgba({fg},140); font-size: 8.5pt; }}
#popupText {{ color: rgba({fg},225); font-size: 9.5pt; }}
QToolButton#popupClose {{ font: 8pt "Segoe MDL2 Assets"; color: rgba({fg},210); background: transparent;
                         border: none; border-radius: 7px; min-width: 28px; min-height: 28px; }}
QToolButton#popupClose:hover {{ background: rgba({fg},40); color: rgb({fg}); }}
"""


def panel_look(ap: dict) -> Look:
    """Kontrol paneli için görünüm: temanın rengi, ama her zaman opak ve sakin bir zemin."""
    look = make_look(ap)
    hue, s = max(0.0, look.bg.hslHueF()), look.bg.hslSaturationF()
    look.bg = QColor.fromHslF(hue, s * 0.35, 0.955) if look.light else QColor.fromHslF(hue, s * 0.45, 0.065)
    return look


def panel_style(look: Look) -> str:
    fg, bg = look.fg, look.bg
    return base_style(look) + f"""
#panel {{ background: {bg.name()}; }}
#sidebar {{ background: rgba({fg},5); border: none; border-right: 1px solid rgba({fg},22);
           outline: 0; padding: 6px 8px; }}
#sidebar::item {{ color: rgba({fg},205); padding: 8px 10px; border-radius: 8px; margin: 1px 0;
                 font-size: 10pt; font-weight: 500; }}
#sidebar::item:hover:!selected {{ background: rgba({fg},14); color: rgb({fg}); }}
#sidebar::item:selected {{ background: rgba({fg},26); color: rgb({fg}); }}
#navBtn {{ background: transparent; border: none; border-radius: 8px; padding: 0; min-height: 36px; }}
#navBtn:hover {{ background: rgba({fg},14); }}
#navBtn:checked {{ background: rgba({fg},28); }}
#navIcon {{ font-family: {ICON_FONT}; font-size: 11.5pt; color: rgba({fg},200); min-width: 20px; max-width: 20px; }}
#navText {{ color: rgba({fg},230); font-size: 10pt; font-weight: 500; }}
#search {{ padding: 6px 10px; border-radius: 8px; }}
#aboutName {{ color: rgb({fg}); font-size: 19pt; font-weight: 600; }}
#aboutSub {{ color: rgba({fg},150); font-size: 9.5pt; }}
#brand {{ color: rgb({fg}); font-size: 11pt; font-weight: 700; }}
#brandSub {{ color: rgba({fg},130); font-size: 8.5pt; }}
#pageTitle {{ color: rgb({fg}); font-size: 17pt; font-weight: 600; }}
#pageDesc {{ color: rgba({fg},150); font-size: 9.5pt; }}
#tileName {{ color: rgba({fg},220); font-size: 9pt; font-weight: 600; }}
#rowList {{ background: rgba({fg},10); border: 1px solid rgba({fg},16); border-radius: 12px;
           outline: 0; padding: 4px; color: rgba({fg},235); font-size: 10pt; }}
#rowList::item {{ padding: 8px 8px; border-radius: 8px; }}
#rowList::item:hover:!selected {{ background: rgba({fg},12); }}
#rowList::item:selected {{ background: rgba({fg},28); color: rgb({fg}); }}
#rowList::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid rgba({fg},90);
                      background: rgba({fg},10); }}
#rowList::indicator:checked {{ background: {look.accent.name()}; border-color: {look.accent.name()}; }}
#status {{ color: rgba({fg},150); font-size: 9pt; }}
"""


# ---------------------------------------------------------------- Simgeler
def make_app_icon() -> QIcon:
    ico = resource("tuckly.ico")
    if ico.exists():
        return QIcon(str(ico))
    pm = QPixmap(64, 64)  # simge dosyası yoksa basit bir yedek çizim
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(20, 21, 31))
    p.drawRoundedRect(QRectF(0, 0, 64, 64), 15, 15)
    p.setBrush(QColor("#7aa2ff"))
    p.drawRoundedRect(QRectF(19, 10, 26, 36), 6, 6)
    p.setBrush(QColor("#3a3f60"))
    p.drawRoundedRect(QRectF(10, 31, 44, 24), 8, 8)
    p.end()
    return QIcon(pm)


def dot_icon(color, size=14) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(4, 4, size * 2 - 8, size * 2 - 8))
    p.end()
    return QIcon(pm)
