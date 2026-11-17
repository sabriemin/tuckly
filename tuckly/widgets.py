"""Ortak arayüz parçaları: açma/kapama düğmesi, ayar satırları, gruplar."""

from PySide6.QtCore import QRectF, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .i18n import t
from .config import THEMES, TOGGLE_ON


class Toggle(QAbstractButton):
    """iOS tarzı açma/kapama düğmesi."""

    on_color = QColor(TOGGLE_ON)       # görünüm değişince uygulama tarafından güncellenir
    fg = QColor(255, 255, 255)

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=160)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on, k = QColor(self.fg.red(), self.fg.green(), self.fg.blue(), 44), QColor(self.on_color), self._pos
        c = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                   int(off.blue() + (on.blue() - off.blue()) * k), int(off.alpha() + (255 - off.alpha()) * k))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(0, 0, 42, 24), 12, 12)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QRectF(3 + k * 18, 3.6, 18, 18))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(3 + k * 18, 3, 18, 18))


def named(w, name):
    w.setObjectName(name)
    return w


def label(text, name="rowLabel", wrap=False):
    lbl = named(QLabel(text), name)
    lbl.setWordWrap(wrap)
    return lbl


def group_label(text):
    return label(text.upper(), "groupLabel")


def make_group(rows):
    g = named(QFrame(), "group")
    g.setAttribute(Qt.WA_StyledBackground)
    lay = QVBoxLayout(g)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for i, r in enumerate(rows):
        if i:
            d = named(QFrame(), "divider")
            d.setFixedHeight(1)
            lay.addWidget(d)
        lay.addWidget(r)
    return g


def icon_label(glyph: str, name="rowIcon"):
    """Windows simge yazı tipinden tek bir simge gösteren etiket."""
    lbl = named(QLabel(glyph), name)
    lbl.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
    return lbl


def setting_row(title, desc=None, control=None, below=None, value=None, icon=None):
    """Tek tip ayar satırı: solda simge, ortada başlık ve açıklama, sağda kontrol; isteğe bağlı olarak
    başlığın altında tam genişlikte bir kontrol (kaydırıcı, liste...). Açıklama sığmazsa alt satıra geçer."""
    w = named(QWidget(), "row")
    w.setAttribute(Qt.WA_StyledBackground)
    w.row_title, w.row_desc = title, desc or ""  # ayarlarda arama için
    h = QHBoxLayout(w)
    h.setContentsMargins(14, 11, 14, 11)
    h.setSpacing(12)
    if icon:
        h.addWidget(icon_label(icon), 0, Qt.AlignTop)
    v = QVBoxLayout()
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)
    top = QHBoxLayout()
    top.setSpacing(10)
    info = QVBoxLayout()
    info.setSpacing(1)
    info.addWidget(label(title, wrap=True))
    if desc:
        info.addWidget(label(desc, "rowDesc", wrap=True))
    top.addLayout(info, 1)
    if value is not None:
        top.addWidget(value, 0, Qt.AlignVCenter)
    if control is not None:
        top.addWidget(control, 0, Qt.AlignVCenter)
    v.addLayout(top)
    if below is not None:
        if isinstance(below, QWidget):
            v.addWidget(below)
        else:
            v.addLayout(below)
    h.addLayout(v, 1)
    return w


class NavButton(QPushButton):
    """Kenar çubuğundaki sayfa düğmesi: simge + ad."""

    def __init__(self, glyph: str, text: str):
        super().__init__()
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)
        self.icon_label = named(QLabel(glyph), "navIcon")
        self.text_label = named(QLabel(text), "navText")
        for w in (self.icon_label, self.text_label):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon_label)
        lay.addWidget(self.text_label, 1)


def segmented(options, slot):
    box = named(QFrame(), "segbox")
    box.setAttribute(Qt.WA_StyledBackground)
    h = QHBoxLayout(box)
    h.setContentsMargins(2, 2, 2, 2)
    h.setSpacing(2)
    grp = QButtonGroup(box)
    for text, ident in options:
        b = named(QPushButton(t(text)), "seg")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumWidth(10)
        grp.addButton(b, ident)
        h.addWidget(b)
    grp.idClicked.connect(slot)
    return box, grp


def scroll_wrap(widget):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sc.setFrameShape(QFrame.NoFrame)
    sc.viewport().setObjectName("vp")
    sc.setWidget(widget)
    return sc


class SwatchRow(QWidget):
    """Renk seçimi: isteğe bağlı "Genel" seçeneği, hazır temalar, eklenmiş özel renkler ve "+" düğmesi."""

    picked = Signal(str)   # tema anahtarı, "#rrggbb" ya da "" (Genel)
    added = Signal(str)    # "+" ile yeni seçilen renk

    def __init__(self, with_general=False, with_add=True, columns=16):
        super().__init__()
        self.with_general, self.with_add, self.columns = with_general, with_add, columns
        self._custom, self._value = [], None
        self._lay = QGridLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(5)
        self._lay.setColumnStretch(columns, 1)
        self._cell = 0
        self._group = QButtonGroup(self)
        self._buttons = {}
        self._build()

    def _swatch(self, key, color, tip):
        b = named(QPushButton(), "swatch")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setStyleSheet(f"QPushButton#swatch {{ background: {color}; }}")
        b.clicked.connect(lambda: self._pick(key))
        self._group.addButton(b)
        self._buttons[key] = b
        self._place(b)

    def _place(self, w, span=1):
        """Bir sonraki boş hücreye yerleştirir; satır dolunca alt satıra geçer."""
        if self._cell % self.columns + span > self.columns:
            self._cell += self.columns - self._cell % self.columns
        self._lay.addWidget(w, self._cell // self.columns, self._cell % self.columns, 1, span, Qt.AlignLeft)
        self._cell += span

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                self._group.removeButton(w)
                w.deleteLater()
        self._buttons = {}
        self._cell = 0
        if self.with_general:
            b = named(QPushButton(t("Genel")), "pill")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: self._pick(""))
            self._group.addButton(b)
            self._buttons[""] = b
            self._place(b, span=3)
        for key, title, seed, _, _ in THEMES:
            self._swatch(key, seed, t(title))
        for c in self._custom[-6:]:
            self._swatch(c, c, c.upper())
        if self.with_add:
            add = named(QPushButton(t("+")), "pill")
            add.setCursor(Qt.PointingHandCursor)
            add.setToolTip(t("Yeni renk ekle"))
            add.clicked.connect(self._add)
            self._place(add, span=2)
        self.set_value(self._value)

    def _pick(self, key):
        self._value = key or None
        self.picked.emit(key)

    def _add(self):
        start = QColor(self._value) if self._value and self._value.startswith("#") else QColor("#5e8bff")
        c = QColorDialog.getColor(start, self.window(), t("Renk seç"))
        if c.isValid():
            self.added.emit(c.name())

    def set_custom(self, colors):
        if list(colors) != self._custom:
            self._custom = list(colors)
            self._build()

    def set_value(self, key):
        self._value = key or None
        b = self._buttons.get(key or "")
        if b:
            b.setChecked(True)
        else:  # listede olmayan değer: hiçbiri seçili görünmesin
            self._group.setExclusive(False)
            for x in self._buttons.values():
                x.setChecked(False)
            self._group.setExclusive(True)

    def value_name(self) -> str:
        if not self._value:
            return t("Genel") if self.with_general else ""
        if self._value.startswith("#"):
            return t("Özel ") + self._value.upper()
        return next((t(th[1]) for th in THEMES if th[0] == self._value), "")


class StyleTile(QAbstractButton):
    """Kart stilini küçük bir önizlemeyle gösteren seçim kutusu."""

    accent = QColor("#0a84ff")  # görünüm değişince uygulama tarafından güncellenir

    def __init__(self, style: str):
        super().__init__()
        self.style_key = style
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(128, 78)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        clip = QPainterPath()
        clip.addRoundedRect(r, 10, 10)
        p.setClipPath(clip)
        p.fillRect(QRectF(r.left(), r.top(), r.width() / 2, r.height()), QColor("#3f86dc"))
        p.fillRect(QRectF(r.center().x(), r.top(), r.width() / 2, r.height()), QColor("#ea9a62"))
        card = QRectF(r.left() + r.width() * 0.2, r.top() + 10, r.width() * 0.6, r.height() - 20)
        fill, edge = {
            "flat": (QColor(13, 14, 20, 235), QColor(255, 255, 255, 30)),
            "frosted": (QColor(255, 255, 255, 105), QColor(255, 255, 255, 170)),
            "liquid": (QColor(255, 255, 255, 40), QColor(255, 255, 255, 230)),
            "material": (QColor(84, 26, 38, 245), QColor(0, 0, 0, 0)),
        }[self.style_key]
        radius = 12 if self.style_key == "material" else 7
        p.setPen(QPen(edge, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(card, radius, radius)
        if self.style_key == "liquid":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(QRectF(card.left() + 3, card.top() + 3, card.width() - 6, 7), 3.5, 3.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff8a7a") if self.style_key == "material" else QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(card.left() + 10, card.top() + 14, 22, 5), 2.5, 2.5)
        p.setBrush(QColor(255, 255, 255, 130))
        p.drawRoundedRect(QRectF(card.left() + 10, card.top() + 24, 13, 5), 2.5, 2.5)
        p.setClipping(False)
        if self.isChecked():
            p.setPen(QPen(self.accent, 2.4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1.2, 1.2, -1.2, -1.2), 12, 12)
