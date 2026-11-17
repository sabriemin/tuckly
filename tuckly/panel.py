"""Kontrol paneli: Tuckly'nin ayar penceresi.

Düzen: solda simgeli gezinme ve arama, sağda sayfalar. Her sayfa bir başlık ve tek bir kaydırma
alanından oluşur; ayarlar `setting_row` ile tek tip satırlar halinde gruplanır.
"""

import os
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
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

from . import __version__
from .i18n import LANGUAGES, current_language, mark, t
from .config import APP_NAME, DATA_DIR, DEFAULT_FONT, REPO_URL
from .winapi import set_dark_titlebar
from .theme import ACCENT_MODES, STYLES, appearance, dot_icon, make_app_icon, panel_look, panel_style, seed_of
from .widgets import (
    NavButton,
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

# Sayfalar: (ad, simge). Sıra, sayfa numaralarını belirler.
NAV = (
    (mark("Kartlar"), ""),
    (mark("Görünüm"), ""),
    (mark("Düzenle"), ""),
    (mark("Seçenekler"), ""),
    (mark("Rehber"), ""),
    (mark("Hakkında"), ""),
)
PAGE_CARDS, PAGE_LOOK, PAGE_SORT, PAGE_OPTIONS, PAGE_GUIDE, PAGE_ABOUT, PAGE_SEARCH = range(7)

# Rehber sayfasındaki konular: (simge, başlık, açıklama)
GUIDE = (
    ("", mark("Kart oluşturma"),
     mark("Kartlar sayfasında “+  Yeni kart”a basın ya da masaüstünde boş bir alana sağ tıklayıp "
          "“Yeni Tuckly kartı”nı seçin.")),
    ("", mark("Karta öğe ekleme"),
     mark("Masaüstündeki bir dosyayı ya da kısayolu kartın üzerine sürükleyin. Dosya yerinde kalır; "
          "simgesi masaüstünde gizlenir ve yalnızca kartta görünür.")),
    ("", mark("Öğeyi karttan çıkarma"),
     mark("Öğeyi kartın dışına sürükleyin ya da sağ tıklayıp “Karttan çıkar”ı seçin. Simge masaüstüne geri gelir.")),
    ("", mark("Taşıma ve boyutlandırma"),
     mark("Kartı başlığından sürükleyerek taşıyın, sağ alt köşesinden boyutlandırın. Başlığa çift tıklamak "
          "kartı daraltır ya da genişletir.")),
    ("", mark("Ad değiştirme"),
     mark("Kart adının yanındaki kaleme tıklayın, yeni adı yazıp Enter'a basın.")),
    ("", mark("Kart ayarları"),
     mark("Karttaki dişli düğmesi o kartın rengini, opaklığını, sıralamasını, kategorilerini ve kilitlerini açar.")),
    ("", mark("Otomatik düzenleme"),
     mark("Her karta hangi tür öğelerin yerleşeceğini kategorilerden seçin. Sonra Düzenle sayfasından "
          "kartsız öğeleri tek seferde kartlara yerleştirin.")),
    ("", mark("Çıkış"),
     mark("Tuckly kapanınca gizlenen simgeler masaüstüne geri gelir; dosyalarınız hiçbir zaman taşınmaz.")),
)


class ControlPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("panel")
        self.setAttribute(Qt.WA_StyledBackground)
        self.apply_look()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.resize(980, 700)
        self.setMinimumSize(900, 580)
        self._plan = []
        self._rows = []       # (sayfa, ayar satırı): ayarlarda arama için
        self._last_page = PAGE_CARDS

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        content = QVBoxLayout()
        content.setContentsMargins(28, 22, 20, 12)
        content.setSpacing(6)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        self.status = named(QLabel(""), "status")
        self.status.setWordWrap(True)
        content.addWidget(self.status)
        root.addLayout(content, 1)

        for build in (self._cards_page, self._appearance_page, self._sort_page, self._options_page,
                      self._guide_page, self._about_page, self._search_page):
            self.pages.addWidget(build())
        self.set_page(PAGE_CARDS)
        self.reload_cards()

    # ---------------------------------------------------------------- kenar çubuğu
    def _sidebar(self):
        frame = named(QFrame(), "sidebar")
        frame.setAttribute(Qt.WA_StyledBackground)
        frame.setFixedWidth(220)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 16, 12, 14)
        v.setSpacing(3)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 10)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(30, 30))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "brand"))
        names.addWidget(label(t("Masaüstü düzenleyici"), "brandSub", wrap=True))  # uzun çevirilerde alt satıra geçer
        brand.addLayout(names, 1)
        v.addLayout(brand)

        self.search = named(QLineEdit(), "search")
        self.search.setPlaceholderText(t("Ayarlarda ara"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.on_search)
        v.addWidget(self.search)
        v.addSpacing(8)

        self.nav = []
        self.nav_group = QButtonGroup(self)
        for i, (title, glyph) in enumerate(NAV):
            b = NavButton(glyph, t(title))
            b.clicked.connect(lambda _=False, i=i: self.set_page(i))
            self.nav_group.addButton(b, i)
            self.nav.append(b)
            v.addWidget(b)
        v.addStretch()

        quit_btn = QPushButton(t("Uygulamadan çık"))
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self.app.quit)
        v.addWidget(quit_btn)
        return frame

    # ---------------------------------------------------------------- ortak yardımcılar
    def _page(self, title, desc, scroll=True):
        """Bir sayfa iskeleti kurar: sabit başlık + (istenirse) tek bir kaydırma alanı.
        (sayfa, içerik düzeni) döndürür."""
        page = named(QWidget(), "page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(label(title, "pageTitle"))
        d = label(desc, "pageDesc", wrap=True)
        d.setContentsMargins(0, 2, 8, 14)
        outer.addWidget(d)
        body = named(QWidget(), "page")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8 if scroll else 0, 12)
        v.setSpacing(8)
        if scroll:
            page.area = scroll_wrap(body)
            outer.addWidget(page.area, 1)
        else:
            outer.addWidget(body, 1)
        return page, v

    def _row(self, page_index, title, desc=None, **kw):
        """Ayar satırı oluşturur ve aramada bulunabilmesi için kaydeder."""
        row = setting_row(title, desc, **kw)
        self._rows.append((page_index, row))
        return row

    def _section(self, layout, title, rows, first=False):
        if not first:
            layout.addSpacing(10)
        layout.addWidget(group_label(title))
        layout.addWidget(make_group(rows))

    @staticmethod
    def _button(text, slot, name=None):
        b = QPushButton(text)
        if name:
            b.setObjectName(name)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def showEvent(self, e):
        super().showEvent(e)
        set_dark_titlebar(self, not self.look.light)
        self.setFocus()  # açılışta arama kutusu seçili görünmesin

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

    def set_page(self, i):
        if i < 0:
            return
        self.pages.setCurrentIndex(i)
        if i < len(self.nav):
            self.nav[i].setChecked(True)
            self._last_page = i
        if i == PAGE_SORT:
            self.refresh_plan()

    def closeEvent(self, e):
        if self.app.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()  # pencere kapatılınca uygulama tepside çalışmaya devam eder

    def set_status(self, text):
        self.status.setText(text)

    # ---------------------------------------------------------------- Kartlar
    def _cards_page(self):
        page, v = self._page(t("Kartlar"), t("Kartlarınızı seçip düzenleyin. Aynı ayarlara her kartın dişli "
                                              "düğmesinden de ulaşabilirsiniz."), scroll=False)
        h = QHBoxLayout()
        h.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(group_label(t("Kartlarım")))
        self.card_list = named(QListWidget(), "rowList")
        self.card_list.setIconSize(QSize(14, 14))
        self.card_list.currentRowChanged.connect(self.on_select)
        left.addWidget(self.card_list, 1)
        left.addWidget(self._button(t("+  Yeni kart"), self.on_new, "primary"))
        left.addWidget(self._button(t("Klasörü kart olarak ekle…"), self.on_add_folder))
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(220)
        h.addWidget(lw)
        self.editor = CardSettings(self.app, in_card=False)
        h.addWidget(scroll_wrap(self.editor), 1)
        v.addLayout(h, 1)
        return page

    def reload_cards(self, select=None):
        cur = select or (self.editor.fence if self.editor.fence in self.app.fences else None)
        self.card_list.blockSignals(True)
        self.card_list.clear()
        for _ in self.app.fences:
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
        path = QFileDialog.getExistingDirectory(self, t("Kartta gösterilecek klasörü seçin"), str(Path.home()))
        if path:
            f = self.app.new_fence(name=Path(path).name or path, folder=path)
            self.reload_cards(select=f)

    # ---------------------------------------------------------------- Görünüm
    def _appearance_page(self):
        page, v = self._page(t("Görünüm"), t("Kartların stili, renkleri ve yazıları. Değişiklikler anında uygulanır."))
        ap, setv, P = appearance(self.app.config), self.app.set_appearance, PAGE_LOOK

        # Stil
        v.addWidget(group_label(t("Stil")))
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.style_tiles = QButtonGroup(self)
        for key, title in STYLES:
            col = QVBoxLayout()
            col.setSpacing(4)
            tile = StyleTile(key)
            tile.setChecked(ap["style"] == key)
            tile.clicked.connect(lambda _=False, k=key: setv("style", k))
            self.style_tiles.addButton(tile)
            col.addWidget(tile)
            nm = label(t(title), "tileName")
            nm.setAlignment(Qt.AlignHCenter)
            col.addWidget(nm)
            tiles.addLayout(col)
        tiles.addStretch()
        v.addLayout(tiles)

        def slider(key, lo, hi, fmt="%{}"):
            s = QSlider(Qt.Horizontal)
            s.setRange(lo, hi)
            s.setValue(int(ap[key]))
            val = label(fmt.format(int(ap[key])), "rowValue")
            val.setMinimumWidth(44)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            s.valueChanged.connect(lambda x: (val.setText(fmt.format(x)), setv(key, x)))
            return s, val

        def toggle(key):
            tg = Toggle(ap[key])
            tg.toggled.connect(lambda on: setv(key, on))
            return tg

        # Renk
        mode_box, mode_group = segmented(((t("Koyu"), 0), (t("Açık"), 1)),
                                         lambda i: setv("mode", "light" if i else "dark"))
        mode_group.button(1 if ap["mode"] == "light" else 0).setChecked(True)

        self.theme_row = SwatchRow(with_general=False, with_add=True)
        self.theme_row.set_custom(ap["custom_colors"])
        self.theme_row.set_value(ap["theme"])
        self.theme_value = label(self.theme_row.value_name(), "rowValue")
        self.theme_row.picked.connect(self.on_theme_picked)
        self.theme_row.added.connect(self.on_color_added)

        keys = [k for k, _ in ACCENT_MODES]
        accent_box, accent_group = segmented(tuple((title, i) for i, (_, title) in enumerate(ACCENT_MODES)),
                                             lambda i: self.on_accent_mode(keys[i]))
        accent_group.button(keys.index(ap["accent"]) if ap["accent"] in keys else 0).setChecked(True)
        self.accent_pick = self._button(t("Renk seç…"), self.on_accent_pick)
        self.accent_pick.setVisible(ap["accent"] == "custom")
        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)
        accent_row.addWidget(accent_box)
        accent_row.addWidget(self.accent_pick)
        accent_row.addStretch()

        op, op_v = slider("opacity", 15, 100)
        sat, sat_v = slider("saturation", 0, 100)
        br, br_v = slider("brightness", 0, 100)
        self._section(v, t("Renk"), [
            self._row(P, t("Tema modu"), t("Koyu ya da açık zemin."), control=mode_box, icon=""),
            self._row(P, t("Hazır temalar"), t("Tek tıkla renk temaları; + ile kendi rengini ekle."),
                      below=self.theme_row, value=self.theme_value, icon=""),
            self._row(P, t("Vurgu rengi"), t("Anahtarlar, düğmeler ve kaydırıcılar için renk."),
                      below=accent_row, icon=""),
            self._row(P, t("Arka plan opaklığı"), t("Kartların ne kadar saydam olacağı."),
                      below=op, value=op_v, icon=""),
            self._row(P, t("Renk doygunluğu"), t("Arka planın ne kadar canlı olacağı."),
                      below=sat, value=sat_v, icon=""),
            self._row(P, t("Arka plan parlaklığı"), t("Arka planın ne kadar açık olacağı."),
                      below=br, value=br_v, icon=""),
        ])

        # Şekil
        rad, rad_v = slider("radius", 0, 20, "{} px")
        brd, brd_v = slider("border", 0, 100)
        self._section(v, t("Şekil"), [
            self._row(P, t("Köşe yuvarlaklığı"), t("Kartların köşeleri ne kadar yuvarlak olsun."),
                      below=rad, value=rad_v, icon=""),
            self._row(P, t("Kenarlık"), t("Kart çevresindeki çizginin belirginliği. %0: çizgi yok."),
                      below=brd, value=brd_v, icon=""),
            self._row(P, t("Simge karoları"), t("Dosya simgelerinin arkasında yuvarlak karo göster."),
                      control=toggle("tiles"), icon=""),
            self._row(P, t("Büyüme efekti"), t("İmleç bir simgenin üzerine gelince simge hafifçe büyür."),
                      control=toggle("animations"), icon=""),
        ])

        # Yazı: her biri kendi yazı tipiyle gösterilen, aranabilir bir liste
        current = ap["font_family"] or DEFAULT_FONT
        font_filter = QLineEdit()
        font_filter.setPlaceholderText(t("Yazı tipi ara…"))
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
        font_filter.textChanged.connect(lambda query: [
            font_list.item(i).setHidden(query.strip().lower() not in font_list.item(i).text().lower())
            for i in range(font_list.count())])
        font_box = QWidget()
        fbl = QVBoxLayout(font_box)
        fbl.setContentsMargins(0, 0, 0, 0)
        fbl.setSpacing(6)
        fbl.addWidget(font_filter)
        fbl.addWidget(font_list)
        size, size_v = slider("font_size", 8, 14, "{} pt")
        self._section(v, t("Yazı"), [
            self._row(P, t("Yazı tipi"), t("Kart başlıkları ve dosya adları için."), below=font_box, icon=""),
            self._row(P, t("Boyut"), below=size, value=size_v, icon=""),
            self._row(P, t("Kalın"), control=toggle("font_bold"), icon=""),
            self._row(P, t("İtalik"), control=toggle("font_italic"), icon=""),
        ])

        v.addSpacing(8)
        row = QHBoxLayout()
        row.addWidget(self._button(t("Görünümü varsayılana döndür"), self.app.reset_appearance))
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return page

    def reload_appearance(self):
        """Görünüm sayfasını ayarlardaki değerlerle yeniden kurar (sıfırlamadan sonra)."""
        self._rows = [(p, r) for p, r in self._rows if p != PAGE_LOOK]
        old = self.pages.widget(PAGE_LOOK)
        self.pages.removeWidget(old)
        old.deleteLater()
        self.pages.insertWidget(PAGE_LOOK, self._appearance_page())
        self.pages.setCurrentIndex(self._last_page)

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
        c = QColorDialog.getColor(QColor(ap["accent_color"]), self, t("Vurgu rengi seç"))
        if c.isValid():
            self.app.set_appearance("accent_color", c.name())

    # ---------------------------------------------------------------- Düzenle
    def _sort_page(self):
        page, v = self._page(t("Masaüstünü düzenle"),
                             t("Henüz bir karta yerleşmemiş masaüstü öğeleri kartların kategorilerine "
                               "göre listelenir. Dosyalar taşınmaz; masaüstünde kalıp kartta görünürler."), scroll=False)
        top = QHBoxLayout()
        top.addWidget(group_label(t("Yerleştirilecek dosyalar")))
        top.addStretch()
        top.addWidget(label(t("Tümünü seç"), "rowDesc"))
        self.sel_all = Toggle(True)
        self.sel_all.toggled.connect(self.on_select_all)
        top.addWidget(self.sel_all)
        v.addLayout(top)
        self.plan_list = named(QListWidget(), "rowList")
        v.addWidget(self.plan_list, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._button(t("Listeyi yenile"), self.refresh_plan))
        row.addWidget(self._button(t("Son düzenlemeyi geri al"), self.app.undo_last))
        row.addStretch()
        self.run_btn = self._button(t("Seçilenleri kartlara yerleştir"), self.on_run, "primary")
        row.addWidget(self.run_btn)
        v.addLayout(row)
        return page

    def refresh_plan(self):
        self._plan = self.app.plan_sort()
        self.plan_list.clear()
        for p, f in self._plan:
            it = QListWidgetItem(f"{p.name}      →  {f.data['name']}")
            it.setIcon(self.app.icon_for(p))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if self.sel_all.isChecked() else Qt.Unchecked)
            self.plan_list.addItem(it)
        if not self._plan:
            it = QListWidgetItem(t("Masaüstünde kurallara uyan dosya yok."))
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
            self.set_status(t("Taşınacak dosya seçilmedi."))
            return
        moved, _ = self.app.execute_sort(chosen)
        self.set_status(t('{0} dosya kartlara yerleştirildi.').format(len(moved)))
        self.refresh_plan()

    # ---------------------------------------------------------------- Seçenekler
    def _options_page(self):
        page, v = self._page(t("Seçenekler"), t("Kartların ve masaüstünün genel davranışı."))
        cfg, app, P = self.app.config, self.app, PAGE_OPTIONS

        def row(title, desc, checked, slot, icon):
            toggle = Toggle(checked)
            toggle.toggled.connect(slot)
            return self._row(P, title, desc, control=toggle, icon=icon)

        self._section(v, t("Masaüstü"), [
            row(t("Yeni dosyaları otomatik düzenle"),
                t("Masaüstüne gelen yeni dosyalar kurallara göre kendiliğinden kartlara yerleşir."),
                cfg.get("auto_sort", False), app.set_auto_sort, ""),
            row(t("Karta konan simgeleri masaüstünde gizle"),
                t("Bir dosya karta yerleşince masaüstündeki simgesi gizlenir, yalnızca kartta görünür. "
                  "Dosya yerinde kalır; karttan çıkarınca ya da Tuckly kapanınca simge geri gelir."),
                app.hide_assigned, app.set_hide_assigned, ""),
            row(t("Masaüstü simgelerini gizle"),
                t("Windows'un kendi simgelerini gizler; kartsız öğeler “Diğer” kartında görünür. Çıkışta geri gelir."),
                cfg.get("hide_icons", False), app.set_hide_icons, ""),
        ], first=True)
        self._section(v, t("Kartlar"), [
            *([row(t("Bildirim sayılarını göster"),
                   t("Bildirim merkezinde bekleyen bildirimi olan uygulamaların simgesinde sayı gösterir. "
                     "İlk açışta Windows izin isteyebilir."),
                   cfg.get("badges", False), app.set_badges, "")] if BADGES_AVAILABLE else []),
            row(t("Kartları kilitle"), t("Kartlar yanlışlıkla taşınamaz ve boyutlandırılamaz."),
                app.locked, app.set_locked, ""),
            row(t("Windows ile başlat"), t("Bilgisayar açıldığında kartlar otomatik gelir."),
                app.is_autostart(), app.set_autostart, ""),
            row(t("Sağ tık menüsüne ekle"),
                t("Masaüstünde boş alana sağ tıklayınca “Yeni Tuckly kartı”, öğelere sağ tıklayınca "
                  "“Tuckly kartına ekle” seçeneği çıkar. Windows 11'de “Daha fazla seçenek göster” altındadır."),
                cfg.get("context_menu", True), app.set_context_menu, ""),
        ])

        # Dil
        langs = QWidget()
        grid = QGridLayout(langs)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.lang_group = QButtonGroup(self)
        for i, (code, name) in enumerate(LANGUAGES):
            b = named(QPushButton(name), "pill")
            b.setCheckable(True)
            b.setChecked(code == current_language())
            b.setCursor(Qt.PointingHandCursor)
            # Arayüz yeniden kurulacağı için düğmenin kendi tıklaması bittikten sonra uygula
            b.clicked.connect(lambda _=False, c=code: QTimer.singleShot(0, lambda: app.set_language(c)))
            self.lang_group.addButton(b)
            grid.addWidget(b, i // 3, i % 3)
        self._section(v, t("Dil"), [
            self._row(P, t("Arayüz dili"), t("Seçtiğiniz dil hemen uygulanır."), below=langs, icon=""),
        ])

        # Ayar dosyası; sıfırlama iki adımlı: yanlışlıkla tıklanmasın
        reset_box = QWidget()
        rb = QHBoxLayout(reset_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(6)
        reset = named(QPushButton(t("Sıfırla…")), "danger")
        yes = named(QPushButton(t("Evet, sıfırla")), "danger")
        no = QPushButton(t("Vazgeç"))
        for b in (reset, yes, no):
            b.setCursor(Qt.PointingHandCursor)
            rb.addWidget(b)
        yes.hide()
        no.hide()
        reset.clicked.connect(lambda: (reset.hide(), yes.show(), no.show()))
        no.clicked.connect(lambda: (yes.hide(), no.hide(), reset.show()))
        yes.clicked.connect(lambda: QTimer.singleShot(0, app.reset_settings))
        self._section(v, t("Ayarlar"), [
            self._row(P, t("Ayarları dışa aktar"), t("Kartlarınızı ve tüm ayarları bir dosyaya kaydeder."),
                      control=self._button(t("Dışa aktar…"), self.on_export), icon=""),
            self._row(P, t("Ayarları içe aktar"),
                      t("Daha önce kaydedilmiş bir ayar dosyasını yükler; mevcut ayarların yerini alır."),
                      control=self._button(t("İçe aktar…"), self.on_import), icon=""),
            self._row(P, t("Varsayılanlara sıfırla"),
                      t("Tüm kartlar ve ayarlar silinir, ilk kurulumdaki haline döner. Dosyalarınıza dokunulmaz."),
                      control=reset_box, icon=""),
        ])
        v.addStretch()
        return page

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, t("Ayarları dışa aktar"),
                                              str(Path.home() / "tuckly-settings.json"), "JSON (*.json)")
        if path:
            ok = self.app.export_settings(path)
            self.set_status(t("Ayarlar kaydedildi: {0}").format(path) if ok else t("Ayarlar kaydedilemedi."))

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, t("Ayarları içe aktar"), str(Path.home()), "JSON (*.json)")
        if path:
            QTimer.singleShot(0, lambda: self.app.import_settings(path))

    # ---------------------------------------------------------------- Rehber
    def _guide_page(self):
        page, v = self._page(t("Rehber"), t("Tuckly'nin nasıl kullanıldığını kısaca anlatır."))
        P = PAGE_GUIDE
        self._section(v, t("Hızlı başlangıç"), [
            self._row(P, t("Rehber turu"), t("Kartları ve ayarları ekranda adım adım gösterir."),
                      control=self._button(t("Turu başlat"), self.app.start_tour, "primary"), icon=""),
        ], first=True)
        self._section(v, t("Nasıl yapılır"),
                      [self._row(P, t(title), t(text), icon=glyph) for glyph, title, text in GUIDE])
        v.addStretch()
        return page

    # ---------------------------------------------------------------- Hakkında
    def _about_page(self):
        page, v = self._page(t("Hakkında"), t("Sürüm, destek ve proje bağlantıları."))
        P = PAGE_ABOUT
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 0, 6)
        head.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(60, 60))
        head.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(label(APP_NAME, "aboutName"))
        names.addWidget(label(t("Sürüm {0}").format(__version__) + "  ·  GPL-3.0", "aboutSub"))
        head.addLayout(names, 1)
        v.addLayout(head)

        if REPO_URL:  # depo adresi girilene kadar GitHub düğmeleri gösterilmez
            def link(url):
                return lambda: QDesktopServices.openUrl(QUrl(url))

            self._section(v, t("Projeyi destekleyin"), [
                self._row(P, t("GitHub'da yıldız verin"), t("Projeyi desteklemenin en kolay yolu."),
                          control=self._button(t("Yıldız ver"), link(REPO_URL), "primary"), icon=""),
                self._row(P, t("Sorun bildirin ya da öneride bulunun"), t("Hata ve istekler GitHub üzerinden izlenir."),
                          control=self._button(t("Aç"), link(REPO_URL + "/issues")), icon=""),
                self._row(P, t("Sürümler"), t("Yeni sürümler ve değişiklik notları."),
                          control=self._button(t("Aç"), link(REPO_URL + "/releases")), icon=""),
            ])
        self._section(v, t("Uygulama"), [
            self._row(P, t("Rehber turu"), t("Kartları ve ayarları ekranda adım adım gösterir."),
                      control=self._button(t("Turu başlat"), self.app.start_tour), icon=""),
            self._row(P, t("Ayar klasörü"), str(DATA_DIR),
                      control=self._button(t("Aç"), lambda: os.startfile(str(DATA_DIR))), icon=""),
            self._row(P, t("Lisans"), t("Tuckly özgür bir yazılımdır; GPL-3.0 lisansıyla dağıtılır."), icon=""),
        ], first=not REPO_URL)
        v.addStretch()
        return page

    # ---------------------------------------------------------------- Arama
    def _search_page(self):
        page, v = self._page(t("Arama sonuçları"), t("Bir sonuca tıklayınca ilgili ayara gidilir."), scroll=False)
        self.results = named(QListWidget(), "rowList")
        self.results.itemClicked.connect(self.on_result)
        v.addWidget(self.results, 1)
        return page

    def on_search(self, text):
        query = text.strip().lower()
        if not query:
            self.set_page(self._last_page)
            return
        self.results.clear()
        for i, (page_index, row) in enumerate(self._rows):
            if query in f"{row.row_title} {row.row_desc}".lower():
                it = QListWidgetItem(f"{row.row_title}    ·  {t(NAV[page_index][0])}")
                it.setData(Qt.UserRole, i)
                it.setToolTip(row.row_desc)
                self.results.addItem(it)
        if not self.results.count():
            it = QListWidgetItem(t("Eşleşen ayar bulunamadı."))
            it.setFlags(Qt.NoItemFlags)
            self.results.addItem(it)
        self.pages.setCurrentIndex(PAGE_SEARCH)
        checked = self.nav_group.checkedButton()
        if checked:  # arama sırasında hiçbir sayfa seçili görünmesin
            self.nav_group.setExclusive(False)
            checked.setChecked(False)
            self.nav_group.setExclusive(True)

    def on_result(self, item):
        index = item.data(Qt.UserRole)
        if index is None:
            return
        page_index, row = self._rows[index]
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.set_page(page_index)
        self.reveal(row)

    def reveal(self, row):
        """Bir ayar satırını görünür alana kaydırır ve kısa süre vurgular."""
        area = getattr(self.pages.currentWidget(), "area", None)
        if area:
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(row, 0, 80))

        def flash(on):
            row.setProperty("flash", "true" if on else "false")
            row.style().unpolish(row)
            row.style().polish(row)

        flash(True)
        QTimer.singleShot(1400, lambda: flash(False))
