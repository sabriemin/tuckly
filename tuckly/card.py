"""Masaüstü kartı: başlık çubuğu, dosya listesi ve kart penceresi."""

import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QFileSystemWatcher,
    QMimeData,
    QPoint,
    QRect,
    QRectF,
    QSize,
    QTimer,
    QUrl,
    Qt,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import t
from .config import ICON_SIZES, SKIP_NAMES, TITLE_H
from .utils import is_hidden, norm, safe_name, snap, unique_dest
from .winapi import (
    GWL_HWNDPARENT,
    HWND_BOTTOM,
    SWP_NOZORDER,
    WINDOWPOS,
    WM_WINDOWPOSCHANGING,
    _SetWindowLongPtr,
    desktop_dir,
    desktop_entries,
    on_desktop,
    recycle,
    set_acrylic,
    set_window_region,
    user32,
)
from .theme import appearance, card_style, make_look, popup_style
from .widgets import label, named, scroll_wrap
from .card_settings import CardSettings
from .notifications import matches

BADGE_ROLE = Qt.UserRole + 1  # öğenin bildirim sayısı


from dataclasses import replace

from .note import NoteEdit

class TileDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.look = None  # kartın görünümü; FenceWindow.apply_settings tarafından verilir

    def geometry(self, rect):
        s = self.view.iconSize().width()
        tile = s + 18
        tx = rect.x() + (rect.width() - tile) // 2
        ty = rect.y() + 4
        return s, tile, QRect(tx, ty, tile, tile), QRect(rect.x() + 3, ty + tile + 5, rect.width() - 6,
                                                          rect.bottom() - (ty + tile + 5))

    def paint(self, p, opt, idx):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        s, tile, tr, text_rect = self.geometry(opt.rect)
        sel = bool(opt.state & QStyle.State_Selected)
        h = self.view.hover_amount(idx.row())  # 0-1: üzerine gelme animasyonunun ilerlemesi
        hov = h > 0.01
        fg = self.look.fg_color if self.look else QColor(255, 255, 255)

        def tone(alpha):
            return QColor(fg.red(), fg.green(), fg.blue(), alpha)

        if sel:
            bg = QColor(self.look.accent if self.look else QColor("#0a84ff"))
            bg.setAlpha(150)
        else:
            bg = tone(int(24 + 26 * h) if (not self.look or self.look.tiles) else int(50 * h))
        if sel or hov or not self.look or self.look.tiles:  # karolar kapalıysa yalnızca üstüne gelince çiz
            p.setPen(QPen(tone(40 if sel else int(18 + 30 * h)), 1))
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(tr).adjusted(0.5, 0.5, -0.5, -0.5), tile * 0.32, tile * 0.32)
        icon = idx.data(Qt.DecorationRole)
        if icon:
            k = 1 + 0.14 * h  # üzerine gelince büyür
            side = s * k
            c = QRectF(tr).center()
            icon.paint(p, QRectF(c.x() - side / 2, c.y() - side / 2, side, side).toRect())
        badge = idx.data(BADGE_ROLE)
        if badge:  # bildirim sayısı rozeti: karonun sağ üst köşesinde
            text_b = "99+" if badge > 99 else str(badge)
            bf = QFont(opt.font)
            bf.setPointSizeF(7.5)
            bf.setBold(True)
            bw = max(17, QFontMetrics(bf).horizontalAdvance(text_b) + 9)
            br = QRectF(tr.right() - bw + 6, tr.top() - 5, bw, 17)
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            p.setBrush(QColor("#ff3b30"))
            p.drawRoundedRect(br, 8.5, 8.5)
            p.setFont(bf)
            p.setPen(QColor("#ffffff"))
            p.drawText(br, Qt.AlignCenter, text_b)
        f = self.look.font(-0.5) if self.look else QFont(opt.font)
        p.setFont(f)
        fm = QFontMetrics(f)
        text = idx.data(Qt.DisplayRole) or ""
        lines, rest, w = [], text, text_rect.width()
        while rest and len(lines) < 2:
            if fm.horizontalAdvance(rest) <= w or len(lines) == 1:
                lines.append(fm.elidedText(rest, Qt.ElideRight, w))
                break
            cut = len(rest)
            while cut > 1 and fm.horizontalAdvance(rest[:cut]) > w:
                cut -= 1
            sp = rest.rfind(" ", 0, cut)
            cut = sp + 1 if sp > 0 else cut
            lines.append(rest[:cut].rstrip())
            rest = rest[cut:]
        shadow = not (self.look and self.look.light)  # saydam kartta yazı duvar kâğıdına karışmasın
        y = text_rect.y()
        for ln in lines:
            if shadow:
                p.setPen(QColor(0, 0, 0, 170))
                p.drawText(QRect(text_rect.x(), y + 1, w, fm.height()), Qt.AlignHCenter, ln)
            p.setPen(tone(250 if sel else 232))
            p.drawText(QRect(text_rect.x(), y, w, fm.height()), Qt.AlignHCenter, ln)
            y += fm.height()
        p.restore()

    def sizeHint(self, opt, idx):
        return self.view.gridSize()

    def updateEditorGeometry(self, editor, opt, idx):
        _, _, _, text_rect = self.geometry(opt.rect)
        editor.setGeometry(text_rect.adjusted(-2, -2, 2, 0).intersected(opt.rect))


class FenceList(QListWidget):
    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.delegate = TileDelegate(self)
        self.setItemDelegate(self.delegate)
        # Büyüme efekti: satır -> üzerine gelme ilerlemesi (0-1)
        self._hover_row, self._hover = -1, {}
        self._ticker = QTimer(self, interval=16, timeout=self._tick)
        self.setViewportMargins(6, 0, 6, 4)

    def apply_icon_size(self, s: int, look=None):
        self.setIconSize(QSize(s, s))
        line = QFontMetrics(look.font(-0.5)).height() if look else 15
        extra = int(max(0, (look.font_size if look else 9) - 9) * 7)  # büyük yazıda karolar genişler
        self.setGridSize(QSize(s + 46 + extra, s + 18 + 4 + 5 + 2 * line + 2))

    # ---- Animasyonlar
    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        self._set_hover(self.indexAt(e.position().toPoint()).row())

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._set_hover(-1)

    def _set_hover(self, row):
        if row != self._hover_row:
            self._hover_row = row
            if row >= 0:
                self._hover.setdefault(row, 0.0)
            self._ticker.start()

    def reset_animation(self):
        self._hover_row, self._hover = -1, {}

    def _tick(self):
        smooth = self.fence.app.animations
        active = False
        for row in list(self._hover):
            target = 1.0 if row == self._hover_row else 0.0
            v = self._hover[row]
            v = v + (target - v) * 0.32 if smooth else target
            if abs(target - v) < 0.02:
                v = target
            # Yalnızca bu karonun alanı yeniden çizilir (büyüyen simge için küçük bir pay bırakılır)
            self.viewport().update(self.visualRect(self.model().index(row, 0)).adjusted(-6, -6, 6, 6))
            if v == 0.0 and target == 0.0:
                del self._hover[row]
            else:
                self._hover[row] = v
                active = active or v != target
        if not active:
            self._ticker.stop()

    def hover_amount(self, row) -> float:
        return self._hover.get(row, 0.0)

    def mimeData(self, items):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(i.data(Qt.UserRole)) for i in items])
        return md

    def mimeTypes(self):
        return ["text/uri-list"]

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def startDrag(self, actions):
        items = self.selectedItems()
        if not items:
            return
        paths = [Path(i.data(Qt.UserRole)) for i in items]
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(items))
        icon = items[0].icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(self.iconSize()))
        drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
        # Kartlar dışına (masaüstüne/Gezgin'e) bırakıldı: masaüstünde duran dosya karttan çıkar
        if drag.target() is None and self.fence.kind == "desktop":
            for p in paths:
                if p.exists() and on_desktop(p):
                    self.fence.app.assign(p, None)
        QTimer.singleShot(300, self.fence.app.refresh_all)

    def _drop_action(self, e):
        if self.fence.kind == "folder":  # klasör kartı dosyayı gerçekten taşır/kopyalar
            return Qt.CopyAction if e.modifiers() & Qt.ControlModifier else Qt.MoveAction
        # Masaüstü kartı dosyayı yerinden oynatmaz. Kaynağa "taşındı" bildirilirse Gezgin asıl
        # dosyayı siler; bu yüzden burada asla MoveAction bildirilmez.
        return Qt.LinkAction if e.possibleActions() & Qt.LinkAction else Qt.CopyAction

    def dragEnterEvent(self, e):
        if not e.mimeData().hasUrls() or self.fence.data.get("lock_content") or self.fence.kind == "note":
            e.ignore()
            return
        self.fence.begin_peek()  # üzerine gelince açılan kart sürüklemede de açılsın
        self.fence.set_drop_highlight(True)
        # Kart içinde sürükleme: yeniden sıralama (dosyaya dokunulmaz)
        e.setDropAction(Qt.MoveAction if e.source() is self else self._drop_action(e))
        e.accept()

    dragMoveEvent = dragEnterEvent

    def dragLeaveEvent(self, e):
        super().dragLeaveEvent(e)
        self.fence.set_drop_highlight(False)

    def dropEvent(self, e):
        self.fence.set_drop_highlight(False)
        if not e.mimeData().hasUrls() or self.fence.data.get("lock_content") or self.fence.kind == "note":
            e.ignore()
            return
        if e.source() is self:
            row = self.indexAt(e.position().toPoint()).row()
            paths = [it.data(Qt.UserRole) for it in self.selectedItems()]
            e.setDropAction(Qt.MoveAction)
            e.accept()
            QTimer.singleShot(0, lambda: self.fence.reorder(paths, row))
            return
        copy = bool(e.modifiers() & Qt.ControlModifier)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.setDropAction(self._drop_action(e))
        e.accept()
        QTimer.singleShot(0, lambda: self.fence.receive(paths, copy))


class TitleBar(QWidget):
    def __init__(self, fence):
        super().__init__()
        self.fence = fence
        self.setObjectName("title")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(TITLE_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(6)
        self.text = named(QLabel(), "titleText")
        self.edit = named(QLineEdit(), "titleEdit")  # kalem düğmesiyle açılan yerinde ad düzenleme
        self.edit.hide()
        self.edit.setMaxLength(60)
        self.edit.editingFinished.connect(lambda: self.finish_rename(True))
        self.edit.installEventFilter(self)
        self.pencil = named(QToolButton(text="\uE70F"), "titlePencil")
        self.pencil.setToolTip(t("Kartın adını değiştir"))
        self.pencil.setCursor(Qt.PointingHandCursor)
        self.pencil.clicked.connect(self.start_rename)
        self.count = named(QLabel(), "titleCount")
        self.lock = named(QLabel("\uE72E"), "titleLock")  # kilit simgesi (Segoe MDL2 Assets)
        self.lock.setToolTip(t("Bu kartta kilit açık"))
        self.lock.hide()
        self.find = named(QLineEdit(), "titleEdit")  # kart içinde arama; büyüteç düğmesiyle açılır
        self.find.hide()
        self.find.setPlaceholderText(t("Kartta ara"))
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(fence.apply_filter)
        self.find.editingFinished.connect(self.finish_search)
        self.find.installEventFilter(self)
        lay.addWidget(self.text)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.find, 1)
        lay.addWidget(self.pencil)
        lay.addWidget(self.count)
        lay.addWidget(self.lock)
        lay.addStretch()
        self.gear = QToolButton(text="\uE713")
        self.gear.setToolTip(t("Kart ayarları"))
        self.gear.setCheckable(True)
        self.gear.setCursor(Qt.PointingHandCursor)
        self.gear.clicked.connect(lambda on: fence.show_settings(on))
        self.fold = QToolButton(text="\uE70D")
        self.fold.setToolTip(t("Daralt / genişlet"))
        self.fold.setCursor(Qt.PointingHandCursor)
        self.fold.clicked.connect(fence.toggle_collapsed)
        self.search = QToolButton(text="\uE721")  # yalnızca kalabalık kartta görünür
        self.search.setToolTip(t("Kartta ara"))
        self.search.setCursor(Qt.PointingHandCursor)
        self.search.clicked.connect(self.start_search)
        self.search.hide()
        lay.addWidget(self.search)
        lay.addWidget(self.gear)
        lay.addWidget(self.fold)
        self._drag = None
        self._moved = False
        self._snapped = (False, False)  # taşırken yatay/dikey olarak bir kenara yapıştı mı
        self._name = ""
        self._hover = False

    # ---- Ad: sığmazsa "…" ile kısalır; dar kartta kalem yalnızca başlığın üzerine gelince görünür
    def set_name(self, name: str):
        self._name = name
        self.fit()

    def fit(self):
        if not self.edit.isHidden() or not self.find.isHidden():
            return
        lay = self.layout()
        m, sp = lay.contentsMargins(), lay.spacing()
        fixed = m.left() + m.right() + 26 + 26 + 2 * sp  # ayar ve daralt düğmeleri
        if not self.search.isHidden():
            fixed += 26 + sp
        if self.count.text():
            self.count.adjustSize()
            fixed += self.count.sizeHint().width() + sp
        if not self.lock.isHidden():
            fixed += self.lock.sizeHint().width() + sp
        fm = self.text.fontMetrics()
        need = fm.horizontalAdvance(self._name) + 4
        pencil = 20 + sp
        room = self.width() - fixed
        show_pencil = self._hover or need + pencil <= room
        self.pencil.setVisible(show_pencil)
        avail = max(24, room - (pencil if show_pencil else 0))
        self.text.setText(fm.elidedText(self._name, Qt.ElideRight, avail))
        self.text.setToolTip(self._name if need > avail else "")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit()

    def enterEvent(self, e):
        super().enterEvent(e)
        self._hover = True
        self.fit()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._hover = False
        self.fit()

    # ---- Adı yerinde değiştirme
    def start_rename(self):
        self.edit.setText(self.fence.data["name"])
        self.text.hide()
        self.pencil.hide()
        self.edit.show()
        self.fence.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()

    def finish_rename(self, commit: bool):
        if not self.edit.isVisible():
            return
        name = self.edit.text().strip()
        self.edit.hide()
        self.text.show()
        self.fit()
        if commit and name and name != self.fence.data["name"]:
            self.fence.data["name"] = name
            self.fence.app.fence_changed(self.fence)

    # ---- Kart içinde arama: yazdıkça adı uymayan öğeler gizlenir
    def start_search(self):
        if not self.find.isHidden():
            self.finish_search(True)
            return
        self.finish_rename(False)
        for w in (self.text, self.pencil, self.count):
            w.hide()
        self.find.show()
        self.fence.activateWindow()
        self.find.setFocus()

    def finish_search(self, force=False):
        """Arama kutusu boşsa (ya da Esc ile) kapanır; yazı varken süzme açık kalır."""
        if self.find.isHidden() or (self.find.text().strip() and not force):
            return
        self.find.clear()
        self.find.hide()
        self.text.show()
        self.count.show()
        self.fit()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            if obj is self.edit:
                self.finish_rename(False)
                return True
            if obj is self.find:
                self.finish_search(True)
                return True
        return super().eventFilter(obj, e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.fence.app.locked and not self.fence.data.get("lock_pos"):
            self._drag = e.globalPosition().toPoint() - self.fence.frameGeometry().topLeft()
            self._snapped = (False, False)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            if not self._moved:  # sürükleme başladı: bulanıklık taşırken takılma yapar, geçici olarak kapat
                self._moved = True
                self.fence.suspend_blur()
            pos = e.globalPosition().toPoint() - self._drag
            self._snapped = (False, False)
            # Ekran kenarına ve diğer kartlara yapıştırma; Alt basılıyken serbest taşınır
            if self.fence.app.config.get("magnet", True) and not e.modifiers() & Qt.AltModifier:
                pos, self._snapped = self.fence.magnet(pos)
            self.fence.move(pos)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.unsetCursor()
            if self._moved:
                self._moved = False
                self.fence.resume_blur()
            pos = self.fence.pos()
            sx, sy = self._snapped  # bir kenara yapışan eksen ızgaraya yuvarlanmaz: hizası bozulmasın
            self.fence.move(pos.x() if sx else snap(pos.x()), pos.y() if sy else snap(pos.y()))
            self.fence.store_geometry()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and not self.fence.data.get("rollup"):
            self.fence.toggle_collapsed()


class SettingsPopup(QWidget):
    """Kart ayarları penceresi: kartın yanında açılan, her zaman üstte duran küçük pencere.

    Kartlar masaüstünün en altında durduğu için ayarlar kartın içinde değil burada gösterilir.
    Pencere engelleyici değildir; dışına tıklanınca, Esc'e basılınca ya da "Bitti" ile kapanır."""

    W, H, PAD = 380, 700, 0

    def __init__(self, fence):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.fence = fence
        self.closed_at = 0.0
        self.opened_at = 0.0
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        frame = named(QFrame(), "popup")
        outer.addWidget(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 12)
        v.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(18, 14, 10, 8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.heading = label("", "popupTitle")
        titles.addWidget(self.heading)
        titles.addWidget(label(t("Kart ayarları"), "popupSub"))
        head.addLayout(titles, 1)
        close = named(QToolButton(text="\uE8BB"), "popupClose")
        close.setCursor(Qt.PointingHandCursor)
        close.setToolTip(t("Kapat (Esc)"))
        close.clicked.connect(self.dismiss)
        head.addWidget(close, 0, Qt.AlignTop)
        v.addLayout(head)

        self.settings = CardSettings(fence.app, in_card=True)
        v.addWidget(scroll_wrap(self.settings), 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(12, 10, 12, 0)
        foot.setSpacing(6)
        b = QPushButton(t("Kontrol paneli"))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: fence.app.show_panel(fence))
        foot.addWidget(b)
        done = named(QPushButton(t("Bitti")), "primary")
        done.setCursor(Qt.PointingHandCursor)
        done.clicked.connect(self.dismiss)
        foot.addWidget(done)
        v.addLayout(foot)

    def apply_look(self, look):
        if look:
            self.setStyleSheet(popup_style(look))

    def _place(self) -> QPoint:
        """Kartın sağında yer varsa sağına, yoksa soluna; ekrana sığacak şekilde."""
        card = self.fence.frameGeometry()
        screen = QGuiApplication.screenAt(card.center()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        w = self.W + 2 * self.PAD
        h = min(self.H + 2 * self.PAD, geo.height() - 20)
        self.resize(w, h)
        x = card.right() + 4
        if x + w > geo.right():
            x = card.left() - w - 4
        x = max(geo.left(), min(x, geo.right() - w))
        y = max(geo.top() + 4, min(card.top() - self.PAD, geo.bottom() - h))
        return QPoint(x, y)

    def open(self):
        self.heading.setText(self.fence.data["name"])
        self.settings.reset_confirm()
        self.settings.load(force=True)
        self.opened_at = time.monotonic()
        self.move(self._place())
        self.show()
        self.raise_()
        self.activateWindow()

    def dismiss(self):
        if not self.isVisible():
            return
        self.closed_at = time.monotonic()
        self.fence.title.gear.setChecked(False)
        self.hide()

    def event(self, e):
        # Dışına tıklanınca kapanır. Açılışın hemen ardından gelen odak değişimleri (başka bir ayar
        # penceresinin kapanması gibi) sayılmaz; yoksa pencere açılır açılmaz kapanabilir.
        if (e.type() == QEvent.WindowDeactivate and self.isVisible()
                and time.monotonic() - self.opened_at > 0.35):
            QTimer.singleShot(0, self.dismiss)
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(e)


class FenceWindow(QWidget):
    def __init__(self, app, data: dict):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.app = app
        self.data = data
        if data.get("icon_size") not in [s for _, s in ICON_SIZES]:
            data["icon_size"] = 36
        data.setdefault("kind", "desktop")
        data.setdefault("items", [])
        self.kind = data["kind"]
        self.folder = Path(data["folder"]) if self.kind == "folder" else None
        if self.folder:
            self.folder.mkdir(parents=True, exist_ok=True)
        self.icons = QFileIconProvider()
        self._loading = False
        self._style_key = None
        self.look = None
        self.popup_look = None
        self._blur = False
        self._suspended = False      # taşıma/boyutlandırma sırasında bulanıklık geçici olarak kapalı
        self._force_refresh = False
        self._filter = ""      # kart içi arama metni (küçük harf)
        self._peek = False     # "üzerine gelince aç" kartı şu an fareyle açık mı
        self._folded = None    # kartın şu an başlığa daraltılmış görünüp görünmediği
        self.popup = None      # kart ayarları penceresi (ilk açılışta oluşturulur)
        self.settings = None   # o penceredeki ayar formu

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(data["name"])
        self.setAcceptDrops(True)
        self.setMinimumWidth(200)

        self.frame = QFrame(self)
        self.frame.setObjectName("fence")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        lay = QVBoxLayout(self.frame)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(0)

        self.title = TitleBar(self)
        lay.addWidget(self.title)
        # Sekme şeridi: kart bir sekme grubundaysa gruptaki kartların adları
        self.tabs_bar = named(QWidget(), "tabs")
        tb = QHBoxLayout(self.tabs_bar)
        tb.setContentsMargins(10, 0, 10, 6)
        tb.setSpacing(4)
        self.tabs_bar.hide()
        self._tabs = []  # (düğme, kart)
        lay.addWidget(self.tabs_bar)

        self.stack = QStackedWidget()
        page = named(QWidget(), "page")
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.list = FenceList(self)
        self.empty = named(QLabel(t("Dosyaları buraya sürükleyin")), "emptyHint")
        self.empty.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.list, 1)
        pl.addWidget(self.empty, 1)
        self.stack.addWidget(page)
        # Not kartı: dosya listesi yerine serbest metin; yazılanlar ayarlarla birlikte saklanır
        self.note = NoteEdit()
        self.note.load(data)
        self._note_timer = QTimer(self, singleShot=True, interval=600, timeout=self.store_note)
        self.note.textChanged.connect(self._note_timer.start)
        self.note.textChanged.connect(self.update_note_count)
        note_page = named(QWidget(), "page")
        nl = QVBoxLayout(note_page)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(0)
        nl.addWidget(self.note, 1)
        # Notun altındaki araç çubuğu
        self.note_bar = named(QWidget(), "noteBar")
        bar = QHBoxLayout(self.note_bar)
        bar.setContentsMargins(10, 2, 26, 0)
        bar.setSpacing(4)
        self.note_tools = {}
        for key, glyph, tip, slot in (
                ("task", "\uE73A", t("Yapılacak maddesi"), self.note.toggle_task),
                ("bullet", "\uE8FD", t("Madde işareti"), self.note.toggle_bullet),
                ("heading", "\uE8E9", t("Başlık"), self.note.toggle_heading),
                ("bold", "\uE8DD", t("Kalın (Ctrl+B)"), self.note.toggle_bold),
                ("italic", "\uE8DB", t("İtalik (Ctrl+I)"), self.note.toggle_italic),
                ("strike", "\uEDE0", t("Üstü çizili"), self.note.toggle_strike),
                ("remind", "\uE823", t("Hatırlatıcı"), self.show_remind_menu)):
            b = QToolButton(text=glyph)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)  # tıklayınca yazı alanı odağını kaybetmesin
            b.clicked.connect(slot)
            bar.addWidget(b)
            self.note_tools[key] = b
        bar.addStretch()
        nl.addWidget(self.note_bar)
        self.stack.addWidget(note_page)
        if self.kind == "note":
            self.stack.setCurrentIndex(1)
        lay.addWidget(self.stack, 1)

        self.grip = QSizeGrip(self.frame)
        self.grip.setStyleSheet("QSizeGrip { background: transparent; width: 16px; height: 16px; }")

        self.list.itemDoubleClicked.connect(lambda it: self.open_path(it.data(Qt.UserRole)))
        self.list.customContextMenuRequested.connect(self.on_list_menu)
        self.list.itemChanged.connect(self.on_item_renamed)

        # Masaüstü kartları uygulamanın masaüstü izleyicisiyle yenilenir; klasör kartı kendi klasörünü izler
        self.watcher = QFileSystemWatcher([str(self.folder)] if self.folder else [])
        self._refresh_timer = QTimer(self, singleShot=True, interval=250, timeout=self.refresh)
        self.watcher.directoryChanged.connect(lambda _: self._refresh_timer.start())
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self.store_geometry)
        self._resume_timer = QTimer(self, singleShot=True, interval=300, timeout=self.resume_blur)
        self._peek_timer = QTimer(self, singleShot=True, interval=350, timeout=self.end_peek)

        self.resize(data.get("w", 340), data.get("h", 230))
        self.move(data.get("x", 100), data.get("y", 100))
        self.ensure_on_screen()
        self.apply_settings()
        self.refresh()
        self.set_collapsed(data.get("collapsed", False), save=False)

    # ---- Masaüstüne iliştirme ve en altta tutma
    def showEvent(self, e):
        super().showEvent(e)
        progman = user32.FindWindowW("Progman", None)
        if progman:  # Win+D ("Masaüstünü göster") kartları gizlemesin
            _SetWindowLongPtr(int(self.winId()), GWL_HWNDPARENT, progman)
        self._style_key = None  # cam efektini görünür pencereye yeniden uygula
        self.apply_settings()

    def vanish(self):
        """Kartı soldurarak kapatır ve siler."""
        if self.popup:
            self.popup.hide()
            self.popup.deleteLater()

        def end():
            self.hide()
            self.deleteLater()

        # Not: kart pencerelerinde pencere saydamlığı animasyonu kullanılmaz; bulanıklık katmanıyla
        # birlikte pencereyi görünmez bırakabiliyor.
        end()

    def set_drop_highlight(self, on: bool):
        """Üzerine dosya sürüklenirken kartın kenarını vurgular.

        Sürükleme karttan çıkarken "ayrıldı" bildirimi her zaman gelmez (başlıktan çıkış, Gezgin'den
        gelen sürükleme, bırakmanın iptali). Bu yüzden vurgu açıkken imleç izlenir: imleç kartın
        dışındaysa ya da fare düğmesi bırakıldıysa vurgu kendiliğinden kapanır.
        """
        if on:
            for other in self.app.fences:  # aynı anda yalnızca bir kart vurgulanır
                if other is not self:
                    other.set_drop_highlight(False)
            if not hasattr(self, "_drop_watch"):
                self._drop_watch = QTimer(self)
                self._drop_watch.setInterval(120)
                self._drop_watch.timeout.connect(self._check_drop_highlight)
            self._drop_watch.start()
        elif hasattr(self, "_drop_watch"):
            self._drop_watch.stop()
        if self.frame.property("drop") != ("true" if on else "false"):
            self.frame.setProperty("drop", "true" if on else "false")
            self.frame.style().unpolish(self.frame)
            self.frame.style().polish(self.frame)

    def _check_drop_highlight(self):
        pressed = any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x01, 0x02))  # sol, sağ düğme
        if not pressed or not self.frameGeometry().contains(QCursor.pos()):
            self.set_drop_highlight(False)

    def nativeEvent(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_WINDOWPOSCHANGING and msg.lParam:
                    wp = WINDOWPOS.from_address(msg.lParam)
                    wp.flags &= ~SWP_NOZORDER
                    wp.hwndInsertAfter = HWND_BOTTOM
        except Exception:  # noqa: BLE001
            pass
        return False, 0

    def magnet(self, pos, gap=10, reach=12):
        """Taşınan kartın konumunu yakındaki ekran kenarına ya da komşu kartın kenarına çeker.
        Dönüş: (konum, (yatay yapıştı mı, dikey yapıştı mı))."""
        w, h = self.width(), self.height()
        screen = (QGuiApplication.screenAt(QPoint(pos.x() + w // 2, pos.y() + h // 2))
                  or QGuiApplication.primaryScreen())
        geo = screen.availableGeometry()
        xs = [geo.left() + gap, geo.right() + 1 - gap - w]
        ys = [geo.top() + gap, geo.bottom() + 1 - gap - h]
        for other in self.app.fences:
            if other is self or not other.isVisible():
                continue
            r = other.frameGeometry()
            left, top, right, bottom = r.left(), r.top(), r.right() + 1, r.bottom() + 1
            if pos.y() < bottom + 3 * gap and pos.y() + h > top - 3 * gap:    # dikeyde yakın: yan yana hizala
                xs += [left, right - w, right + gap, left - gap - w]
            if pos.x() < right + 3 * gap and pos.x() + w > left - 3 * gap:    # yatayda yakın: alt alta hizala
                ys += [top, bottom - h, bottom + gap, top - gap - h]

        def pick(value, candidates):
            best = min(candidates, key=lambda c: abs(c - value))
            return (best, True) if abs(best - value) <= reach else (value, False)

        (x, sx), (y, sy) = pick(pos.x(), xs), pick(pos.y(), ys)
        return QPoint(x, y), (sx, sy)

    def apply_filter(self, text=None):
        """Kart içi arama: adı aranan metni içermeyen öğeleri gizler."""
        if text is not None:
            self._filter = text.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(self._filter) and self._filter not in it.text().lower())

    def ensure_on_screen(self):
        if QGuiApplication.screenAt(self.frameGeometry().center()) is None:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            self.move(geo.left() + 40, geo.top() + 40)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = self.grip.sizeHint()
        self.grip.move(self.frame.width() - g.width() - 4, self.frame.height() - g.height() - 4)
        self.fit_tabs()
        if self._blur and self.isVisible():  # boyutlanırken bulanıklık takılma yapar: bitene kadar kapat
            self.suspend_blur()
            self._resume_timer.start()
        self._apply_region()
        if not self.is_folded():
            self._save_timer.start()

    def _apply_region(self):
        """Bulanıklık açıkken pencereyi kartın köşe yuvarlaklığına göre kırpar."""
        if self.look:
            set_window_region(self, self.look.radius if self._blur and not self._suspended else None)

    def suspend_blur(self):
        """Kart taşınırken ya da boyutlanırken arka plan bulanıklığını geçici olarak kapatır.
        Windows bulanık pencereleri hareket ettirirken belirgin biçimde yavaşlıyor."""
        if self._blur and not self._suspended and self.look:
            self._suspended = True
            set_acrylic(self, self.look.bg, 6, enable=False)
            set_window_region(self, None)
            self.setStyleSheet(card_style(self.look, False))

    def resume_blur(self):
        if self._suspended:
            self._suspended = False
            self._style_key = None
            self.apply_settings()

    def store_geometry(self):
        self.data["x"], self.data["y"] = self.x(), self.y()
        self.data["w"] = self.width()
        if not self.is_folded():
            self.data["h"] = self.height()
        self.app.save()

    # ---- Görünüm
    def apply_settings(self):
        d = self.data
        ap = appearance(self.app.config)
        paper = d.get("paper") if self.kind == "note" else None
        key = (repr(sorted(ap.items(), key=lambda kv: kv[0])), d.get("theme"), d.get("opacity"), paper)
        if key != self._style_key:
            self._style_key = key
            look = make_look(ap, d.get("theme"), d.get("opacity"))
            self.popup_look = look  # ayar penceresi kâğıt rengine bürünmez
            if paper:  # yapışkan not: düz renkli kâğıt, koyu yazı; genel tema ve saydamlık uygulanmaz
                look = replace(look, style="flat", light=True, bg=QColor(paper), opacity=100,
                               accent=QColor(paper).darker(260))
            self.look = look
            # Bulanıklık katmanı renksiz tutulur; renk ve opaklık stil sayfasında boyanır
            self._blur = blur = set_acrylic(self, look.bg, 6, enable=look.wants_blur) and look.wants_blur
            self._apply_region()
            self.setStyleSheet(card_style(look, blur))
            if self.popup:
                self.popup.apply_look(self.popup_look)
            self.list.delegate.look = look
            self.list.viewport().update()
        self.list.apply_icon_size(d.get("icon_size", 36), self.look)
        self.setWindowTitle(d["name"])
        # Kilitler: genel kilit konumu ve boyutu, kartın kendi kilitleri ayrı ayrı
        self.grip.setVisible(not self.app.locked and not d.get("lock_size") and not self.is_folded())
        self.title.fold.setVisible(not d.get("rollup"))  # açılır kartta daraltma düğmesine gerek yok
        locked = bool(d.get("lock_content"))
        self.note.setReadOnly(locked)
        self.note_bar.setVisible(not locked)
        if self.kind == "note":
            self.note.set_accent(self.look.accent)
            self.note.setStyleSheet(f"font-size: {self.look.font_size + 1 + d.get('note_size', 0):g}pt;")
            self.note.setLineWrapMode(NoteEdit.WidgetWidth if d.get("note_wrap", True) else NoteEdit.NoWrap)
            remind = self.note_tools["remind"]
            remind.setCheckable(True)
            remind.setChecked(bool(d.get("remind")))
            remind.setToolTip(t("Hatırlatıcı: {0}").format(time.strftime("%d.%m.%Y %H:%M", time.localtime(d["remind"])))
                              if d.get("remind") else t("Hatırlatıcı"))
        self.list.setDragEnabled(not locked)
        self.list.setEditTriggers(QAbstractItemView.NoEditTriggers if locked else QAbstractItemView.EditKeyPressed)
        self.title.lock.setVisible(bool(d.get("lock_pos") or d.get("lock_size") or locked))
        self.title.set_name(f"{d['emoji']} {d['name']}" if d.get("emoji") else d["name"])
        if self._folded is not None and self._folded != self.is_folded():  # "üzerine gelince aç" değişti
            self._fold(self.is_folded())

    # ---- Daraltma ve "üzerine gelince aç"
    def is_folded(self) -> bool:
        """Kart şu an yalnızca başlık olarak mı görünmeli?"""
        if self.data.get("rollup"):
            return not self._peek
        return bool(self.data.get("collapsed"))

    def _fold(self, folded: bool):
        self._folded = folded
        self.title.fold.setText("\uE76C" if folded else "\uE70D")
        self.stack.setVisible(not folded)
        self.tabs_bar.setVisible(not folded and len(self._tabs) > 1)
        self.frame.layout().setContentsMargins(0, 0, 0, 0 if folded else 6)
        if folded:
            self.setFixedHeight(TITLE_H + 2)
        else:
            self.setMinimumHeight(TITLE_H + 90)
            self.setMaximumHeight(16777215)
            self.resize(self.width(), max(self.data.get("h", 230), TITLE_H + 90))
        self.grip.setVisible(not self.app.locked and not self.data.get("lock_size") and not folded)

    def begin_peek(self):
        """Açılır kartı açar ve diğer kartların üstüne getirir."""
        if not self.data.get("rollup"):
            return
        self._peek_timer.stop()
        if not self._peek:
            self._peek = True
            self._fold(False)
            for other in self.app.fences:  # hepsi masaüstünün en altında: ötekileri bunun altına indir
                if other is not self and other.isVisible():
                    other.lower()

    def end_peek(self):
        if not self._peek:
            return
        busy = (self.frameGeometry().contains(QCursor.pos()) or (self.popup and self.popup.isVisible())
                or not self.title.edit.isHidden() or not self.title.find.isHidden() or self.note.hasFocus()
                or any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x01, 0x02)))
        if busy and self.data.get("rollup"):
            self._peek_timer.start()  # hâlâ kullanılıyor: biraz sonra yeniden bak
            return
        self._peek = False
        self._fold(self.is_folded())

    def enterEvent(self, e):
        super().enterEvent(e)
        self.begin_peek()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self._peek:
            self._peek_timer.start()

    def update_tabs(self):
        """Sekme şeridini grubun güncel üyelerine göre yeniden kurar."""
        members = self.app.group_of(self)
        lay = self.tabs_bar.layout()
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._tabs = []
        if len(members) > 1:
            for m in members:
                b = named(QPushButton(), "tab")
                b.setCheckable(True)
                b.setChecked(m is self)
                b.setCursor(Qt.PointingHandCursor)
                b.setMinimumWidth(24)
                b.setToolTip(m.data["name"])
                # Sekme değişince bu şerit yeniden kurulur: tıklama bittikten sonra uygula
                b.clicked.connect(lambda _=False, card=m: QTimer.singleShot(0, lambda: self.app.activate_tab(card)))
                lay.addWidget(b, 1)
                self._tabs.append((b, m))
        self.tabs_bar.setVisible(len(self._tabs) > 1 and not self.is_folded())
        self.fit_tabs()

    def fit_tabs(self):
        """Sekme adlarını eldeki genişliğe göre kısaltır."""
        if not self._tabs:
            return
        room = max(24, (self.width() - 20 - 4 * (len(self._tabs) - 1)) // len(self._tabs) - 18)
        for b, m in self._tabs:
            name = f"{m.data['emoji']} {m.data['name']}" if m.data.get("emoji") else m.data["name"]
            b.setText(b.fontMetrics().elidedText(name, Qt.ElideRight, room))

    def store_note(self):
        if self.kind != "note":
            return
        md = self.note.markdown()
        if self.data.get("md") != md:
            self.data["md"] = md
            self.data["text"] = self.note.toPlainText()  # düz metin: arama ve dışa aktarma için
            self.app.save()

    # ---- Hatırlatıcı
    def show_remind_menu(self):
        now = time.time()
        tomorrow = time.localtime(now + 86400)
        nine = time.mktime((tomorrow.tm_year, tomorrow.tm_mon, tomorrow.tm_mday, 9, 0, 0, 0, 0, -1))
        m = QMenu(self)
        m.addAction(t("15 dakika sonra"), lambda: self.set_reminder(now + 15 * 60))
        m.addAction(t("1 saat sonra"), lambda: self.set_reminder(now + 3600))
        m.addAction(t("Yarın 09:00"), lambda: self.set_reminder(nine))
        m.addAction(t("Tarih ve saat seç…"), lambda: (self.show_settings(True), self.settings.set_tab(1)))
        if self.data.get("remind"):
            m.addSeparator()
            m.addAction(t("Hatırlatıcıyı kaldır"), lambda: self.set_reminder(None))
        button = self.note_tools["remind"]
        m.exec(button.mapToGlobal(QPoint(0, -m.sizeHint().height() - 4)))

    def set_reminder(self, when):
        self.data["remind"] = int(when) if when else None
        self.app.fence_changed(self)

    def update_note_count(self):
        """Not kartının başlığında tamamlanan/toplam yapılacak sayısını gösterir."""
        if self.kind == "note":
            done, total = self.note.counts()
            self.title.count.setText(f"{done}/{total}" if total else "")
            self.title.fit()

    def set_collapsed(self, collapsed: bool, save=True):
        self.data["collapsed"] = collapsed
        self._fold(self.is_folded())
        self.apply_settings()
        if save:
            self.store_geometry()
            self.app.fence_changed(self)

    def toggle_collapsed(self):
        self.set_collapsed(not self.data.get("collapsed", False))

    def show_settings(self, on: bool):
        """Kart ayarlarını kartın yanında ayrı bir pencerede açar ya da kapatır."""
        if on:
            if self.popup is None:
                self.popup = SettingsPopup(self)
                self.settings = self.popup.settings
                self.settings.bind(self)
                self.popup.apply_look(self.popup_look)
            if time.monotonic() - self.popup.closed_at < 0.3:
                on = False  # pencereyi kapatan tıklamanın kendisi: yeniden açma
            else:
                self.app.close_popups(keep=self)
                self.popup.open()
        elif self.popup and self.popup.isVisible():
            self.popup.dismiss()
        self.title.gear.setChecked(on)

    def set_folder(self, path):
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        self.kind = self.data["kind"] = "folder"
        self.folder = Path(path)
        self.data["folder"] = str(self.folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.watcher.addPath(str(self.folder))
        self.refresh()

    # ---- İçerik
    def entries(self):
        if self.kind == "folder":
            try:
                items = [p for p in self.folder.iterdir()
                         if p.name.lower() not in SKIP_NAMES and not is_hidden(p)]
            except OSError:
                items = []
        elif self.kind == "rest":
            taken = self.app.assigned_keys()
            items = [p for p in desktop_entries() if norm(p) not in taken]
        else:
            # Var olmayanları (silinmiş/taşınmış) kart listesinden düşür
            alive = [p for p in self.data["items"] if Path(p).exists()]
            if len(alive) != len(self.data["items"]):
                self.data["items"] = alive
                self.app.save()
            items = [Path(p) for p in alive]
        return self.sorted_items(items)

    def sorted_items(self, items):
        mode = self.data.get("sort", "name")
        if mode == "manual":  # serbest: kullanıcının sürükleyerek verdiği sıra; yeni gelenler sona
            order = {k: i for i, k in enumerate(self.data.get("order", []))}
            return sorted(items, key=lambda p: (order.get(norm(p), len(order)), p.name.lower()))
        if mode == "type":
            return sorted(items, key=lambda p: (not p.is_dir(), p.suffix.lower(), p.name.lower()))
        if mode == "date":  # en yeni en başta
            def mtime(p):
                try:
                    return p.stat().st_mtime
                except OSError:
                    return 0
            return sorted(items, key=lambda p: (-mtime(p), p.name.lower()))
        return sorted(items, key=lambda p: (not p.is_dir(), p.name.lower()))

    def reorder(self, paths, row):
        """Seçili öğeleri kart içinde bırakılan yere taşır ve sıralamayı "Serbest"e alır."""
        current = [norm(self.list.item(i).data(Qt.UserRole)) for i in range(self.list.count())]
        moving = [norm(p) for p in paths if norm(p) in current]
        target = current[row] if 0 <= row < len(current) else None
        if not moving or target in moving:
            return
        rest = [k for k in current if k not in moving]
        at = rest.index(target) if target in rest else len(rest)
        self.data["order"] = rest[:at] + moving + rest[at:]
        self.data["sort"] = "manual"
        self.refresh()
        self.app.fence_changed(self)

    def apply_badges(self):
        """Bildirim sayılarını karttaki kısayollarla eşleştirip rozetleri günceller."""
        badges = self.app.badges
        for i in range(self.list.count()):
            it = self.list.item(i)
            p = Path(it.data(Qt.UserRole))
            n = 0
            if badges and p.suffix.lower() in (".lnk", ".url", ".exe"):
                stem = p.stem.lower()
                n = sum(c for name, aumid, c in badges if matches(stem, name, aumid))
            if (it.data(BADGE_ROLE) or 0) != n:
                self._loading = True  # itemChanged yeniden adlandırma sanılmasın
                it.setData(BADGE_ROLE, n)
                self._loading = False

    def refresh(self):
        entries = self.entries()
        shown = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        if not self._force_refresh and shown == [str(p) for p in entries]:
            self.apply_badges()  # içerik aynı: listeyi baştan kurma (masaüstündeki her değişiklikte çağrılır)
            return
        self._force_refresh = False
        self._loading = True
        selected = {it.data(Qt.UserRole) for it in self.list.selectedItems()}
        self.list.clear()
        for p in entries:
            text = p.stem if p.suffix.lower() in (".lnk", ".url") else p.name
            it = QListWidgetItem(self.app.icon_for(p), text)
            it.setData(Qt.UserRole, str(p))
            it.setToolTip(p.name)
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.list.addItem(it)
            if str(p) in selected:
                it.setSelected(True)
        n = self.list.count()
        self.title.count.setText(str(n) if n else "")
        self.title.search.setVisible(n >= 6 or bool(self._filter))  # az öğeli kartta aramaya gerek yok
        self.title.fit()
        if self._filter:
            self.apply_filter()
        self.list.setVisible(n > 0)
        self.empty.setVisible(n == 0)
        self._loading = False
        self.list.reset_animation()
        self.apply_badges()
        self.update_note_count()
        if hasattr(self.app, "panel"):
            self.app.panel.update_names()

    def receive(self, paths, copy=False):
        """Bırakılan öğeler: masaüstü kartı yalnızca atar (dışarıdan geleni önce masaüstüne alır),
        klasör kartı ise klasöre taşır/kopyalar."""
        if self.data.get("lock_content"):
            self.app.notify(t('“{0}” kartının içeriği kilitli.').format(self.data['name']))
            return
        errors = []
        target = self.folder if self.kind == "folder" else desktop_dir()
        for raw in paths:
            if not raw:
                continue
            src = Path(raw)
            try:
                if not src.exists():
                    continue
                if self.kind != "folder" and on_desktop(src) and not copy:
                    dst = src  # zaten masaüstünde: dosyaya dokunma, sadece karta ata
                elif norm(src.parent) == norm(target) and not copy:
                    dst = src
                else:
                    if norm(target).startswith(norm(src) + os.sep):
                        continue  # klasörü kendi içine bırakma
                    dst = unique_dest(target, src.name)
                    if copy:
                        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
                    else:
                        shutil.move(str(src), str(dst))
                if self.kind == "desktop":
                    self.app.assign(dst, self)
                elif self.kind == "rest":
                    self.app.assign(dst, None)
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{src.name}: {ex}")
        self.app.refresh_all()
        if errors:
            self.app.notify(t("Bazı öğeler eklenemedi: ") + "; ".join(errors[:3]), warn=True)

    def open_path(self, path):
        try:
            os.startfile(path)
        except OSError as ex:
            self.app.notify(t('Açılamadı: {0}').format(ex), warn=True)

    def selected_paths(self):
        return [Path(it.data(Qt.UserRole)) for it in self.list.selectedItems()]

    def on_item_renamed(self, item):
        if self._loading:
            return
        old = Path(item.data(Qt.UserRole))
        text = safe_name(item.text())
        new_name = text + old.suffix if old.suffix.lower() in (".lnk", ".url") else text
        if new_name != old.name:
            new = old.with_name(new_name)
            try:
                old.rename(new)
                self.app.path_renamed(old, new)
                if self.kind == "desktop":
                    items = self.data["items"]
                    self.data["items"] = [str(new) if norm(p) == norm(old) else p for p in items]
                    self.app.save()
            except OSError as ex:
                self.app.notify(t('Yeniden adlandırılamadı: {0}').format(ex), warn=True)
        self._force_refresh = True  # ad değişmediyse bile yazılan metni geri al
        QTimer.singleShot(0, self.app.refresh_all)

    def recycle_selected(self):
        paths = self.selected_paths()
        if paths:
            recycle(paths)
            self.app.refresh_all()

    def unassign_selected(self):
        for p in self.selected_paths():
            self.app.assign(p, None)
        self.app.refresh_all()

    def move_selected_to_desktop(self):
        desk = desktop_dir()
        for p in self.selected_paths():
            try:
                shutil.move(str(p), str(unique_dest(desk, p.name)))
            except Exception as ex:  # noqa: BLE001
                self.app.notify(t('{0} taşınamadı: {1}').format(p.name, ex), warn=True)
        self.app.refresh_all()

    def on_list_menu(self, pos):
        it = self.list.itemAt(pos)
        gpos = self.list.viewport().mapToGlobal(pos)
        m = QMenu(self)
        if it is None:
            m.addAction(t("Kart ayarları"), lambda: self.show_settings(True))
            if self.folder:
                m.addAction(t("Klasörü aç"), lambda: os.startfile(str(self.folder)))
            m.addAction(t("Kontrol paneli"), lambda: self.app.show_panel(self))
            m.exec(gpos)
            return
        if not it.isSelected():
            self.list.clearSelection()
            it.setSelected(True)
        paths = self.selected_paths()
        m.addAction(t("Aç"), lambda: [self.open_path(str(p)) for p in paths])
        if len(paths) == 1:
            m.addAction(t("Dosya konumunu göster"),
                        lambda: subprocess.Popen(["explorer", "/select,", str(paths[0])]))
            if not self.data.get("lock_content"):
                m.addAction(t("Yeniden adlandır"), lambda: self.list.editItem(it))
        if self.data.get("lock_content"):  # içerik kilitli: yalnızca açma ve gösterme
            m.exec(gpos)
            return
        m.addSeparator()
        if self.kind == "desktop":
            m.addAction(t("Karttan çıkar (masaüstünde kalır)"), self.unassign_selected)
        elif self.kind == "folder":
            m.addAction(t("Masaüstüne taşı"), self.move_selected_to_desktop)
        m.addSeparator()
        # Silme iki adımlı: alt menüden ayrıca onaylanır
        what = paths[0].name if len(paths) == 1 else t('{0} öğe').format(len(paths))
        sub = m.addMenu(t("Sil…"))
        sub.addAction(t('Evet, “{0}” Geri Dönüşüm Kutusuna gitsin').format(what), self.recycle_selected)
        sub.addAction(t("Vazgeç"))
        m.exec(gpos)

    def dragEnterEvent(self, e):
        self.list.dragEnterEvent(e)

    def dragMoveEvent(self, e):
        self.list.dragMoveEvent(e)

    def dragLeaveEvent(self, e):
        self.set_drop_highlight(False)

    def dropEvent(self, e):
        self.list.dropEvent(e)
