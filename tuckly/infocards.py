"""Dosya göstermeyen kartların içerikleri: saat, takvim, hava durumu, pano ve web bağlantıları.

Her görünüm bir QWidget'tir ve kart penceresinin içine yerleşir. Renkler kartın stil sayfasından gelir.
Hava durumu Open-Meteo'dan alınır: servise yalnızca kullanıcının yazdığı şehir adı ve koordinatı gider.
Pano geçmişi yalnızca bellekte tutulur, diske yazılmaz.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QDate, QLocale, QObject, QRectF, QSize, QTime, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import DATA_DIR, _override
from .i18n import current_language, mark, t
from .widgets import named

INFO_KINDS = ("clock", "calendar", "weather", "clipboard", "links")
# Yeni kartın adı ve boyutu
KIND_DEFAULTS = {
    "clock": (mark("Saat"), 260, 160),
    "calendar": (mark("Takvim"), 300, 320),
    "weather": (mark("Hava durumu"), 300, 240),
    "clipboard": (mark("Pano"), 320, 300),
    "links": (mark("Bağlantılar"), 340, 230),
}


# "Başka kart ekle" menüsündeki adlar
KIND_MENU = {
    "clock": mark("Saat kartı"),
    "calendar": mark("Takvim kartı"),
    "weather": mark("Hava durumu kartı"),
    "clipboard": mark("Pano kartı"),
    "links": mark("Web bağlantıları kartı"),
}


def locale() -> QLocale:
    return QLocale(current_language())


# ---------------------------------------------------------------- Saat
class ClockView(QWidget):
    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 0, 12, 10)
        v.setSpacing(0)
        self.time = named(QLabel(), "clockTime")
        self.time.setAlignment(Qt.AlignCenter)
        self.date = named(QLabel(), "clockDate")
        self.date.setAlignment(Qt.AlignCenter)
        v.addStretch()
        v.addWidget(self.time)
        v.addWidget(self.date)
        v.addStretch()
        self.timer = QTimer(self, interval=1000, timeout=self.tick)
        self.timer.start()
        self.tick()

    def tick(self):
        d = self.fence.data
        fmt = ("HH:mm" if d.get("clock_24h", True) else "h:mm AP") if not d.get("clock_seconds") else (
            "HH:mm:ss" if d.get("clock_24h", True) else "h:mm:ss AP")
        self.time.setText(locale().toString(QTime.currentTime(), fmt))
        self.date.setText(locale().toString(QDate.currentDate(), "d MMMM yyyy, dddd"))

    def reload(self):
        self.tick()
        self.resizeEvent(None)

    def resizeEvent(self, e):
        if e is not None:
            super().resizeEvent(e)
        # Saat yazısı kartın boyutuna göre büyür
        chars = max(5, len(self.time.text()))
        size = max(14, min(int(self.height() * 0.42), int(self.width() * 1.55 / chars)))
        # Kartın stil sayfası yazı boyutunu belirlediği için boyut burada da stil olarak verilir
        self.time.setStyleSheet(f"font-size: {size}px; font-weight: 600;")


# ---------------------------------------------------------------- Takvim
class CalendarView(QWidget):
    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        today = QDate.currentDate()
        self.year, self.month = today.year(), today.month()
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 0, 12, 10)
        v.setSpacing(6)
        head = QHBoxLayout()
        self.prev = QToolButton(text="")
        self.next = QToolButton(text="")
        for b, step in ((self.prev, -1), (self.next, 1)):
            b.setObjectName("calNav")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=step: self.shift(s))
        self.title = named(QLabel(), "calHead")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.setToolTip(t("Bugüne dön"))
        self.title.mousePressEvent = lambda e: self.go_today()
        head.addWidget(self.prev)
        head.addWidget(self.title, 1)
        head.addWidget(self.next)
        v.addLayout(head)
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        self.heads, self.cells = [], []
        for col in range(7):
            lbl = named(QLabel(), "calWeekday")
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, 0, col)
            self.heads.append(lbl)
        for row in range(6):
            for col in range(7):
                lbl = named(QLabel(), "calDay")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setMinimumSize(20, 18)
                self.grid.addWidget(lbl, row + 1, col)
                self.cells.append(lbl)
        for row in range(1, 7):
            self.grid.setRowStretch(row, 1)
        v.addLayout(self.grid, 1)
        self._day = today
        self.timer = QTimer(self, interval=60000, timeout=self.check_day)
        self.timer.start()
        self.reload()

    def shift(self, step):
        d = QDate(self.year, self.month, 1).addMonths(step)
        self.year, self.month = d.year(), d.month()
        self.reload()

    def go_today(self):
        today = QDate.currentDate()
        self.year, self.month = today.year(), today.month()
        self.reload()

    def check_day(self):
        if QDate.currentDate() != self._day:  # gün döndü: bugünü yeniden işaretle
            self._day = QDate.currentDate()
            self.go_today()

    def reload(self):
        loc = locale()
        self.title.setText(f"{loc.standaloneMonthName(self.month)} {self.year}")
        for col, lbl in enumerate(self.heads):  # hafta pazartesi başlar
            lbl.setText(loc.dayName(col + 1, QLocale.NarrowFormat))
        first = QDate(self.year, self.month, 1)
        start = first.addDays(-(first.dayOfWeek() - 1))
        today = QDate.currentDate()
        for i, lbl in enumerate(self.cells):
            day = start.addDays(i)
            lbl.setText(str(day.day()))
            state = "today" if day == today else "in" if day.month() == self.month else "out"
            if lbl.property("state") != state:
                lbl.setProperty("state", state)
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)


# ---------------------------------------------------------------- Hava durumu
# WMO hava kodları -> (simge, açıklama)
WEATHER = (
    ((0,), "☀️", mark("Açık hava")),
    ((1, 2), "⛅", mark("Parçalı bulutlu")),
    ((3,), "☁️", mark("Bulutlu")),
    ((45, 48), "🌫️", mark("Sisli")),
    ((51, 53, 55, 56, 57), "🌦️", mark("Çisenti")),
    ((61, 63, 65, 66, 67, 80, 81, 82), "🌧️", mark("Yağmurlu")),
    ((71, 73, 75, 77, 85, 86), "🌨️", mark("Karlı")),
    ((95, 96, 99), "⛈️", mark("Fırtınalı")),
)


def describe(code):
    for codes, icon, text in WEATHER:
        if code in codes:
            return icon, t(text)
    return "🌡️", ""


class WeatherFetcher(QObject):
    """Şehri koordinata çevirir ve tahmini alır; ağ işi arka plan iş parçacığında yapılır."""

    done = Signal(dict)  # {"place", "temp", "code", "days": [(tarih, kod, en yüksek, en düşük)]} ya da {"error": ...}

    def fetch(self, city: str, fahrenheit: bool):
        threading.Thread(target=self._run, args=(city, fahrenheit), daemon=True).start()

    @staticmethod
    def _get(url):
        req = urllib.request.Request(url, headers={"User-Agent": f"Tuckly/{__version__}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    def _run(self, city, fahrenheit):
        try:
            geo = self._get("https://geocoding-api.open-meteo.com/v1/search?count=1&language="
                            f"{current_language()}&name={urllib.parse.quote(city)}")
            places = geo.get("results") or []
            if not places:
                self.done.emit({"error": "notfound"})
                return
            place = places[0]
            unit = "&temperature_unit=fahrenheit" if fahrenheit else ""
            data = self._get("https://api.open-meteo.com/v1/forecast?"
                             f"latitude={place['latitude']}&longitude={place['longitude']}"
                             "&current=temperature_2m,weather_code"
                             "&daily=weather_code,temperature_2m_max,temperature_2m_min"
                             f"&timezone=auto&forecast_days=4{unit}")
            daily = data["daily"]
            self.done.emit({
                "place": place.get("name", city),
                "temp": data["current"]["temperature_2m"],
                "code": data["current"]["weather_code"],
                "days": list(zip(daily["time"], daily["weather_code"],
                                 daily["temperature_2m_max"], daily["temperature_2m_min"])),
            })
        except Exception as ex:  # noqa: BLE001 - ağ yok, zaman aşımı, beklenmeyen yanıt
            self.done.emit({"error": str(ex)})


class WeatherView(QWidget):
    REFRESH = 30 * 60 * 1000

    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        self.status = ""  # ayarlarda gösterilen son durum
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 0, 14, 10)
        v.setSpacing(4)
        top = QHBoxLayout()
        self.icon = named(QLabel(), "wxIcon")
        self.temp = named(QLabel(), "wxTemp")
        side = QVBoxLayout()
        side.setSpacing(0)
        self.place = named(QLabel(), "wxPlace")
        self.text = named(QLabel(), "wxText")
        side.addStretch()
        side.addWidget(self.place)
        side.addWidget(self.text)
        side.addStretch()
        top.addWidget(self.icon)
        top.addWidget(self.temp)
        top.addSpacing(6)
        top.addLayout(side, 1)
        v.addLayout(top)
        self.hint = named(QLabel(), "emptyHint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        v.addWidget(self.hint, 1)
        self.days_box = QWidget()
        self.days = QHBoxLayout(self.days_box)
        self.days.setContentsMargins(0, 4, 0, 0)
        self.days.setSpacing(4)
        self.day_labels = []
        for _ in range(3):
            lbl = named(QLabel(), "wxDay")
            lbl.setAlignment(Qt.AlignCenter)
            self.days.addWidget(lbl, 1)
            self.day_labels.append(lbl)
        v.addWidget(self.days_box)
        v.addStretch()
        self.fetcher = WeatherFetcher()
        self.fetcher.done.connect(self.show_data)
        self.timer = QTimer(self, interval=self.REFRESH, timeout=self.update_now)
        self.timer.start()
        self.show_data(None)
        QTimer.singleShot(1500, self.update_now)

    def reload(self):
        self.update_now()

    def update_now(self):
        city = (self.fence.data.get("city") or "").strip()
        if not city:
            self.show_data(None)
        elif not _override:  # testler internete çıkmaz
            self.fetcher.fetch(city, self.fence.data.get("fahrenheit", False))

    def show_data(self, data):
        ok = bool(data) and "error" not in data
        for w in (self.icon, self.temp, self.place, self.text, self.days_box):
            w.setVisible(ok)
        self.hint.setVisible(not ok)
        if not ok:
            city = (self.fence.data.get("city") or "").strip()
            if not city:
                self.hint.setText(t("Kart ayarlarından şehir yazın."))
                self.status = ""
            elif data and data.get("error") == "notfound":
                self.hint.setText(t("“{0}” bulunamadı.").format(city))
                self.status = self.hint.text()
            elif data:
                self.hint.setText(t("Hava durumu alınamadı. İnternet bağlantısını denetleyin."))
                self.status = self.hint.text()
            else:
                self.hint.setText(t("Hava durumu alınıyor…"))
            return
        unit = "°F" if self.fence.data.get("fahrenheit") else "°C"
        icon, text = describe(data["code"])
        self.icon.setText(icon)
        self.temp.setText(f"{round(data['temp'])}{unit}")
        self.place.setText(data["place"])
        self.text.setText(text)
        loc = locale()
        for lbl, (day, code, high, low) in zip(self.day_labels, data["days"][1:4]):
            name = loc.dayName(QDate.fromString(day, "yyyy-MM-dd").dayOfWeek(), QLocale.ShortFormat)
            lbl.setText(f"{name}\n{describe(code)[0]}\n{round(high)}° / {round(low)}°")
        self.status = t("Güncellendi: {0}").format(time.strftime("%H:%M"))


# ---------------------------------------------------------------- Pano
class ClipboardView(QWidget):
    LIMIT, MAX_CHARS = 20, 5000

    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        self._own = None  # karttan panoya geri koyduğumuz metin: yeniden listelenmesin
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 0, 8, 8)
        v.setSpacing(4)
        self.list = named(QListWidget(), "clipList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.on_menu)
        self.list.itemClicked.connect(self.copy_item)
        self.hint = named(QLabel(t("Kopyaladığınız metinler burada listelenir. Tıklayınca yeniden kopyalanır.")),
                          "emptyHint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        v.addWidget(self.list, 1)
        v.addWidget(self.hint, 1)
        self.list.hide()
        QApplication.clipboard().dataChanged.connect(self.on_clipboard)

    def reload(self):
        pass

    def on_clipboard(self):
        text = QApplication.clipboard().text()
        if not text or not text.strip() or len(text) > self.MAX_CHARS or text == self._own:
            return
        self.add(text)

    def add(self, text):
        for i in range(self.list.count()):  # aynı metin yeniden kopyalandıysa başa al
            if self.list.item(i).data(Qt.UserRole) == text:
                self.list.takeItem(i)
                break
        shown = " ".join(text.split())
        it = QListWidgetItem(shown[:140] + ("…" if len(shown) > 140 else ""))
        it.setData(Qt.UserRole, text)
        it.setToolTip(text[:600])
        self.list.insertItem(0, it)
        while self.list.count() > self.LIMIT:
            self.list.takeItem(self.list.count() - 1)
        self._sync()

    def _sync(self):
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.hint.setVisible(not has)
        self.fence.title.count.setText(str(self.list.count()) if has else "")
        self.fence.title.fit()

    def copy_item(self, item):
        self._own = item.data(Qt.UserRole)
        QApplication.clipboard().setText(self._own)
        self.fence.app.notify(t("Panoya kopyalandı."))

    def clear(self):
        self.list.clear()
        self._sync()

    def on_menu(self, pos):
        it = self.list.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            m.addAction(t("Kopyala"), lambda: self.copy_item(it))
            m.addAction(t("Listeden kaldır"), lambda: (self.list.takeItem(self.list.row(it)), self._sync()))
            m.addSeparator()
        m.addAction(t("Tümünü temizle"), self.clear)
        m.exec(self.list.viewport().mapToGlobal(pos))


# ---------------------------------------------------------------- Web bağlantıları
def normalize_url(text: str):
    """Yazılan adresi tam bir http(s) adresine çevirir; adres değilse None."""
    text = (text or "").strip()
    if not text or " " in text:
        return None
    if "://" not in text:
        text = "https://" + text
    url = QUrl(text)
    if url.scheme() not in ("http", "https") or "." not in url.host():
        return None
    return url.toString()


def host_title(url: str) -> str:
    parts = QUrl(url).host().split(".")
    if len(parts) < 2:
        return url
    # Alan adının asıl kısmı: news.ycombinator.com -> Ycombinator, bbc.co.uk -> Bbc
    index = -3 if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "edu") else -2
    return parts[index].capitalize()


def letter_icon(title: str, url: str, size=64) -> QIcon:
    """Site simgesi yokken: sitenin baş harfini taşıyan renkli karo."""
    hue = sum(ord(c) for c in QUrl(url).host()) * 37 % 360
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor.fromHsl(hue, 150, 120))
    p.drawRoundedRect(QRectF(4, 4, size - 8, size - 8), 14, 14)
    f = QFont("Segoe UI Variable Display")
    f.setPixelSize(int(size * 0.5))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (title[:1] or "?").upper())
    p.end()
    return QIcon(pm)


class FaviconFetcher(QObject):
    """Sitenin kendi /favicon.ico dosyasını indirir ve ayar klasöründe saklar."""

    done = Signal(str)  # host

    @staticmethod
    def path(host: str) -> Path:
        return DATA_DIR / "favicons" / (host.replace(":", "_") + ".ico")

    def fetch(self, host: str):
        if _override or not host:  # testler internete çıkmaz
            return
        threading.Thread(target=self._run, args=(host,), daemon=True).start()

    def _run(self, host):
        try:
            req = urllib.request.Request(f"https://{host}/favicon.ico", headers={"User-Agent": f"Tuckly/{__version__}"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read(512 * 1024)
            if len(data) < 64:
                return
            target = self.path(host)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.done.emit(host)
        except Exception:  # noqa: BLE001 - simge yoksa harfli karo kalır
            pass


class LinksView(QWidget):
    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 0, 4, 6)
        self.list = named(QListWidget(), "linkList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.setIconSize(QSize(36, 36))
        self.list.setGridSize(QSize(82, 78))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.on_menu)
        self.list.itemDoubleClicked.connect(lambda it: self.open(it.data(Qt.UserRole)))
        self.hint = named(QLabel(t("Tarayıcıdan bir adresi buraya sürükleyin ya da kart ayarlarından ekleyin.")),
                          "emptyHint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        v.addWidget(self.list, 1)
        v.addWidget(self.hint, 1)
        self.favicons = FaviconFetcher()
        self.favicons.done.connect(lambda host: self.reload())
        self._asked = set()
        self.reload()

    def links(self) -> list:
        return self.fence.data.setdefault("links", [])

    def reload(self):
        self.list.clear()
        for link in self.links():
            host = QUrl(link["url"]).host()
            icon_file = FaviconFetcher.path(host)
            icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
            if icon.isNull() or not icon.availableSizes():
                icon = letter_icon(link["title"], link["url"])
                if host not in self._asked:
                    self._asked.add(host)
                    self.favicons.fetch(host)
            it = QListWidgetItem(icon, link["title"])
            it.setData(Qt.UserRole, link["url"])
            it.setToolTip(link["url"])
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.list.addItem(it)
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.hint.setVisible(not has)
        self.fence.title.count.setText(str(self.list.count()) if has else "")
        self.fence.title.fit()

    def add(self, text, title=None) -> bool:
        url = normalize_url(text)
        if not url or self.fence.data.get("lock_content"):
            return False
        if any(link["url"] == url for link in self.links()):
            return True
        self.links().append({"title": (title or host_title(url))[:40], "url": url})
        self.fence.app.save()
        self.reload()
        return True

    def remove(self, url):
        self.fence.data["links"] = [link for link in self.links() if link["url"] != url]
        self.fence.app.save()
        self.reload()

    @staticmethod
    def open(url):
        QDesktopServices.openUrl(QUrl(url))

    def on_menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        url = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction(t("Aç"), lambda: self.open(url))
        m.addAction(t("Adresi kopyala"), lambda: QApplication.clipboard().setText(url))
        if not self.fence.data.get("lock_content"):
            m.addSeparator()
            m.addAction(t("Karttan kaldır"), lambda: self.remove(url))
        m.exec(self.list.viewport().mapToGlobal(pos))

    # Tarayıcıdan sürüklenen adres
    def _dragged(self, mime):
        if mime.hasUrls():
            for u in mime.urls():
                if u.scheme() in ("http", "https"):
                    return u.toString()
        return normalize_url(mime.text()) if mime.hasText() and mime.text().startswith("http") else None

    def dragEnterEvent(self, e):
        if self._dragged(e.mimeData()) and not self.fence.data.get("lock_content"):
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        url = self._dragged(e.mimeData())
        if url and self.add(url):
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()


VIEWS = {"clock": ClockView, "calendar": CalendarView, "weather": WeatherView, "clipboard": ClipboardView,
         "links": LinksView}
