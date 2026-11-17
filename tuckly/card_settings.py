"""Kart ayarları formu; hem kartın içinde hem kontrol panelinde kullanılır."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .config import CATEGORIES, ICON_SIZES, SORT_MODES
from .theme import appearance
from .widgets import SwatchRow, Toggle, group_label, label, make_group, named, segmented, setting_row


class CardSettings(QWidget):
    def __init__(self, app, in_card: bool):
        super().__init__()
        self.app = app
        self.in_card = in_card
        self.fence = None
        self._loading = False
        self.setObjectName("cardSettings")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 12) if in_card else lay.setContentsMargins(0, 0, 6, 12)
        lay.setSpacing(8)

        # --- Kart
        lay.addWidget(group_label("Kart"))
        self.name = QLineEdit()
        self.name.textEdited.connect(self.on_name)

        # Kartın kendi rengi; "Genel" seçiliyse Görünüm sayfasındaki tema kullanılır
        self.colors = SwatchRow(with_general=True, with_add=False, columns=10 if in_card else 16)
        self.colors.picked.connect(self.on_theme)
        self.theme_value = label("", "rowValue")

        # Kartın kendi opaklığı; "Genel" seçiliyse görünüm ayarlarındaki değer kullanılır
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(15, 100)
        self.opacity.valueChanged.connect(self.on_opacity)
        self.opacity_value = label("", "rowValue")
        self.op_general = named(QPushButton("Genel"), "pill")
        self.op_general.setCheckable(True)
        self.op_general.setCursor(Qt.PointingHandCursor)
        self.op_general.clicked.connect(self.on_opacity_general)
        sizes_box, self.sizes = segmented(ICON_SIZES, self.on_size)
        self._sort_keys = [k for k, _ in SORT_MODES]
        sort_box, self.sorts = segmented(tuple((t, i) for i, (_, t) in enumerate(SORT_MODES)),
                                         lambda i: self.on_sort(self._sort_keys[i]))

        rows = [
            setting_row("Ad", below=self.name),
            setting_row("Renk", "Bu karta özel renk. Genel: görünüm ayarlarındaki tema.",
                        below=self.colors, value=self.theme_value),
            setting_row("Opaklık", "Bu karta özel saydamlık.", control=self.op_general,
                        below=self.opacity, value=self.opacity_value),
            setting_row("Simge boyutu", below=sizes_box),
            setting_row("Sıralama", "Serbest: simgeleri kart içinde sürükleyerek dizersin.", below=sort_box),
        ]
        if in_card:
            b = QPushButton("Aç")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: self.app.show_panel(page=1))
            rows.append(setting_row("Görünüm ayarları", "Stil, opaklık, yazı tipi ve daha fazlası.", control=b))
        lay.addWidget(make_group(rows))

        # --- Düzen (yalnızca masaüstü kartları)
        self.rules_box = QWidget()
        rl = QVBoxLayout(self.rules_box)
        rl.setContentsMargins(0, 4, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(group_label("Bu karta ne yerleşsin"))
        cats = QWidget()
        grid = QGridLayout(cats)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        cols = 2 if in_card else 3
        self.cat_buttons = {}
        for i, (key, title, _) in enumerate(CATEGORIES):
            b = named(QPushButton(title), "pill")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self.on_categories)
            self.cat_buttons[key] = b
            grid.addWidget(b, i // cols, i % cols)
        self.rules = QLineEdit()
        self.rules.setPlaceholderText("örn: dwg, blend")
        self.rules.editingFinished.connect(self.on_rules)
        go = QPushButton("Masaüstünü düzenle")
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(lambda: self.app.show_panel(page=2))
        rl.addWidget(make_group([
            setting_row("Kategoriler", "Seçtiğin türdeki masaüstü öğeleri düzenlemede bu karta yerleşir.",
                        below=cats),
            setting_row("Ek uzantılar", "İsteğe bağlı: listede olmayan dosya türleri, virgülle ayırarak.",
                        below=self.rules),
            setting_row("Şimdi uygula", "Kartsız öğeleri kategorilere göre yerleştir.", control=go),
        ]))
        lay.addWidget(self.rules_box)

        # --- Klasör (yalnızca klasör kartları)
        self.folder_box = QWidget()
        fbl = QVBoxLayout(self.folder_box)
        fbl.setContentsMargins(0, 4, 0, 0)
        fbl.setSpacing(8)
        fbl.addWidget(group_label("Klasör"))
        self.folder = label("", "rowDesc", wrap=True)
        self.folder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.folder.setMinimumWidth(10)
        self.folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fb = QHBoxLayout()
        fb.setSpacing(6)
        b = QPushButton("Aç")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: self.fence and os.startfile(str(self.fence.folder)))
        fb.addWidget(b)
        if not in_card:
            b = QPushButton("Değiştir…")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self.on_change_folder)
            fb.addWidget(b)
        fb.addStretch()
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        fl.addWidget(self.folder)
        fl.addLayout(fb)
        fbl.addWidget(make_group([setting_row("Konum", "Bu kart bir klasörü gösterir; karta bırakılan "
                                                         "dosyalar bu klasöre taşınır.", below=fw)]))
        lay.addWidget(self.folder_box)

        self.rest_info = label("Bu kart, hiçbir karta yerleştirilmemiş masaüstü öğelerini gösterir. "
                               "Yalnızca masaüstü simgeleri gizliyken görünür.", "rowDesc", wrap=True)
        lay.addWidget(self.rest_info)

        # --- Kilit
        self.lock_box = QWidget()
        kl = QVBoxLayout(self.lock_box)
        kl.setContentsMargins(0, 4, 0, 0)
        kl.setSpacing(8)
        kl.addWidget(group_label("Kilit"))
        self.locks = {}
        lock_rows = []
        for key, title, desc in (
                ("lock_pos", "Konumu kilitle", "Kart başlığından sürüklenerek taşınamaz."),
                ("lock_size", "Boyutu kilitle", "Kart köşesinden boyutlandırılamaz."),
                ("lock_content", "İçeriği kilitle", "Karta öğe eklenemez, çıkarılamaz, yeniden dizilemez; "
                                                    "öğeler yine açılabilir.")):
            t = Toggle(False)
            t.toggled.connect(lambda on, k=key: self.on_lock(k, on))
            self.locks[key] = t
            lock_rows.append(setting_row(title, desc, control=t))
        kl.addWidget(make_group(lock_rows))
        lay.addWidget(self.lock_box)

        # --- Kaldırma (satır içi onay)
        lay.addSpacing(6)
        self.remove_btn = named(QPushButton("Kartı kaldır"), "danger")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(lambda: (self.confirm.show(), self.remove_btn.hide()))
        lay.addWidget(self.remove_btn)
        self.confirm = QWidget()
        cl = QVBoxLayout(self.confirm)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.confirm_text = label("", "rowDesc", wrap=True)
        cl.addWidget(self.confirm_text)
        cr = QHBoxLayout()
        b = QPushButton("Vazgeç")
        b.clicked.connect(self.reset_confirm)
        cr.addWidget(b)
        b = named(QPushButton("Kaldır"), "danger")
        b.clicked.connect(lambda: self.app.remove_fence(self.fence))
        cr.addWidget(b)
        cl.addLayout(cr)
        lay.addWidget(self.confirm)
        self.confirm.hide()
        lay.addStretch()
        self.setEnabled(False)

    def reset_confirm(self):
        self.confirm.hide()
        self.remove_btn.show()

    def bind(self, fence):
        self.fence = fence
        self.reset_confirm()
        self.setEnabled(fence is not None)
        self.load(force=True)

    def load(self, force=False):
        f = self.fence
        if f is None:
            for w in (self.name, self.rules):
                w.clear()
            self.folder.clear()
            return
        self._loading = True
        d = f.data
        if force or not self.name.hasFocus():
            self.name.setText(d["name"])
        self.colors.set_custom(appearance(self.app.config)["custom_colors"])
        self.colors.set_value(d.get("theme"))
        self.theme_value.setText(self.colors.value_name())
        for key, t in self.locks.items():
            t.setChecked(bool(d.get(key)))
        ov = d.get("opacity")
        shown = appearance(self.app.config)["opacity"] if ov is None else ov
        self.opacity.setValue(int(shown))
        self.opacity_value.setText(f"%{int(shown)}")
        self.op_general.setChecked(ov is None)
        btn = self.sizes.button(d.get("icon_size", 36))
        if btn:
            btn.setChecked(True)
        if force or not self.rules.hasFocus():
            self.rules.setText(", ".join(d.get("rules", [])))
        for key, b in self.cat_buttons.items():
            b.setChecked(key in d.get("categories", []))
        mode = d.get("sort", "name")
        self.sorts.button(self._sort_keys.index(mode) if mode in self._sort_keys else 0).setChecked(True)
        kind = d.get("kind", "desktop")
        self.rules_box.setVisible(kind == "desktop")
        self.folder_box.setVisible(kind == "folder")
        self.rest_info.setVisible(kind == "rest")
        self.remove_btn.setVisible(kind != "rest" and not self.confirm.isVisible())
        self.confirm_text.setText(
            "Kart kaldırılacak. Klasör ve içindekiler olduğu gibi kalır." if kind == "folder" else
            "Kart kaldırılacak. İçindeki dosyalar masaüstünde olduğu gibi kalır.")
        self.folder.setText(str(f.folder) if f.folder else "")
        self._loading = False

    def _changed(self):
        if not self._loading and self.fence:
            self.app.fence_changed(self.fence, source=self)

    def on_name(self, text):
        if self.fence and text.strip():
            self.fence.data["name"] = text.strip()
            self._changed()

    def on_theme(self, key):
        if self.fence:
            self.fence.data["theme"] = key or None
            self.theme_value.setText(self.colors.value_name())
            self._changed()

    def on_opacity(self, v):
        if self.fence and not self._loading:
            self.fence.data["opacity"] = v
            self.opacity_value.setText(f"%{v}")
            self.op_general.setChecked(False)
            self._changed()

    def on_opacity_general(self, on):
        if self.fence:
            self.fence.data["opacity"] = None if on else self.opacity.value()
            self._changed()
            self.load()

    def on_lock(self, key, on):
        if self.fence and not self._loading:
            self.fence.data[key] = on
            self._changed()

    def on_size(self, s):
        if self.fence:
            self.fence.data["icon_size"] = s
            self._changed()

    def on_sort(self, mode):
        if self.fence:
            if mode == "manual" and self.fence.data.get("sort") != "manual":
                # Serbest sıralama o anki dizilişten başlar
                lst = self.fence.list
                self.fence.data["order"] = [os.path.normcase(os.path.abspath(lst.item(i).data(Qt.UserRole)))
                                            for i in range(lst.count())]
            self.fence.data["sort"] = mode
            self.fence.refresh()
            self._changed()

    def on_categories(self):
        if self.fence:
            self.fence.data["categories"] = [k for k, b in self.cat_buttons.items() if b.isChecked()]
            self._changed()

    def on_rules(self):
        if self.fence:
            text = self.rules.text()
            self.fence.data["rules"] = [r.strip().lower().lstrip(".")
                                        for r in text.replace(";", ",").replace(" ", ",").split(",") if r.strip()]
            self._changed()

    def on_change_folder(self):
        if not self.fence:
            return
        path = QFileDialog.getExistingDirectory(self.window(), "Kartta gösterilecek klasörü seçin",
                                                str(self.fence.folder or ""))
        if path:
            self.fence.set_folder(path)
            self._changed()
