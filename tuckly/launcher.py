"""Hızlı başlatıcı: bir kısayol tuşuyla açılan arama kutusu; tüm kartlardaki öğeleri yazarak bulup açar."""

from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from .i18n import t
from .theme import appearance, base_style, panel_look
from .widgets import label, named

FENCE_ROLE = Qt.UserRole + 1
MAX_RESULTS = 8


class Launcher(QWidget):
    W = 560

    def __init__(self, app):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = named(QFrame(), "launcher")
        outer.addWidget(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 12, 12, 10)
        v.setSpacing(8)
        self.edit = named(QLineEdit(), "launcherEdit")
        self.edit.setPlaceholderText(t("Kartlarda ara ve aç"))
        self.edit.textChanged.connect(self.search)
        self.edit.installEventFilter(self)
        v.addWidget(self.edit)
        self.list = named(QListWidget(), "launcherList")
        self.list.setIconSize(QSize(28, 28))
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.itemClicked.connect(self.open_item)
        v.addWidget(self.list)
        self.hint = label(t("Enter: aç   ·   ↑ ↓: seç   ·   Esc: kapat"), "launcherHint")
        v.addWidget(self.hint)

    def apply_look(self):
        look = panel_look(appearance(self.app.config))
        fg = look.fg
        self.setStyleSheet(base_style(look) + f"""
#launcher {{ background: {look.bg.name()}; border: 1px solid rgba({fg},60); border-radius: 16px; }}
#launcherEdit {{ font-size: 13pt; padding: 9px 12px; border-radius: 10px; }}
#launcherList {{ background: transparent; outline: 0; font-size: 10.5pt; color: rgba({fg},235); }}
#launcherList::item {{ padding: 6px 8px; border-radius: 8px; }}
#launcherList::item:selected {{ background: {look.accent.name()}; color: {look.on_accent}; }}
#launcherHint {{ color: rgba({fg},110); font-size: 8.5pt; padding-left: 4px; }}
""")

    # ---- Açma ve kapama
    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        self.apply_look()
        self.edit.clear()
        self.search("")
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.W // 2, geo.top() + geo.height() // 4)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def event(self, e):
        if e.type() == QEvent.WindowDeactivate and self.isVisible():
            QTimer.singleShot(0, self.hide)  # dışına tıklanınca kapanır
        return super().event(e)

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == QEvent.KeyPress:
            key = e.key()
            if key == Qt.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key_Down, Qt.Key_Up) and self.list.count():
                step = 1 if key == Qt.Key_Down else -1
                self.list.setCurrentRow((self.list.currentRow() + step) % self.list.count())
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.open_item(self.list.currentItem())
                return True
        return super().eventFilter(obj, e)

    # ---- Arama
    def entries(self):
        """(ad, yol ya da None, kart) üçlüleri: kartlardaki öğeler ve not kartları."""
        out = []
        for fence in self.app.fences:
            if fence.kind == "note":
                out.append((fence.data["name"], None, fence))
                continue
            for i in range(fence.list.count()):
                it = fence.list.item(i)
                out.append((it.text(), it.data(Qt.UserRole), fence))
        return out

    def search(self, text):
        words = text.lower().split()
        scored = []
        for name, path, fence in self.entries():
            low = name.lower()
            if path is None and words:  # not: adında ya da metninde geçiyorsa
                low += " " + fence.note.toPlainText().lower()
            if not all(w in low for w in words):
                continue
            # Adın başında eşleşenler önce, sonra sözcük başında, sonra geri kalan
            rank = 0 if words and low.startswith(words[0]) else 1 if words and any(
                part.startswith(words[0]) for part in low.split()) else 2
            scored.append((rank, name.lower(), name, path, fence))
        scored.sort(key=lambda s: s[:2])
        self.list.clear()
        for _, _, name, path, fence in scored[:MAX_RESULTS]:
            it = QListWidgetItem(f"{name}     ·  {fence.data['name']}" if path else f"{name}     ·  {t('Not')}")
            if path:
                it.setIcon(self.app.icon_for(Path(path)))
            it.setData(Qt.UserRole, path)
            it.setData(FENCE_ROLE, fence)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        row = self.list.sizeHintForRow(0) if self.list.count() else 0
        self.list.setFixedHeight(row * self.list.count())
        self.list.setVisible(self.list.count() > 0)
        # Pencere içeriği kadar yüksek olur: arama kutusu + sonuçlar + ipucu satırı
        height = 22 + self.edit.sizeHint().height() + 8 + self.hint.sizeHint().height()
        if self.list.count():
            height += row * self.list.count() + 8
        self.setFixedSize(self.W, height)

    def open_item(self, item):
        if item is None:
            return
        path, fence = item.data(Qt.UserRole), item.data(FENCE_ROLE)
        self.hide()
        if path:
            fence.open_path(path)
        else:  # not kartı: kartı görünür yap ve yazı alanına geç
            self.app.reveal(fence)
            fence.activateWindow()
            fence.note.setFocus()
