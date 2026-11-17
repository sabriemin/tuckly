"""Kontrol paneli penceresi."""

from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .config import APP_NAME, DEFAULT_FONT
from .winapi import set_dark_titlebar
from .theme import ACCENT_MODES, STYLES, appearance, dot_icon, make_app_icon, panel_look, panel_style, seed_of
from .widgets import (
    StyleTile,
    SwatchRow,
    Toggle,
    group_label,
    label,
    make_group,
    named,
    scroll_wrap,
    segmented,
    setting_row,
)
from .card_settings import CardSettings
from .notifications import AVAILABLE as BADGES_AVAILABLE


class ControlPanel(QWidget):
    PAGES = ("Kartlar", "Görünüm", "Masaüstünü düzenle", "Seçenekler")

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("panel")
        self.setAttribute(Qt.WA_StyledBackground)
        self.apply_look()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.resize(860, 620)
        self.setMinimumSize(720, 480)
        self._plan = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Kenar çubuğu
        side = QWidget()
        side.setFixedWidth(200)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(18, 18, 12, 14)
        ic = QLabel()
        ic.setPixmap(make_app_icon().pixmap(30, 30))
        brand.addWidget(ic)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bt.addWidget(label(APP_NAME, "brand"))
        bt.addWidget(label("Masaüstü düzenleyici", "brandSub"))
        brand.addLayout(bt, 1)
        sl.addLayout(brand)
        self.sidebar = named(QListWidget(), "sidebar")
        for t in self.PAGES:
            self.sidebar.addItem(t)
        self.sidebar.currentRowChanged.connect(self.set_page)
        sl.addWidget(self.sidebar, 1)
        quit_box = QVBoxLayout()
        quit_box.setContentsMargins(12, 8, 12, 14)
        b = named(QPushButton("Uygulamadan çık"), "danger")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(app.quit)
        quit_box.addWidget(b)
        sl.addLayout(quit_box)
        side_frame = named(QFrame(), "sidebar")
        side_frame.setAttribute(Qt.WA_StyledBackground)
        sf = QVBoxLayout(side_frame)
        sf.setContentsMargins(0, 0, 0, 0)
        sf.addWidget(side)
        self.sidebar.setStyleSheet("#sidebar { border: none; background: transparent; padding: 0 8px; }")
        root.addWidget(side_frame)

        # --- İçerik
        content = QVBoxLayout()
        content.setContentsMargins(28, 22, 28, 14)
        content.setSpacing(0)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        self.status = named(QLabel(""), "status")
        content.addWidget(self.status)
        root.addLayout(content, 1)

        self.pages.addWidget(self._cards_page())
        self.pages.addWidget(self._appearance_page())
        self.pages.addWidget(self._sort_page())
        self.pages.addWidget(self._options_page())
        self.sidebar.setCurrentRow(0)
        self.reload_cards()

    def showEvent(self, e):
        super().showEvent(e)
        set_dark_titlebar(self, not self.look.light)

    def apply_look(self):
        """Panelin renklerini geçerli görünüm ayarlarına göre yeniler."""
        self.look = panel_look(appearance(self.app.config))
        self.setStyleSheet(panel_style(self.look))
        if self.isVisible():
            set_dark_titlebar(self, not self.look.light)
        if hasattr(self, "card_list"):
            self.update_names()
            for w in self.findChildren(Toggle) + self.findChildren(StyleTile):
                w.update()

    # ---- Görünüm sayfası
    def _appearance_page(self):
        page = named(QWidget(), "page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        self._header(outer, "Görünüm", "Kartların stili, renkleri ve yazıları. Değişiklikler anında uygulanır.")
        inner = named(QWidget(), "page")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 6, 12)
        v.setSpacing(8)
        ap, setv = appearance(self.app.config), self.app.set_appearance

        # Stil
        v.addWidget(group_label("Stil"))
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.style_tiles = QButtonGroup(self)
        for key, title in STYLES:
            col = QVBoxLayout()
            col.setSpacing(4)
            t = StyleTile(key)
            t.setChecked(ap["style"] == key)
            t.clicked.connect(lambda _=False, k=key: setv("style", k))
            self.style_tiles.addButton(t)
            col.addWidget(t)
            nm = label(title, "tileName")
            nm.setAlignment(Qt.AlignHCenter)
            col.addWidget(nm)
            tiles.addLayout(col)
        tiles.addStretch()
        v.addLayout(tiles)

        # Renk
        v.addSpacing(6)
        v.addWidget(group_label("Renk"))
        mode_box, mode_group = segmented((("Koyu", 0), ("Açık", 1)),
                                         lambda i: setv("mode", "light" if i else "dark"))
        mode_group.button(1 if ap["mode"] == "light" else 0).setChecked(True)

        self.theme_row = SwatchRow(with_general=False, with_add=True)
        self.theme_row.set_custom(ap["custom_colors"])
        self.theme_row.set_value(ap["theme"])
        self.theme_value = label(self.theme_row.value_name(), "rowValue")
        self.theme_row.picked.connect(self.on_theme_picked)
        self.theme_row.added.connect(self.on_color_added)

        keys = [k for k, _ in ACCENT_MODES]
        accent_box, accent_group = segmented(tuple((t, i) for i, (_, t) in enumerate(ACCENT_MODES)),
                                             lambda i: self.on_accent_mode(keys[i]))
        accent_group.button(keys.index(ap["accent"]) if ap["accent"] in keys else 0).setChecked(True)
        self.accent_pick = QPushButton("Renk seç…")
        self.accent_pick.setCursor(Qt.PointingHandCursor)
        self.accent_pick.clicked.connect(self.on_accent_pick)
        self.accent_pick.setVisible(ap["accent"] == "custom")
        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)
        accent_row.addWidget(accent_box)
        accent_row.addWidget(self.accent_pick)
        accent_row.addStretch()

        def slider(key, lo, hi, fmt="%{}"):
            s = QSlider(Qt.Horizontal)
            s.setRange(lo, hi)
            s.setValue(int(ap[key]))
            val = label(fmt.format(int(ap[key])), "rowValue")
            s.valueChanged.connect(lambda x: (val.setText(fmt.format(x)), setv(key, x)))
            return s, val

        op, op_v = slider("opacity", 15, 100)
        sat, sat_v = slider("saturation", 0, 100)
        br, br_v = slider("brightness", 0, 100)
        v.addWidget(make_group([
            setting_row("Tema modu", "Koyu ya da açık zemin.", control=mode_box),
            setting_row("Hazır temalar", "Tek tıkla renk temaları; + ile kendi rengini ekle.",
                        below=self.theme_row, value=self.theme_value),
            setting_row("Vurgu rengi", "Anahtarlar, düğmeler ve kaydırıcılar için renk.", below=accent_row),
            setting_row("Arka plan opaklığı", "Kartların ne kadar saydam olacağı.", below=op, value=op_v),
            setting_row("Renk doygunluğu", "Arka planın ne kadar canlı olacağı.", below=sat, value=sat_v),
            setting_row("Arka plan parlaklığı", "Arka planın ne kadar açık olacağı.", below=br, value=br_v),
        ]))

        # Şekil
        v.addSpacing(6)
        v.addWidget(group_label("Şekil"))
        rad, rad_v = slider("radius", 0, 20, "{} px")
        brd, brd_v = slider("border", 0, 100)
        tiles_t = Toggle(ap["tiles"])
        tiles_t.toggled.connect(lambda on: setv("tiles", on))
        anim_t = Toggle(ap["animations"])
        anim_t.toggled.connect(lambda on: setv("animations", on))
        v.addWidget(make_group([
            setting_row("Köşe yuvarlaklığı", "Kartların köşeleri ne kadar yuvarlak olsun.", below=rad, value=rad_v),
            setting_row("Kenarlık", "Kart çevresindeki çizginin belirginliği. %0: çizgi yok.",
                        below=brd, value=brd_v),
            setting_row("Simge karoları", "Dosya simgelerinin arkasında yuvarlak karo göster.", control=tiles_t),
            setting_row("Büyüme efekti", "İmleç bir simgenin üzerine gelince simge hafifçe büyür.",
                        control=anim_t),
        ]))

        # Yazı
        v.addSpacing(6)
        v.addWidget(group_label("Yazı"))
        # Yazı tipleri: her biri kendi yazı tipiyle gösterilen, aranabilir bir liste
        current = ap["font_family"] or DEFAULT_FONT
        font_filter = QLineEdit()
        font_filter.setPlaceholderText("Yazı tipi ara…")
        font_list = named(QListWidget(), "rowList")
        font_list.setFixedHeight(210)
        font_list.setUniformItemSizes(True)
        for fam in QFontDatabase.families():
            if fam.startswith("@"):  # dikey yazım için çift kayıtlar
                continue
            it = QListWidgetItem(fam)
            f = QFont(fam)
            f.setPointSize(11)
            it.setFont(f)
            font_list.addItem(it)
            if fam == current:
                font_list.setCurrentItem(it)
        if font_list.currentItem():
            font_list.scrollToItem(font_list.currentItem(), QListWidget.ScrollHint.PositionAtCenter)
        font_list.currentTextChanged.connect(lambda fam: setv("font_family", fam) if fam else None)
        font_filter.textChanged.connect(lambda t: [
            font_list.item(i).setHidden(t.strip().lower() not in font_list.item(i).text().lower())
            for i in range(font_list.count())])
        font_box = QWidget()
        fbl = QVBoxLayout(font_box)
        fbl.setContentsMargins(0, 0, 0, 0)
        fbl.setSpacing(6)
        fbl.addWidget(font_filter)
        fbl.addWidget(font_list)
        size, size_v = slider("font_size", 8, 14, "{} pt")
        bold = Toggle(ap["font_bold"])
        bold.toggled.connect(lambda on: setv("font_bold", on))
        italic = Toggle(ap["font_italic"])
        italic.toggled.connect(lambda on: setv("font_italic", on))
        v.addWidget(make_group([
            setting_row("Yazı tipi", "Kart başlıkları ve dosya adları için.", below=font_box),
            setting_row("Boyut", below=size, value=size_v),
            setting_row("Kalın", control=bold),
            setting_row("İtalik", control=italic),
        ]))

        v.addSpacing(8)
        reset = QPushButton("Görünümü varsayılana döndür")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self.app.reset_appearance)
        row = QHBoxLayout()
        row.addWidget(reset)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        outer.addWidget(scroll_wrap(inner), 1)
        return page

    def reload_appearance(self):
        """Görünüm sayfasını ayarlardaki değerlerle yeniden kurar (sıfırlamadan sonra)."""
        old = self.pages.widget(1)
        self.pages.removeWidget(old)
        old.deleteLater()
        self.pages.insertWidget(1, self._appearance_page())
        self.pages.setCurrentIndex(self.sidebar.currentRow())

    def on_theme_picked(self, key):
        self.theme_value.setText(self.theme_row.value_name())
        self.app.set_appearance("theme", key)

    def on_color_added(self, color):
        ap = appearance(self.app.config)
        if color not in ap["custom_colors"]:
            ap["custom_colors"].append(color)
        self.theme_row.set_custom(ap["custom_colors"])
        self.theme_row.set_value(color)
        self.on_theme_picked(color)
        self.editor.load()

    def on_accent_mode(self, key):
        self.accent_pick.setVisible(key == "custom")
        self.app.set_appearance("accent", key)

    def on_accent_pick(self):
        ap = appearance(self.app.config)
        c = QColorDialog.getColor(QColor(ap["accent_color"]), self, "Vurgu rengi seç")
        if c.isValid():
            self.app.set_appearance("accent_color", c.name())

    def _header(self, lay, title, desc):
        lay.addWidget(label(title, "pageTitle"))
        d = label(desc, "pageDesc", wrap=True)
        d.setContentsMargins(0, 2, 0, 14)
        lay.addWidget(d)

    def _cards_page(self):
        page = named(QWidget(), "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        self._header(v, "Kartlar", "Kartlarınızı seçip düzenleyin. Aynı ayarlara her kartın ⚙ düğmesinden de "
                                   "ulaşabilirsiniz.")
        h = QHBoxLayout()
        h.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(group_label("Kartlarım"))
        self.card_list = named(QListWidget(), "rowList")
        self.card_list.setIconSize(QSize(14, 14))
        self.card_list.currentRowChanged.connect(self.on_select)
        left.addWidget(self.card_list, 1)
        b = named(QPushButton("+  Yeni kart"), "primary")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.on_new)
        left.addWidget(b)
        b = QPushButton("Klasörü kart olarak ekle…")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.on_add_folder)
        left.addWidget(b)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(230)
        h.addWidget(lw)
        self.editor = CardSettings(self.app, in_card=False)
        h.addWidget(scroll_wrap(self.editor), 1)
        v.addLayout(h, 1)
        return page

    def _sort_page(self):
        page = named(QWidget(), "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        self._header(v, "Masaüstünü düzenle", "Henüz bir karta yerleşmemiş masaüstü öğeleri kartların kategorilerine "
                                              "göre listelenir. Dosyalar taşınmaz; masaüstünde kalıp kartta görünürler.")
        top = QHBoxLayout()
        top.addWidget(group_label("Yerleştirilecek dosyalar"))
        top.addStretch()
        top.addWidget(label("Tümünü seç", "rowDesc"))
        self.sel_all = Toggle(True)
        self.sel_all.toggled.connect(self.on_select_all)
        top.addWidget(self.sel_all)
        v.addLayout(top)
        v.addSpacing(6)
        self.plan_list = named(QListWidget(), "rowList")
        v.addWidget(self.plan_list, 1)
        v.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        b = QPushButton("Listeyi yenile")
        b.clicked.connect(self.refresh_plan)
        row.addWidget(b)
        b = QPushButton("Son düzenlemeyi geri al")
        b.clicked.connect(self.app.undo_last)
        row.addWidget(b)
        row.addStretch()
        self.run_btn = named(QPushButton("Seçilenleri kartlara yerleştir"), "primary")
        self.run_btn.clicked.connect(self.on_run)
        row.addWidget(self.run_btn)
        for i in range(row.count()):
            w = row.itemAt(i).widget()
            if w:
                w.setCursor(Qt.PointingHandCursor)
        v.addLayout(row)
        return page

    def _options_page(self):
        page = named(QWidget(), "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        self._header(v, "Seçenekler", "Kartların ve masaüstünün genel davranışı.")
        cfg, app = self.app.config, self.app

        def row(title, desc, checked, slot):
            t = Toggle(checked)
            t.toggled.connect(slot)
            return setting_row(title, desc, control=t)

        v.addWidget(group_label("Masaüstü"))
        v.addSpacing(6)
        v.addWidget(make_group([
            row("Yeni dosyaları otomatik düzenle",
                "Masaüstüne gelen yeni dosyalar kurallara göre kendiliğinden kartlara yerleşir.",
                cfg.get("auto_sort", False), app.set_auto_sort),
            row("Karta konan simgeleri masaüstünde gizle",
                "Bir dosya karta yerleşince masaüstündeki simgesi gizlenir, yalnızca kartta görünür. "
                "Dosya yerinde kalır; karttan çıkarınca ya da Tuckly kapanınca simge geri gelir.",
                app.hide_assigned, app.set_hide_assigned),
            row("Masaüstü simgelerini gizle",
                "Windows'un kendi simgelerini gizler; kartsız öğeler “Diğer” kartında görünür. Çıkışta geri gelir.",
                cfg.get("hide_icons", False), app.set_hide_icons),
        ]))
        v.addSpacing(16)
        v.addWidget(group_label("Kartlar"))
        v.addSpacing(6)
        v.addWidget(make_group([
            *([row("Bildirim sayılarını göster",
                   "Bildirim merkezinde bekleyen bildirimi olan uygulamaların simgesinde sayı gösterir. "
                   "İlk açışta Windows izin isteyebilir.",
                   cfg.get("badges", False), app.set_badges)] if BADGES_AVAILABLE else []),
            row("Kartları kilitle", "Kartlar yanlışlıkla taşınamaz ve boyutlandırılamaz.",
                app.locked, app.set_locked),
            row("Windows ile başlat", "Bilgisayar açıldığında kartlar otomatik gelir.",
                app.is_autostart(), app.set_autostart),
            row("Sağ tık menüsüne ekle",
                "Masaüstünde boş alana sağ tıklayınca “Yeni Tuckly kartı”, öğelere sağ tıklayınca "
                "“Tuckly kartına ekle” seçeneği çıkar. Windows 11'de “Daha fazla seçenek göster” altındadır.",
                cfg.get("context_menu", True), app.set_context_menu),
        ]))
        v.addStretch()
        return page

    def set_page(self, i):
        if i < 0:
            return
        self.pages.setCurrentIndex(i)
        if self.sidebar.currentRow() != i:
            self.sidebar.setCurrentRow(i)
        if i == 2:
            self.refresh_plan()

    def closeEvent(self, e):
        if self.app.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()  # pencere kapatılınca uygulama tepside çalışmaya devam eder

    # ---- Kartlar
    def reload_cards(self, select=None):
        cur = select or (self.editor.fence if self.editor.fence in self.app.fences else None)
        self.card_list.blockSignals(True)
        self.card_list.clear()
        for f in self.app.fences:
            self.card_list.addItem(QListWidgetItem(""))
        self.card_list.blockSignals(False)
        self.update_names()
        if self.app.fences:
            idx = self.app.fences.index(cur) if cur in self.app.fences else 0
            self.card_list.setCurrentRow(idx)
            self.on_select(idx)
        else:
            self.editor.bind(None)

    def update_names(self):
        for i, f in enumerate(self.app.fences):
            if i < self.card_list.count():
                it = self.card_list.item(i)
                n = f.list.count()
                it.setText(f"{f.data['name']}" + (f"   ·  {n}" if n else ""))
                it.setIcon(dot_icon(seed_of(f.data.get("theme") or appearance(self.app.config)["theme"])[0]))

    def on_select(self, row):
        fence = self.app.fences[row] if 0 <= row < len(self.app.fences) else None
        self.editor.bind(fence)

    def on_new(self):
        f = self.app.new_fence()
        self.reload_cards(select=f)
        self.editor.name.setFocus()
        self.editor.name.selectAll()

    def on_add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Kartta gösterilecek klasörü seçin", str(Path.home()))
        if path:
            f = self.app.new_fence(name=Path(path).name or path, folder=path)
            self.reload_cards(select=f)

    # ---- Düzenleme
    def refresh_plan(self):
        self._plan = self.app.plan_sort()
        self.plan_list.clear()
        for p, f in self._plan:
            it = QListWidgetItem(f"{p.name}      →  {f.data['name']}")
            it.setIcon(f.icons.icon(QFileInfo(str(p))))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if self.sel_all.isChecked() else Qt.Unchecked)
            self.plan_list.addItem(it)
        if not self._plan:
            it = QListWidgetItem("Masaüstünde kurallara uyan dosya yok.")
            it.setFlags(Qt.NoItemFlags)
            self.plan_list.addItem(it)
        self.run_btn.setEnabled(bool(self._plan))

    def on_select_all(self, on):
        for i in range(len(self._plan)):
            self.plan_list.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def on_run(self):
        chosen = [self._plan[i] for i in range(len(self._plan))
                  if self.plan_list.item(i).checkState() == Qt.Checked]
        if not chosen:
            self.set_status("Taşınacak dosya seçilmedi.")
            return
        moved, errors = self.app.execute_sort(chosen)
        msg = f"{len(moved)} dosya kartlara yerleştirildi."
        self.set_status(msg)
        self.refresh_plan()

    def set_status(self, text):
        self.status.setText(text)
