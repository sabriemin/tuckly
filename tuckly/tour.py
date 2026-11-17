"""Rehber turu: Tuckly'yi ekranda adım adım tanıtan küçük bir açıklama balonu ve vurgulama çerçevesi."""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QToolButton, QVBoxLayout, QWidget

from .i18n import t
from .theme import appearance, make_look, popup_style
from .widgets import label, named


class HighlightRing(QWidget):
    """Hedef bileşenin çevresine çizilen, tıklamaları engellemeyen vurgu çerçevesi."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.color = QColor("#0a84ff")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.color, 3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)


class CoachBubble(QWidget):
    """Tur adımının başlığını, açıklamasını ve ileri/geri düğmelerini gösteren pencere."""

    WIDTH = 340

    def __init__(self, tour):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.tour = tour
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(self.WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = named(QFrame(), "popup")
        outer.addWidget(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(18, 14, 14, 14)
        v.setSpacing(8)
        head = QHBoxLayout()
        self.title = label("", "popupTitle", wrap=True)
        head.addWidget(self.title, 1)
        close = named(QToolButton(text=""), "popupClose")
        close.setCursor(Qt.PointingHandCursor)
        close.setToolTip(t("Turu kapat"))
        close.clicked.connect(tour.finish)
        head.addWidget(close, 0, Qt.AlignTop)
        v.addLayout(head)
        self.text = label("", "popupText", wrap=True)
        v.addWidget(self.text)
        v.addSpacing(4)
        foot = QHBoxLayout()
        foot.setSpacing(6)
        self.counter = label("", "popupSub")
        foot.addWidget(self.counter, 1)
        self.back = QPushButton(t("Geri"))
        self.back.setCursor(Qt.PointingHandCursor)
        self.back.clicked.connect(tour.previous)
        foot.addWidget(self.back)
        self.next = named(QPushButton(t("İleri")), "primary")
        self.next.setCursor(Qt.PointingHandCursor)
        self.next.clicked.connect(tour.advance)
        foot.addWidget(self.next)
        v.addLayout(foot)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.tour.finish()
        else:
            super().keyPressEvent(e)


class Tour:
    """Adımları sırayla gösterir. Hedefi olmayan adımlar ekranın ortasında görünür; hedefi o an
    bulunmayan adımlar (örneğin hiç kart yoksa) atlanır."""

    def __init__(self, app):
        self.app = app
        self.bubble = None
        self.ring = None
        self.index = 0
        self.steps = []

    # Her adım: (başlık, açıklama, hedefi döndüren işlev ya da None, adımdan önce çalışacak işlev ya da None)
    def _build_steps(self):
        app = self.app

        def card():
            return next((f for f in app.fences if f.kind != "rest" and f.isVisible()), None)

        def card_part(get):
            return lambda: (get(card()) if card() else None)

        return [
            (t("Tuckly'ye hoş geldiniz"),
             t("Bu kısa tur kartları ve ayarları tanıtır. İstediğiniz an kapatabilirsiniz."), None, None),
            (t("Kartlar"),
             t("Kartlar masaüstünüzdeki öğeleri gruplar. Bir dosyayı ya da kısayolu kartın üzerine sürükleyin; "
               "dosya yerinde kalır, simgesi kartta görünür."), card, None),
            (t("Taşıma ve ad"),
             t("Kartı başlığından sürükleyerek taşıyın. Adın yanındaki kalem adı değiştirir; başlığa çift "
               "tıklamak kartı daraltır."), card_part(lambda f: f.title), None),
            (t("Kart ayarları"),
             t("Dişli düğmesi bu kartın rengini, opaklığını, sıralamasını, kategorilerini ve kilitlerini açar."),
             card_part(lambda f: f.title.gear), None),
            (t("Kontrol paneli"),
             t("Tüm kartlar, görünüm, masaüstünü düzenleme ve seçenekler burada. Tepsideki Tuckly simgesine "
               "tıklayarak açabilirsiniz."), lambda: app.panel.nav[0].parentWidget(), lambda: app.show_panel(page=0)),
            (t("Görünüm"),
             t("Stil, renk, opaklık ve yazı tipini buradan değiştirin. Değişiklikler anında uygulanır."),
             lambda: app.panel.pages, lambda: app.show_panel(page=1)),
            (t("Hazırsınız"),
             t("Masaüstünde boş alana sağ tıklayıp “Yeni Tuckly kartı” ile de kart ekleyebilirsiniz. Bu turu "
               "Rehber sayfasından yeniden başlatabilirsiniz."), None, None),
        ]

    def start(self):
        self.finish()
        self.steps = self._build_steps()
        self.bubble = CoachBubble(self)
        self.ring = HighlightRing()
        look = make_look(appearance(self.app.config))
        self.bubble.setStyleSheet(popup_style(look))
        self.ring.color = look.accent
        self.index = 0
        self._show(+1)

    def active(self) -> bool:
        return self.bubble is not None

    def finish(self):
        for w in (self.bubble, self.ring):
            if w is not None:
                w.hide()
                w.deleteLater()
        self.bubble = self.ring = None

    def advance(self):
        if self.index >= len(self.steps) - 1:
            self.finish()
            return
        self.index += 1
        self._show(+1)

    def previous(self):
        if self.index > 0:
            self.index -= 1
            self._show(-1)

    def _show(self, direction):
        # Hedefi bulunamayan adımları geç
        while 0 <= self.index < len(self.steps):
            title, text, target, before = self.steps[self.index]
            if before:
                before()
            widget = target() if target else None
            if target is None or widget is not None:
                break
            self.index += direction
        else:
            self.finish()
            return
        b = self.bubble
        b.title.setText(title)
        b.text.setText(text)
        b.counter.setText(f"{self.index + 1} / {len(self.steps)}")
        b.back.setVisible(self.index > 0)
        b.next.setText(t("Bitir") if self.index == len(self.steps) - 1 else t("İleri"))
        b.adjustSize()
        if widget is None:
            self.ring.hide()
            geo = QGuiApplication.primaryScreen().availableGeometry()
            b.move(geo.center() - QPoint(b.width() // 2, b.height() // 2))
        else:
            rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size()).adjusted(-6, -6, 6, 6)
            self.ring.setGeometry(rect)
            self.ring.show()
            b.move(self._beside(rect, b))
        b.show()
        b.raise_()
        b.activateWindow()

    @staticmethod
    def _beside(rect: QRect, bubble) -> QPoint:
        """Balonu hedefin sağına, sığmazsa soluna, o da olmazsa altına ya da üstüne yerleştirir."""
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        w, h, gap = bubble.width(), bubble.height(), 12
        y = max(geo.top() + 8, min(rect.top(), geo.bottom() - h - 8))
        if rect.right() + gap + w <= geo.right():
            return QPoint(rect.right() + gap, y)
        if rect.left() - gap - w >= geo.left():
            return QPoint(rect.left() - gap - w, y)
        x = max(geo.left() + 8, min(rect.center().x() - w // 2, geo.right() - w - 8))
        if rect.bottom() + gap + h <= geo.bottom():
            return QPoint(x, rect.bottom() + gap)
        return QPoint(x, max(geo.top() + 8, rect.top() - gap - h))
