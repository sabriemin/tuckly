"""Kart ayarları formu; hem kartın ayar penceresinde hem kontrol panelinde kullanılır.

Üç sekme vardır: Genel (ad, renk, opaklık, simge boyutu, sıralama), İçerik (kategoriler ya da
klasör) ve Kilit (kilitler ve kartı kaldırma). Sekmeler sayesinde form kaydırma gerektirmeden sığar.
"""

import os

from PySide6.QtCore import QDateTime, QTime, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QApplication,
    QDateTimeEdit,
    QTimeEdit,
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

from .i18n import t
from .config import CATEGORIES, DAYS, EMOJIS, ICON_SIZES, NOTE_SIZES, PAPERS, SORT_MODES
from .theme import appearance
from .widgets import SwatchRow, Toggle, label, make_group, named, segmented, setting_row


class CardSettings(QWidget):
    def __init__(self, app, in_card: bool):
        super().__init__()
        self.app = app
        self.in_card = in_card
        self.fence = None
        self._loading = False
        self.setObjectName("cardSettings")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 2, 12, 12) if in_card else lay.setContentsMargins(0, 0, 6, 12)
        lay.setSpacing(10)

        tab_box, self.tabs = segmented(((t("Temel"), 0), (t("İçerik"), 1), (t("Davranış"), 2), (t("Kilit"), 3)), self.set_tab)
        lay.addWidget(tab_box)
        # Sekmeler alt alta eklenir, yalnızca seçili olan gösterilir: form her zaman o sekmenin boyundadır
        self.pages = [build() for build in (self._general_tab, self._content_tab, self._behaviour_tab, self._lock_tab)]
        for page in self.pages:
            lay.addWidget(page)
        lay.addStretch()
        self.set_tab(0)
        self.setEnabled(False)

    @staticmethod
    def _tab():
        page = named(QWidget(), "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        return page, v

    def set_tab(self, index):
        self.tabs.button(index).setChecked(True)
        for i, page in enumerate(self.pages):
            page.setVisible(i == index)

    # ---------------------------------------------------------------- Genel
    def _general_tab(self):
        page, v = self._tab()
        self.name = QLineEdit()
        self.name.textEdited.connect(self.on_name)
        # Başlıkta adın önünde gösterilen simge (emoji); ilk düğme "simge yok"
        name_box = QWidget()
        nb = QVBoxLayout(name_box)
        nb.setContentsMargins(0, 0, 0, 0)
        nb.setSpacing(6)
        nb.addWidget(self.name)
        emoji_row = QHBoxLayout()
        emoji_row.setContentsMargins(0, 0, 0, 0)
        emoji_row.setSpacing(4)
        self.emojis = QButtonGroup(self)
        self._emoji_values = ("",) + EMOJIS
        for i, value in enumerate(self._emoji_values):
            b = named(QPushButton(value or "–"), "emoji")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(27, 26)
            b.setFont(QFont("Segoe UI Emoji", 10))
            b.setToolTip(t("Başlık simgesi") if value else t("Simge yok"))
            self.emojis.addButton(b, i)
            emoji_row.addWidget(b)
        emoji_row.addStretch()
        self.emojis.idClicked.connect(self.on_emoji)
        nb.addLayout(emoji_row)

        # Kartın kendi rengi; "Genel" seçiliyse Görünüm sayfasındaki tema kullanılır
        self.colors = SwatchRow(with_general=True, with_add=False, columns=10)
        self.colors.picked.connect(self.on_theme)
        self.theme_value = label("", "rowValue")

        # Kartın kendi opaklığı; "Genel" seçiliyse görünüm ayarlarındaki değer kullanılır
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(15, 100)
        self.opacity.valueChanged.connect(self.on_opacity)
        self.opacity_value = label("", "rowValue")
        self.op_general = named(QPushButton(t("Genel")), "pill")
        self.op_general.setCheckable(True)
        self.op_general.setCursor(Qt.PointingHandCursor)
        self.op_general.clicked.connect(self.on_opacity_general)

        sizes_box, self.sizes = segmented(ICON_SIZES, self.on_size)
        self._sort_keys = [k for k, _ in SORT_MODES]
        sort_box, self.sorts = segmented(tuple((title, i) for i, (_, title) in enumerate(SORT_MODES)),
                                         lambda i: self.on_sort(self._sort_keys[i]))
        rows = [
            setting_row(t("Ad"), below=name_box, icon=""),
            setting_row(t("Renk"), t("Bu karta özel renk. Genel: görünüm ayarlarındaki tema."),
                        below=self.colors, value=self.theme_value, icon=""),
            setting_row(t("Opaklık"), t("Bu karta özel saydamlık."), control=self.op_general,
                        below=self.opacity, value=self.opacity_value, icon=""),
        ]
        v.addWidget(make_group(rows))
        # Dosya kartlarına özel
        self.file_group = make_group([
            setting_row(t("Simge boyutu"), below=sizes_box, icon=""),
            setting_row(t("Sıralama"), t("Serbest: simgeleri kart içinde sürükleyerek dizersin."),
                        below=sort_box, icon=""),
        ])
        v.addWidget(self.file_group)
        # Not kartına özel: yazı boyutu, kâğıt rengi, satır kaydırma
        note_size_box, self.note_sizes = segmented(NOTE_SIZES, self.on_note_size)
        paper_box = QWidget()
        pr = QHBoxLayout(paper_box)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(6)
        self.papers = QButtonGroup(self)
        self._paper_values = ("",) + PAPERS
        for i, value in enumerate(self._paper_values):
            b = QPushButton("–" if not value else "")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(26, 26)
            b.setToolTip(t("Kart rengi") if not value else t("Kâğıt rengi"))
            if value:
                b.setStyleSheet(f"QPushButton {{ background: {value}; border: 2px solid transparent; border-radius: 13px; }}"
                                "QPushButton:checked { border-color: #0a84ff; }")
            else:
                b.setObjectName("emoji")
            self.papers.addButton(b, i)
            pr.addWidget(b)
        pr.addStretch()
        self.papers.idClicked.connect(self.on_paper)
        self.note_wrap = Toggle(True)
        self.note_wrap.toggled.connect(self.on_note_wrap)
        self.note_group = make_group([
            setting_row(t("Yazı boyutu"), below=note_size_box, icon="\uE8E9"),
            setting_row(t("Kâğıt rengi"), t("Yapışkan not görünümü: düz renkli kâğıt ve koyu yazı."),
                        below=paper_box, icon="\uE790"),
        ])
        v.addWidget(self.note_group)
        return page

    # ---------------------------------------------------------------- İçerik
    def _content_tab(self):
        page, v = self._tab()

        # Masaüstü kartı: kategoriler
        cats = QWidget()
        grid = QGridLayout(cats)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        cols = 2 if self.in_card else 3
        self.cat_buttons = {}
        for i, (key, title, _) in enumerate(CATEGORIES):
            b = named(QPushButton(t(title)), "pill")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self.on_categories)
            self.cat_buttons[key] = b
            grid.addWidget(b, i // cols, i % cols)
        self.rules = QLineEdit()
        self.rules.setPlaceholderText(t("örn: dwg, blend"))
        self.rules.editingFinished.connect(self.on_rules)
        self.name_rules = QLineEdit()
        self.name_rules.setPlaceholderText(t("örn: fatura, rapor"))
        self.name_rules.editingFinished.connect(self.on_name_rules)
        go = QPushButton(t("Masaüstünü düzenle"))
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(lambda: self.app.show_panel(page=2))
        self.rules_box = make_group([
            setting_row(t("Kategoriler"), t("Seçtiğin türdeki masaüstü öğeleri düzenlemede bu karta yerleşir."),
                        below=cats, icon=""),
            setting_row(t("Ek uzantılar"), t("İsteğe bağlı: listede olmayan dosya türleri, virgülle ayırarak."),
                        below=self.rules, icon=""),
            setting_row(t("Ada göre"), t("Adında bu sözcüklerden biri geçen öğeler, türü ne olursa olsun bu karta yerleşir."),
                        below=self.name_rules, icon="\uE8AC"),
            setting_row(t("Şimdi uygula"), t("Kartsız öğeleri kategorilere göre yerleştir."), control=go,
                        icon=""),
        ])
        v.addWidget(self.rules_box)

        # Klasör kartı: konum
        self.folder = label("", "rowDesc", wrap=True)
        self.folder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.folder.setMinimumWidth(10)
        self.folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fb = QHBoxLayout()
        fb.setSpacing(6)
        b = QPushButton(t("Aç"))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: self.fence and os.startfile(str(self.fence.folder)))
        fb.addWidget(b)
        if not self.in_card:
            b = QPushButton(t("Değiştir…"))
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
        self.folder_box = make_group([
            setting_row(t("Konum"), t("Bu kart bir klasörü gösterir; karta bırakılan dosyalar bu klasöre taşınır."),
                        below=fw, icon=""),
        ])
        v.addWidget(self.folder_box)

        # "Diğer" kartı: açıklama
        self.rest_info = make_group([
            setting_row(t("Kartsız öğeler"),
                        t("Bu kart, hiçbir karta yerleştirilmemiş masaüstü öğelerini gösterir. "
                          "Yalnızca masaüstü simgeleri gizliyken görünür."), icon=""),
        ])
        v.addWidget(self.rest_info)

        # Son kullanılanlar kartı: açıklama ve öğe sayısı
        count_box, self.recent_counts = segmented((("10", 10), ("20", 20), ("30", 30)), self.on_recent_count)
        self.recent_info = make_group([
            setting_row(t("Son kullanılanlar"),
                        t("Windows'ta en son açtığınız dosyaları gösterir; liste kendiliğinden güncellenir. "
                          "Karta öğe eklenmez ve dosyalara dokunulmaz."), icon="\uE81C"),
            setting_row(t("Öğe sayısı"), below=count_box, icon="\uE8FD"),
        ])
        v.addWidget(self.recent_info)

        # Not kartı: açıklama
        save_box = QWidget()
        sv = QHBoxLayout(save_box)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(6)
        for ext in ("txt", "md"):
            b = QPushButton("." + ext)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, e=ext: self.on_note_export(e))
            sv.addWidget(b)
        # Hatırlatıcı: tarih ve saat + kur / kaldır
        remind_box = QWidget()
        rm = QHBoxLayout(remind_box)
        rm.setContentsMargins(0, 0, 0, 0)
        rm.setSpacing(6)
        self.remind_at = QDateTimeEdit()
        self.remind_at.setDisplayFormat("dd.MM.yyyy  HH:mm")
        rm.addWidget(self.remind_at, 1)
        self.remind_set = named(QPushButton(t("Kur")), "primary")
        self.remind_set.setCursor(Qt.PointingHandCursor)
        self.remind_set.clicked.connect(self.on_remind_set)
        rm.addWidget(self.remind_set)
        self.remind_clear = QPushButton(t("Kaldır"))
        self.remind_clear.setCursor(Qt.PointingHandCursor)
        self.remind_clear.clicked.connect(self.on_remind_clear)
        rm.addWidget(self.remind_clear)
        self.remind_value = label("", "rowValue")
        copy = QPushButton(t("Kopyala"))
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(self.on_note_copy)
        self.note_info = make_group([
            setting_row(t("Not kartı"),
                        t("Kartın içine tıklayıp yazın; yazdıklarınız kendiliğinden kaydedilir. Alttaki düğmeler "
                          "satırı yapılacak maddesine ya da madde işaretine çevirir; Ctrl+tıklama bağlantıyı açar."),
                        icon="\uE70B"),
            setting_row(t("Satır kaydırma"), t("Uzun satırlar kartın genişliğine göre alt satıra geçer."),
                        control=self.note_wrap, icon="\uE751"),
            setting_row(t("Hatırlatıcı"), t("Zamanı gelince Windows bildirimi çıkar ve not öne gelir."),
                        below=remind_box, value=self.remind_value, icon="\uE823"),
            setting_row(t("Panoya kopyala"), t("Notun tamamını düz metin olarak kopyalar."), control=copy,
                        icon="\uE8C8"),
            setting_row(t("Dosyaya kaydet"), t("Notu metin ya da Markdown dosyası olarak kaydeder."),
                        control=save_box, icon="\uE74E"),
        ])
        v.addWidget(self.note_info)
        return page

    # ---------------------------------------------------------------- Davranış
    def _behaviour_tab(self):
        page, v = self._tab()
        self.locks = {}
        rollup = Toggle(False)
        rollup.toggled.connect(lambda on: self.on_lock("rollup", on))
        self.locks["rollup"] = rollup

        # Zamanlama: kart yalnızca seçilen gün ve saatlerde görünür
        self.schedule_on = Toggle(False)
        self.schedule_on.toggled.connect(self.on_schedule)
        sched = QWidget()
        sl = QVBoxLayout(sched)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        days = QHBoxLayout()
        days.setSpacing(4)
        self.day_buttons = []
        for name in DAYS:
            b = named(QPushButton(t(name)), "pill")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(10)
            b.setStyleSheet("padding: 3px 0;")  # yedi gün tek satıra sığsın
            b.clicked.connect(self.on_schedule)
            self.day_buttons.append(b)
            days.addWidget(b, 1)
        sl.addLayout(days)
        hours = QHBoxLayout()
        hours.setSpacing(8)
        self.time_from, self.time_to = QTimeEdit(), QTimeEdit()
        for w in (self.time_from, self.time_to):
            w.setDisplayFormat("HH:mm")
            w.editingFinished.connect(self.on_schedule)
        hours.addWidget(self.time_from, 1)
        hours.addWidget(label("–", "rowValue"))
        hours.addWidget(self.time_to, 1)
        sl.addLayout(hours)
        self.schedule_box = sched

        v.addWidget(make_group([
            setting_row(t("Üzerine gelince aç"),
                        t("Kart yalnızca başlık olarak durur; fare üzerine gelince açılır, ayrılınca kapanır."),
                        control=rollup, icon="\uE70D"),
            setting_row(t("Zamanlama"), t("Kart yalnızca seçtiğiniz gün ve saatlerde görünür."),
                        control=self.schedule_on, below=sched, icon="\uE823"),
        ]))

        # Sekmeler: seçilen kartlar bu kartla aynı yerde durur
        self.tab_box = QWidget()
        self.tab_grid = QGridLayout(self.tab_box)
        self.tab_grid.setContentsMargins(0, 0, 0, 0)
        self.tab_grid.setSpacing(6)
        self.tab_group = make_group([
            setting_row(t("Sekmeler"),
                        t("Seçtiğiniz kartlar bu kartla aynı yerde durur; başlığın altındaki sekmelerle "
                          "aralarında geçersiniz."),
                        below=self.tab_box, icon="\uE8A9"),
        ])
        v.addWidget(self.tab_group)
        return page

    # ---------------------------------------------------------------- Kilit
    def _lock_tab(self):
        page, v = self._tab()
        rows = []
        for key, title, desc, glyph in (
                ("lock_pos", t("Konumu kilitle"), t("Kart başlığından sürüklenerek taşınamaz."), ""),
                ("lock_size", t("Boyutu kilitle"), t("Kart köşesinden boyutlandırılamaz."), ""),
                ("lock_content", t("İçeriği kilitle"),
                 t("Karta öğe eklenemez, çıkarılamaz, yeniden dizilemez; öğeler yine açılabilir."), "")):
            toggle = Toggle(False)
            toggle.toggled.connect(lambda on, k=key: self.on_lock(k, on))
            self.locks[key] = toggle
            rows.append(setting_row(title, desc, control=toggle, icon=glyph))
        v.addWidget(make_group(rows))

        # Kaldırma: satır içi onay
        self.remove_btn = named(QPushButton(t("Kartı kaldır")), "danger")
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(lambda: (self.confirm.show(), self.remove_btn.hide()))
        self.confirm = QWidget()
        cr = QHBoxLayout(self.confirm)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.setSpacing(6)
        b = QPushButton(t("Vazgeç"))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.reset_confirm)
        cr.addWidget(b)
        b = named(QPushButton(t("Kaldır")), "danger")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: self.app.remove_fence(self.fence))
        cr.addWidget(b)
        self.confirm.hide()
        control = QWidget()
        cl = QHBoxLayout(control)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.remove_btn)
        cl.addWidget(self.confirm)
        self.confirm_text = label("", "rowDesc", wrap=True)
        self.remove_row = setting_row(t("Kartı kaldır"), None, control=control, below=self.confirm_text, icon="")
        self.remove_group = make_group([self.remove_row])
        v.addWidget(self.remove_group)
        return page

    def reset_confirm(self):
        self.confirm.hide()
        self.remove_btn.show()

    # ---------------------------------------------------------------- bağlama ve yükleme
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
        emoji = d.get("emoji", "")
        self.emojis.button(self._emoji_values.index(emoji) if emoji in self._emoji_values else 0).setChecked(True)
        self.colors.set_custom(appearance(self.app.config)["custom_colors"])
        self.colors.set_value(d.get("theme"))
        self.theme_value.setText(self.colors.value_name())
        for key, toggle in self.locks.items():
            toggle.setChecked(bool(d.get(key)))
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
        if force or not self.name_rules.hasFocus():
            self.name_rules.setText(", ".join(d.get("name_rules", [])))
        self._load_tabs()
        sch = d.get("schedule") or {}
        self.schedule_on.setChecked(bool(sch.get("on")))
        for i, b in enumerate(self.day_buttons):
            b.setChecked(i in sch.get("days", [0, 1, 2, 3, 4]))
        if force or not (self.time_from.hasFocus() or self.time_to.hasFocus()):
            self.time_from.setTime(QTime.fromString(sch.get("from", "09:00"), "HH:mm"))
            self.time_to.setTime(QTime.fromString(sch.get("to", "18:00"), "HH:mm"))
        self.schedule_box.setVisible(bool(sch.get("on")))
        for key, b in self.cat_buttons.items():
            b.setChecked(key in d.get("categories", []))
        mode = d.get("sort", "name")
        self.sorts.button(self._sort_keys.index(mode) if mode in self._sort_keys else 0).setChecked(True)
        kind = d.get("kind", "desktop")
        self.rules_box.setVisible(kind == "desktop")
        self.folder_box.setVisible(kind == "folder")
        self.rest_info.setVisible(kind == "rest")
        self.note_info.setVisible(kind == "note")
        self.recent_info.setVisible(kind == "recent")
        (self.recent_counts.button(int(d.get("recent_count", 20))) or self.recent_counts.button(20)).setChecked(True)
        self.file_group.setVisible(kind != "note")
        self.note_group.setVisible(kind == "note")
        size = d.get("note_size", 0)
        (self.note_sizes.button(size) or self.note_sizes.button(0)).setChecked(True)
        paper = d.get("paper") or ""
        self.papers.button(self._paper_values.index(paper) if paper in self._paper_values else 0).setChecked(True)
        self.note_wrap.setChecked(bool(d.get("note_wrap", True)))
        remind = d.get("remind")
        if force or not self.remind_at.hasFocus():
            self.remind_at.setDateTime(QDateTime.fromSecsSinceEpoch(int(remind)) if remind
                                       else QDateTime.currentDateTime().addSecs(3600))
        self.remind_value.setText(t("Kurulu") if remind else t("Yok"))
        self.remind_clear.setVisible(bool(remind))
        self.remove_group.setVisible(kind != "rest")
        self.confirm_text.setText(
            t("Klasör ve içindekiler olduğu gibi kalır.") if kind == "folder" else
            t("Kartla birlikte içindeki not da silinir.") if kind == "note" else
            t("Dosyalara dokunulmaz.") if kind == "recent" else
            t("İçindeki dosyalar masaüstünde olduğu gibi kalır."))
        self.folder.setText(str(f.folder) if f.folder else "")
        self._loading = False

    # ---------------------------------------------------------------- değişiklikler
    def _changed(self):
        if not self._loading and self.fence:
            self.app.fence_changed(self.fence, source=self)

    def on_name(self, text):
        if self.fence and text.strip():
            self.fence.data["name"] = text.strip()
            self._changed()

    def on_schedule(self, *_):
        if self.fence and not self._loading:
            self.fence.data["schedule"] = {
                "on": self.schedule_on.isChecked(),
                "days": [i for i, b in enumerate(self.day_buttons) if b.isChecked()],
                "from": self.time_from.time().toString("HH:mm"),
                "to": self.time_to.time().toString("HH:mm"),
            }
            self.schedule_box.setVisible(self.schedule_on.isChecked())
            self._changed()

    def on_recent_count(self, count):
        if self.fence:
            self.fence.data["recent_count"] = count
            self.fence._force_refresh = True
            self.fence.refresh()
            self._changed()

    # ---- Not kartı
    def on_note_size(self, delta):
        if self.fence:
            self.fence.data["note_size"] = delta
            self._changed()

    def on_paper(self, index):
        if self.fence:
            self.fence.data["paper"] = self._paper_values[index] or None
            self._changed()

    def on_note_wrap(self, on):
        if self.fence and not self._loading:
            self.fence.data["note_wrap"] = on
            self._changed()

    def on_remind_set(self):
        if self.fence:
            self.fence.set_reminder(self.remind_at.dateTime().toSecsSinceEpoch())
            self.load(force=True)

    def on_remind_clear(self):
        if self.fence:
            self.fence.set_reminder(None)
            self.load(force=True)

    def on_note_copy(self):
        if self.fence:
            QApplication.clipboard().setText(self.fence.note.toPlainText())
            self.app.notify(t("Not panoya kopyalandı."))

    def on_note_export(self, ext):
        if not self.fence:
            return
        fence = self.fence
        text = fence.note.markdown() if ext == "md" else fence.note.toPlainText()
        start = os.path.join(os.path.expanduser("~"), "Documents", f"{fence.data['name']}.{ext}")
        path, _ = QFileDialog.getSaveFileName(None, t("Notu kaydet"), start, f"*.{ext}")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.app.notify(t("Not kaydedildi: {0}").format(path))
            except OSError:
                self.app.notify(t("Not kaydedilemedi."), warn=True)

    def on_emoji(self, index):
        if self.fence:
            self.fence.data["emoji"] = self._emoji_values[index]
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

    def _load_tabs(self):
        """Sekme olarak birleştirilebilecek kartların düğmelerini güncel kart listesine göre kurar."""
        while self.tab_grid.count():
            w = self.tab_grid.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        f = self.fence
        others = [o for o in self.app.fences if o is not f and o.kind != "rest"] if f and f.kind != "rest" else []
        self.tab_group.setVisible(bool(others))
        cols = 2 if self.in_card else 3
        for i, other in enumerate(others):
            b = named(QPushButton(), "pill")
            b.setCheckable(True)
            b.setChecked(bool(f.data.get("group")) and other.data.get("group") == f.data.get("group"))
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(other.data["name"])
            b.setText(b.fontMetrics().elidedText(other.data["name"], Qt.ElideRight, 120))
            # Düğmeler bu işlemle yeniden kurulur: tıklama bittikten sonra uygula
            b.clicked.connect(lambda on, o=other: QTimer.singleShot(0, lambda: self.app.set_grouped(self.fence, o, on)))
            self.tab_grid.addWidget(b, i // cols, i % cols)

    def on_name_rules(self):
        if self.fence:
            text = self.name_rules.text()
            self.fence.data["name_rules"] = [w.strip().lower() for w in text.replace(";", ",").split(",") if w.strip()]
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
        path = QFileDialog.getExistingDirectory(self.window(), t("Kartta gösterilecek klasörü seçin"),
                                                str(self.fence.folder or ""))
        if path:
            self.fence.set_folder(path)
            self._changed()
