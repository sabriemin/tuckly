"""Uygulama: kartların yönetimi, masaüstünü düzenleme, seçenekler ve başlatma."""

import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QFileInfo, QFileSystemWatcher, QPoint, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QFileIconProvider, QMenu, QSystemTrayIcon

from . import __version__
from .i18n import set_language, t
from .config import (
    REPO_URL,
    resource,
    APP_ID,
    APP_NAME,
    CATEGORIES,
    CATEGORY_EXTS,
    CONFIG_FILE,
    DATA_DIR,
    DEFAULT_FENCES,
    FENCE_ROOT,
    LEGACY_DATA_DIR,
    LEGACY_ID,
    LOG_FILE,
    PARTIAL_EXT,
    SERVER_NAME,
    TEMPLATES,
    TOGGLE_ON,
    UNDO_FILE,
    _override,
)
from .utils import norm, snap, unique_dest
from .winapi import (
    allow_foreground,
    desktop_window,
    on_desktop,
    register_context_menu,
    desktop_dir,
    desktop_dirs,
    desktop_entries,
    register_app_identity,
    explorer_view,
    file_attrs,
    set_desktop_icons_visible,
    set_file_hidden,
)
from .theme import appearance, base_style, make_app_icon, make_look
from .winapi import fullscreen_busy, wallpaper_key
from .widgets import StyleTile, Toggle
from .card import FenceWindow
from .notifications import AVAILABLE as BADGES_AVAILABLE, NotificationWatcher
from .panel import ControlPanel
from .shortcuts import DesktopClickWatcher, Hotkeys
from .launcher import Launcher
from .infocards import KIND_DEFAULTS
from .tour import Tour
from .updater import UpdateChecker, is_newer


class FencesApp:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        self.quitting = False
        self.badges = []  # bildirim sayıları: [(uygulama adı, kimliği, sayı)]
        self.tour = Tour(self)
        # Dosya simgeleri önbelleği: Windows'tan simge istemek yavaş; her yenilemede yeniden istenmesin
        self._icon_provider = QFileIconProvider()
        self._icons = {}
        self.config = self.load()
        set_language(self.config.get("language"))  # None: Windows'un dili
        self.locked = self.config.get("locked", False)
        self.fences: list[FenceWindow] = []
        self.cards_hidden = False  # tüm kartlar geçici olarak gizli (çift tıklama / kısayol)
        self.fullscreen_hidden = False  # tam ekran uygulama çalıştığı için gizli
        self.picked = []  # Ctrl+tıkla seçilen kartlar: birlikte taşınır ve hizalanır

        if not self.config.get("fences"):
            self.create_defaults()
        self.migrate()
        # "Diğer" kartı en sona: diğer kartların atamalarına bakar
        self.config["fences"].sort(key=lambda d: d.get("kind") == "rest")
        self.rest = None
        self.build_cards()

        # Kartlar masaüstü penceresine bağlıdır. Gezgin çökerse ya da yeniden başlarsa o pencere ve
        # ona bağlı kartlar yok olur; yeni masaüstü penceresi gelince kartlar yeniden kurulur.
        self._shell = desktop_window()
        self._shell_timer = QTimer(interval=2500, timeout=self.check_shell)
        self._shell_timer.start()

        set_desktop_icons_visible(not self.config.get("hide_icons"))
        if self.hide_assigned:
            self.sync_hidden(True)

        self.desk_watcher = QFileSystemWatcher([str(d) for d in desktop_dirs()])
        self._desk_timer = QTimer(singleShot=True, interval=300, timeout=self.on_desktop_changed)
        self._auto_timer = QTimer(singleShot=True, interval=3000, timeout=self.auto_sort_tick)
        self.desk_watcher.directoryChanged.connect(lambda _: self._desk_timer.start())

        # Bildirim sayıları (isteğe bağlı)
        self.watcher = NotificationWatcher()
        self.watcher.counts.connect(self.on_badges)
        self.watcher.denied.connect(self.on_badges_denied)
        if self.config.get("badges") and BADGES_AVAILABLE:
            self.watcher.start()

        # Güncelleme denetimi: yalnızca depo adresi tanımlıysa ve kullanıcı açık bıraktıysa, günde bir kez
        self.update_state = "idle"   # idle | checking | current | available | error | downloading
        self.update_info = None
        self._update_silent = True
        self.updater = UpdateChecker()
        self.updater.finished.connect(self.on_update_result)
        self.updater.downloaded.connect(self.on_update_downloaded)
        if (REPO_URL and not _override and self.config.get("update_check", True)
                and time.time() - self.config.get("update_checked", 0) > 86400):
            QTimer.singleShot(8000, lambda: self.check_updates(silent=True))

        self._incoming = []  # sağ tık menüsünden gelen, karta eklenecek yollar
        self._incoming_timer = QTimer(singleShot=True, interval=350, timeout=self.show_add_menu)
        if self.config.get("context_menu", True) and not _override:  # exe yolu değişmiş olabilir: her açılışta yaz
            register_context_menu(True, self.launch_command(), str(resource("tuckly.ico")))

        self._look_timer = QTimer(singleShot=True, interval=25, timeout=self.apply_look)
        # Vurgu rengi duvar kâğıdından alınıyorsa, duvar kâğıdı değişince renk de yenilenir
        self._wallpaper = wallpaper_key()
        self._wallpaper_timer = QTimer(interval=20000, timeout=self.check_wallpaper)
        self._wallpaper_timer.start()
        # Not hatırlatıcıları; Tuckly kapalıyken zamanı geçenler açılışta bildirilir
        self._remind_timer = QTimer(interval=15000, timeout=self.check_reminders)
        self._remind_timer.start()
        QTimer.singleShot(4000, self.check_reminders)

        # Monitör düzeni (takılı ekranlar ve yerleri) değişince kartlar o düzendeki yerlerine döner
        self._screen_sig = self.screen_signature()
        self._screen_timer = QTimer(singleShot=True, interval=1500, timeout=self.on_screens_changed)
        for s in QGuiApplication.screens():
            s.geometryChanged.connect(lambda *_: self._screen_timer.start())
        qapp.screenAdded.connect(self._on_screen_added)
        qapp.screenRemoved.connect(lambda *_: self._screen_timer.start())
        qapp.primaryScreenChanged.connect(lambda *_: self._screen_timer.start())
        self._sync_widget_colors()
        self.panel = ControlPanel(self)

        self.tray = QSystemTrayIcon(make_app_icon())
        self.build_tray_menu()
        self.tray.activated.connect(
            lambda r: self.show_panel() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        qapp.aboutToQuit.connect(self.on_quit)

        # Masaüstünde boş yere çift tıklama ve genel kısayol tuşları (Ctrl+Alt+H / N / T)
        self.click_watcher = DesktopClickWatcher()
        self.click_watcher.double_clicked.connect(self.toggle_cards)
        self.launcher = Launcher(self)
        self.hotkeys = Hotkeys(qapp, {"H": self.toggle_cards, "N": self.new_card_at_cursor, "T": self.show_panel,
                                      "F": self.launcher.toggle})
        # Tam ekran uygulama ve kart zamanlamaları için görünürlük denetimi
        self._fullscreen_timer = QTimer(interval=2000, timeout=self.check_fullscreen)
        self._schedule_timer = QTimer(interval=30000, timeout=self.refresh_visibility)
        self._schedule_timer.start()
        if self.config.get("fullscreen_hide") and not _override:
            self._fullscreen_timer.start()
        if not _override:  # testler gerçek fareyi ve klavyeyi dinlemesin
            self.click_watcher.set_enabled(self.config.get("dblclick_hide", True))
            self.hotkeys.set_enabled(self.config.get("hotkeys", True))

    def build_tray_menu(self):
        self.tray.setToolTip(APP_NAME + t(" — tıklayın: kontrol paneli"))
        m = QMenu()
        m.setStyleSheet(base_style(make_look(appearance(self.config))))
        m.addAction(t("Kontrol paneli"), self.show_panel)
        m.addAction(t("Görünüm"), lambda: self.show_panel(page=1))
        m.addAction(t("Masaüstünü düzenle"), lambda: self.show_panel(page=2))
        m.addAction(t("Kartları gizle / göster"), self.toggle_cards)
        m.addAction(t("Hızlı başlat"), lambda: self.launcher.toggle())
        m.addSeparator()
        m.addAction(t("Çıkış"), self.quit)
        self.tray_menu = m
        self.tray.setContextMenu(m)

    # ---- Dil, ayar dosyası ve sıfırlama
    def rebuild_ui(self, page=0):
        """Dil ya da ayarların tamamı değiştiğinde kartları, paneli ve tepsi menüsünü yeniden kurar."""
        self.tour.finish()
        old = self.panel
        visible, geo = old.isVisible(), old.geometry()
        self.close_popups()
        self.rebuild_cards()
        self._sync_widget_colors()
        self.panel = ControlPanel(self)
        self.panel.setGeometry(geo)
        old.hide()
        old.deleteLater()
        self.build_tray_menu()
        if self.config.get("context_menu", True) and not _override:  # menü adları dile göre yazılır
            register_context_menu(True, self.launch_command(), str(resource("tuckly.ico")))
        if visible:
            self.show_panel(page=page)

    # ---- Güncelleme
    def update_status_text(self) -> str:
        if not REPO_URL:
            return t("Bu sürümde güncelleme adresi tanımlı değil.")
        return {
            "idle": t("Henüz denetlenmedi."),
            "checking": t("Denetleniyor…"),
            "current": t("Tuckly güncel."),
            "available": t("Yeni sürüm hazır: {0}").format((self.update_info or {}).get("version", "")),
            "error": t("Güncelleme denetlenemedi. İnternet bağlantınızı kontrol edin."),
            "downloading": t("İndiriliyor…"),
        }[self.update_state]

    def _update_changed(self):
        if hasattr(self, "panel"):
            self.panel.refresh_update()

    def check_updates(self, silent=False):
        if not REPO_URL or self.update_state in ("checking", "downloading"):
            return
        self._update_silent = silent
        self.update_state = "checking"
        self._update_changed()
        self.updater.check()

    def on_update_result(self, info):
        self.config["update_checked"] = time.time()
        self.save()
        if info.get("error"):
            self.update_state = "idle" if self._update_silent else "error"
        elif is_newer(info["version"]):
            self.update_state, self.update_info = "available", info
            self.notify(t("Yeni sürüm hazır: {0}").format(info["version"]))
        else:
            self.update_state = "current"
        self._update_changed()

    def install_update(self):
        """Yeni sürümün kurulum dosyasını indirip başlatır; kurulum dosyası yoksa sürüm sayfasını açar."""
        info = self.update_info or {}
        if info.get("asset"):
            self.update_state = "downloading"
            self._update_changed()
            self.updater.download(info["asset"])
        elif info.get("page"):
            QDesktopServices.openUrl(QUrl(info["page"]))

    def on_update_downloaded(self, path):
        if not path:
            self.update_state = "error"
            self._update_changed()
            return
        os.startfile(path)  # kurulum programı Tuckly'yi kapatıp yenisini kurar
        self.quit()

    def set_update_check(self, on):
        self.config["update_check"] = on
        self.save()

    # ---- Kaldırma
    def uninstall(self):
        """Tuckly'nin Windows'taki izlerini temizler, varsa kaldırma programını açar ve çıkar."""
        self.close_popups()
        if self.hide_assigned:
            self.sync_hidden(False)
        set_desktop_icons_visible(True)
        if not _override:
            register_context_menu(False)
            self.set_autostart(False)
        self.save()
        uninstaller = Path(sys.executable).parent / "unins000.exe"
        if getattr(sys, "frozen", False) and uninstaller.exists():
            os.startfile(str(uninstaller))
        else:
            self.notify(t("Tuckly'nin Windows'taki kayıtları kaldırıldı. Uygulama klasörünü silebilirsiniz."))
        self.quit()

    def start_tour(self):
        """Rehber turunu başlatır (Rehber ve Hakkında sayfalarından, ilk kurulumda da kendiliğinden)."""
        self.tour.start()

    def set_language(self, code):
        self.config["language"] = code
        set_language(code)
        self.save()
        self.rebuild_ui(page=3)

    def export_settings(self, path) -> bool:
        """Kartları ve tüm ayarları bir JSON dosyasına yazar."""
        data = dict(self.config)
        data["tuckly_export"] = __version__
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    def import_settings(self, path) -> bool:
        """Dışa aktarılmış bir ayar dosyasını yükler; mevcut ayarların yerini alır."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.notify(t("Ayar dosyası okunamadı."), warn=True)
            return False
        fences = data.get("fences") if isinstance(data, dict) else None
        if not isinstance(fences, list) or not all(isinstance(d, dict) and d.get("name") for d in fences):
            self.notify(t("Bu dosya bir Tuckly ayar dosyası değil."), warn=True)
            return False
        if self.hide_assigned:
            self.sync_hidden(False)  # eski kartlardaki simgeler masaüstüne dönsün
        data.pop("tuckly_export", None)
        data["system_marked"] = []
        self.config = data
        self._apply_new_config()
        self.notify(t("Ayarlar içe aktarıldı."))
        return True

    def reset_settings(self):
        """Tüm kartları ve ayarları ilk kurulumdaki haline döndürür. Dosyalara dokunmaz."""
        if self.hide_assigned:
            self.sync_hidden(False)
        self.config = {"fences": [], "language": self.config.get("language")}
        self.create_defaults()
        self._apply_new_config()
        self.notify(t("Tüm ayarlar varsayılana döndürüldü. Dosyalara dokunulmadı."))

    def _apply_new_config(self):
        self.locked = self.config.get("locked", False)
        set_language(self.config.get("language"))
        self.migrate()
        self.config["fences"].sort(key=lambda d: d.get("kind") == "rest")
        self.save()
        self.rebuild_ui(page=3)
        set_desktop_icons_visible(not self.config.get("hide_icons"))
        if self.hide_assigned:
            self.sync_hidden(True)
        if self.config.get("badges") and BADGES_AVAILABLE:
            self.watcher.start()
        else:
            self.watcher.stop()

    # ---- Kart pencereleri
    def build_cards(self):
        """Ayarlardaki kartlar için pencereleri oluşturur ve gösterir."""
        self.fences = [FenceWindow(self, d) for d in self.config["fences"]]
        self.rest = next((f for f in self.fences if f.kind == "rest"), None)
        if self.rest:
            self.rest.refresh()
        self.normalize_groups()
        for f in self.fences:
            if self.should_show(f):
                f.show()
        self.refresh_tabs()

    def check_shell(self):
        """Masaüstü penceresi değiştiyse (Gezgin yeniden başladı) kartları yeniden kurar."""
        now = desktop_window()
        if not now or now == self._shell:
            return  # Gezgin kapalıysa geri gelmesini bekle
        self._shell = now
        self.rebuild_cards()

    def rebuild_cards(self):
        self.picked = []
        for f in self.fences:
            if f.popup:
                f.popup.hide()
                f.popup.deleteLater()
            f.hide()
            f.deleteLater()
        self.build_cards()
        set_desktop_icons_visible(not self.config.get("hide_icons"))
        if hasattr(self, "panel"):
            self.panel.reload_cards()
        for f in self.fences:
            f.apply_badges()

    # ---- Ayarlar
    def load(self) -> dict:
        # Tuckly ayarı yoksa eski addaki (Masaüstü Kutuları) ayarları devral; eski dosyaya dokunma
        for path in (CONFIG_FILE, LEGACY_DATA_DIR / "ayarlar.json"):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return {"fences": []}

    def save(self):
        if self.config.get("screen_memory", True) and hasattr(self, "_screen_sig"):
            # Kart yerleri geçerli monitör düzeninin adıyla da saklanır
            layouts = self.config.setdefault("screen_layouts", {})
            layouts.pop(self._screen_sig, None)  # en son kullanılan sona gelsin
            layouts[self._screen_sig] = {d["id"]: [d.get("x", 0), d.get("y", 0), d.get("w", 340), d.get("h", 230)]
                                         for d in self.config.get("fences", []) if d.get("id")}
            while len(layouts) > 8:
                layouts.pop(next(iter(layouts)))
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CONFIG_FILE)

    def create_defaults(self):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        w, h, gap = 340, 230, 20
        per_col = max(1, (geo.height() - gap) // (h + gap))
        fences = []
        for i, (name, cats) in enumerate(DEFAULT_FENCES):
            col, row = divmod(i, per_col)
            d = self._fence_data(
                t(name), [], snap(geo.right() - (col + 1) * (w + gap)), snap(geo.top() + gap + row * (h + gap)))
            d["categories"] = list(cats)
            fences.append(d)
        self.config["fences"] = fences
        self.save()

    def migrate(self):
        """Eski sürüm: dosyalar kart klasörlerine taşınıyordu. Onları masaüstüne geri getir ve
        aynı kartta göster. Ayrıca her kurulumda bir "Diğer" kartı olsun."""
        desk = desktop_dir()
        changed = False
        # Görünüm artık genel bir ayar: eski "cam efekti" seçeneği ve kart başına opaklık devralınır
        ap = appearance(self.config)
        if "glass" in self.config:
            if not self.config.pop("glass"):
                ap["style"] = "flat"
            changed = True
        if self.config.get("schema", 1) < 2:  # bir kez: eski kart başına varsayılanları genel ayara bağla
            for d in self.config["fences"]:
                d["opacity"] = None
                if d.get("theme") == "graphite":
                    d["theme"] = None
            self.config["schema"] = 2
            changed = True
        if self.config.get("schema", 1) < 3:  # bir kez: elle yazılmış uzantı kurallarını kategorilere çevir
            for d in self.config["fences"]:
                rules, cats = set(d.get("rules", [])), list(d.get("categories", []))
                for key, _, exts in CATEGORIES:
                    if exts and key not in cats and len(rules & set(exts)) * 2 >= len(exts):
                        cats.append(key)
                covered = {e for k in cats for e in CATEGORY_EXTS.get(k, ())}
                d["categories"] = cats
                d["rules"] = sorted(rules - covered)
                d.setdefault("sort", "name")
            self.config["schema"] = 3
            changed = True
        for d in self.config["fences"]:
            if "kind" in d:
                continue
            changed = True
            folder = Path(d.get("folder", ""))
            under_root = bool(d.get("folder")) and norm(folder.parent) == norm(FENCE_ROOT)
            if under_root or not d.get("folder"):
                d["kind"], items = "desktop", []
                if under_root and folder.exists():
                    for p in list(folder.iterdir()):
                        try:
                            dst = unique_dest(desk, p.name)
                            shutil.move(str(p), str(dst))
                            items.append(str(dst))
                        except Exception:  # noqa: BLE001
                            pass
                    try:
                        folder.rmdir()
                    except OSError:
                        pass
                d["items"] = items
                d.pop("folder", None)
            else:
                d["kind"] = "folder"
            d.pop("color", None)
        try:  # boş kalan eski kök klasörü temizle
            if FENCE_ROOT.exists() and not any(FENCE_ROOT.iterdir()):
                FENCE_ROOT.rmdir()
        except OSError:
            pass
        if not any(d.get("kind") == "rest" for d in self.config["fences"]):
            geo = QGuiApplication.primaryScreen().availableGeometry()
            rest = self._fence_data(t("Diğer"), [], snap(geo.left() + 20), snap(geo.top() + 20))
            rest["kind"] = "rest"
            self.config["fences"].append(rest)
            changed = True
        for d in self.config["fences"]:
            if "id" not in d:
                d["id"] = os.urandom(6).hex()
                changed = True
        if changed:
            self.save()

    @staticmethod
    def _fence_data(name, rules, x, y, kind="desktop", folder=None):
        d = {"id": os.urandom(6).hex(), "name": name, "kind": kind, "items": [], "rules": rules,
             "x": x, "y": y, "w": 340, "h": 230,
             "collapsed": False, "icon_size": 36, "theme": None, "opacity": None,
             "categories": [], "sort": "name", "order": []}
        if folder:
            d["folder"] = folder
        return d

    # ---- Atamalar (dosyalar masaüstünde kalır, kart sadece gösterir)
    def assigned_keys(self):
        return {norm(p) for f in self.fences if f.kind == "desktop" for p in f.data["items"]}

    def assign(self, path, fence):
        key = norm(path)
        for f in self.fences:
            if f.kind == "desktop":
                f.data["items"] = [p for p in f.data["items"] if norm(p) != key]
        placed = fence is not None and fence.kind == "desktop"
        if placed:
            fence.data["items"].append(str(path))
        if self.hide_assigned:  # karta konan simge masaüstünde gizlenir, karttan çıkınca geri gelir
            self._hide(path, placed)
        self.save()

    def _hide(self, path, hide: bool):
        """Bir dosyanın masaüstü simgesini gizler ya da geri getirir.

        Gezgin gizli dosyaları gösterecek şekilde ayarlıysa "gizli" işareti yetmez (simge soluk
        görünür); o durumda dosya ayrıca "sistem" olarak işaretlenir. Bu işareti Tuckly'nin koyduğu
        dosyalar ayarlarda tutulur ki geri alırken yalnızca kendi koyduğumuz işaret kaldırılsın."""
        marked = self.config.setdefault("system_marked", [])
        key = str(path)
        if hide:
            shows_hidden, shows_system = explorer_view()
            attrs = file_attrs(path)
            system = shows_hidden and not shows_system and attrs is not None and not attrs & 0x4
            if set_file_hidden(path, True, system) and system and key not in marked:
                marked.append(key)
        else:
            set_file_hidden(path, False, key in marked)
            if key in marked:
                marked.remove(key)

    def path_renamed(self, old, new):
        marked = self.config.setdefault("system_marked", [])
        if str(old) in marked:
            marked[marked.index(str(old))] = str(new)

    @property
    def hide_assigned(self) -> bool:
        return self.config.get("hide_assigned", True)

    def sync_hidden(self, hide: bool):
        """Kartlara yerleşmiş tüm dosyaların masaüstündeki simgesini gizler ya da geri getirir.
        Dosyalar yerinden oynamaz; yalnızca "gizli" özniteliği değişir."""
        for f in self.fences:
            if f.kind == "desktop":
                for p in f.data["items"]:
                    self._hide(p, hide)

    def set_hide_assigned(self, on):
        self.config["hide_assigned"] = on
        self.sync_hidden(on)
        self.save()

    def refresh_all(self):
        for f in self.fences:
            if f.kind != "rest":
                f.refresh()
        if self.rest:
            self.rest.refresh()

    def on_desktop_changed(self):
        self.refresh_all()
        if self.config.get("auto_sort"):
            self._auto_timer.start()

    # ---- Ortak olaylar
    def notify(self, text, warn=False):
        if hasattr(self, "panel"):
            self.panel.set_status(text)
        if hasattr(self, "tray") and not _override:  # testler gerçek ekrana bildirim göndermesin
            if warn:
                self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.Warning, 3500)
            else:  # bilgi bildirimlerinde Windows'un mavi "i" simgesi yerine Tuckly logosu
                self.tray.showMessage(APP_NAME, text, make_app_icon(), 3500)

    def fence_changed(self, fence, source=None):
        fence.apply_settings()
        if fence.data.get("group"):  # sekmelerde görünen ad değişmiş olabilir
            self.refresh_tabs()
        if fence in self.fences:  # zamanlama değişmiş olabilir
            fence.setVisible(self.should_show(fence))
        panel = getattr(self, "panel", None)
        for ed in (fence.settings, panel.editor if panel else None):
            if ed and ed is not source and ed.fence is fence:
                ed.load()
        if panel:
            panel.update_names()
        self.save()

    def show_panel(self, fence=None, page=0):
        if isinstance(fence, FenceWindow):
            self.panel.reload_cards(select=fence)
        self.panel.set_page(page)
        self.panel.show()
        self.panel.setWindowState(self.panel.windowState() & ~Qt.WindowMinimized)
        self.panel.raise_()
        self.panel.activateWindow()

    # ---- Kart yönetimi
    def new_fence(self, name=None, folder=None, pos=None, note=False, kind=None):
        if self.cards_hidden:  # yeni kart görünsün
            self.set_cards_hidden(False)
        if name is None:
            base = (t("Not") if note else t("Son kullanılanlar") if kind == "recent"
                    else t(KIND_DEFAULTS[kind][0]) if kind in KIND_DEFAULTS else t("Yeni Kart"))
            i = 2
            names = {f.data["name"] for f in self.fences}
            name = base
            while name in names:
                name = f"{base} {i}"
                i += 1
        geo = QGuiApplication.primaryScreen().availableGeometry()
        off = 30 * (len(self.fences) % 6)
        if pos is not None:  # örn. sağ tık menüsünden: imlecin olduğu ekranda ve yerde
            geo = (QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()).availableGeometry()
            x = max(geo.left(), min(pos.x() - 30, geo.right() - 350))
            y = max(geo.top(), min(pos.y() - 20, geo.bottom() - 240))
        else:
            x, y = geo.center().x() - 170 + off, geo.center().y() - 115 + off
        kind = kind or ("note" if note else "folder" if folder else "desktop")
        data = self._fence_data(name, [], snap(x), snap(y), kind=kind, folder=folder)
        if kind in KIND_DEFAULTS:
            data["w"], data["h"] = KIND_DEFAULTS[kind][1:]
        # "Diğer" kartı listenin sonunda kalsın
        idx = self.fences.index(self.rest) if self.rest in self.fences else len(self.fences)
        self.config["fences"].insert(idx, data)
        f = FenceWindow(self, data)
        self.fences.insert(idx, f)
        f.show()
        self.save()
        return f

    # ---- Çoklu kart seçimi
    def toggle_pick(self, fence):
        if fence in self.picked:
            self.picked.remove(fence)
        elif fence.kind != "rest":
            self.picked.append(fence)
        fence.set_picked(fence in self.picked)

    def clear_picks(self):
        for fence in self.picked:
            fence.set_picked(False)
        self.picked = []

    def arrange_picks(self, mode, ref):
        """Seçili kartları hizalar ya da boyutlandırır. ref: menünün açıldığı kart."""
        cards = [f for f in self.picked if f in self.fences and f.isVisible()]
        movable = [f for f in cards if not self.locked and not f.data.get("lock_pos")]
        if mode == "left":
            x = min(f.x() for f in cards)
            for f in movable:
                f.move(x, f.y())
        elif mode == "top":
            y = min(f.y() for f in cards)
            for f in movable:
                f.move(f.x(), y)
        elif mode == "size":
            for f in cards:
                if f is not ref and not self.locked and not f.data.get("lock_size"):
                    f.data["h"] = ref.data.get("h", f.data.get("h", 230))
                    f.resize(ref.width(), f.height() if f.is_folded() else f.data["h"])
        elif mode == "stack":
            x, y = min(f.x() for f in cards), min(f.y() for f in cards)
            for f in sorted(cards, key=lambda c: c.y()):
                if f in movable:
                    f.move(x, y)
                y = f.y() + f.height() + 10
        for f in cards:
            f.store_geometry()

    def apply_template(self, key):
        """Hazır bir kart setini ekler; var olan kartlara ve dosyalara dokunmaz."""
        template = next((tpl for tpl in TEMPLATES if tpl[0] == key), None)
        if not template:
            return []
        geo = QGuiApplication.primaryScreen().availableGeometry()
        made = []
        for i, (name, kind, categories, emoji, words) in enumerate(template[2]):
            col, row = divmod(i, max(1, (geo.height() - 60) // 250))
            pos = QPoint(geo.left() + 90 + col * 360, geo.top() + 80 + row * 250)
            fence = self.new_fence(name=t(name), pos=pos, note=kind == "note")
            fence.data["categories"] = list(categories)
            fence.data["name_rules"] = list(words)
            if emoji:
                fence.data["emoji"] = emoji
            fence.apply_settings()
            made.append(fence)
        self.save()
        self.panel.reload_cards(select=made[0] if made else None)
        self.notify(t('“{0}” şablonu eklendi: {1} kart.').format(t(template[1]), len(made)))
        return made

    def remove_fence(self, fence):
        if fence is None or fence not in self.fences or fence.kind == "rest":
            return
        if fence.kind == "desktop":  # karttaki dosyalar masaüstünde yeniden görünsün
            for p in fence.data["items"]:
                self._hide(p, False)
        if fence.data.get("group"):  # sekme grubundaysa önce gruptan çıkar: yerine başka sekme gelir
            was_active = fence.data.get("tab_active")
            others = [m for m in self.group_of(fence) if m is not fence]
            fence.data.pop("group", None)
            if was_active and others:
                others[0].data["tab_active"] = True
                others[0].move(fence.pos())
                others[0].data["x"], others[0].data["y"] = fence.x(), fence.y()
        if fence in self.picked:
            self.picked.remove(fence)
        self.config["fences"].remove(fence.data)
        self.fences.remove(fence)
        fence.vanish()
        self._apply_groups()
        self.save()
        self.refresh_all()
        self.panel.reload_cards()
        self.notify(t('“{0}” kartı kaldırıldı. Dosyalara dokunulmadı.').format(fence.data['name']))

    # ---- Masaüstünü düzenleme
    def plan_sort(self, min_age=0.0):
        """Henüz hiçbir karta yerleşmemiş masaüstü öğelerini kartların kategorilerine göre eşleştirir.
        Aynı kategori birden çok kartta seçiliyse listede önce gelen kart kazanır."""
        exts, folder_card, words = {}, None, []
        for f in self.fences:
            if f.kind != "desktop" or f.data.get("lock_content"):  # içeriği kilitli karta yerleştirme
                continue
            words += [(w, f) for w in f.data.get("name_rules", [])]  # adında bu sözcük geçen öğeler
            for key in f.data.get("categories", []):
                if key == "folders":
                    folder_card = folder_card or f
                for ext in CATEGORY_EXTS.get(key, ()):
                    exts.setdefault(ext, f)
            for ext in f.data.get("rules", []):  # elle eklenen ek uzantılar
                exts.setdefault(ext, f)
        taken = self.assigned_keys()
        plan, now = [], time.time()
        for p in sorted(desktop_entries(), key=lambda p: p.name.lower()):
            try:
                if norm(p) in taken:
                    continue
                # Ad kuralı tür kuralından önce gelir: "fatura" geçen PDF, Belgeler yerine Faturalar kartına gider
                named_card = next((card for w, card in words if w in p.name.lower()), None)
                if p.is_dir():
                    f = named_card or folder_card
                else:
                    if p.suffix.lower() in PARTIAL_EXT:
                        continue
                    if min_age and now - p.stat().st_mtime < min_age:
                        continue
                    f = named_card or exts.get(p.suffix.lower().lstrip("."))
            except OSError:
                continue
            if f:
                plan.append((p, f))
        return plan

    def execute_sort(self, plan):
        """Dosyaları taşımaz; yalnızca kartlara yerleştirir (geri alınabilir)."""
        done = []
        for path, fence in plan:
            self.assign(path, fence)
            done.append(str(path))
        if done:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            UNDO_FILE.write_text(json.dumps({"time": time.time(), "assigned": done},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
        self.refresh_all()
        return done, []

    def auto_sort_tick(self):
        plan = self.plan_sort(min_age=3)
        if plan:
            done, _ = self.execute_sort(plan)
            if done:
                self.notify(t('{0} yeni dosya kartlara yerleştirildi.').format(len(done)))
        if any(p.suffix.lower() in PARTIAL_EXT for p in desktop_entries()):
            self._auto_timer.start()

    def undo_last(self):
        try:
            data = json.loads(UNDO_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.notify(t("Geri alınacak bir düzenleme yok."))
            return
        paths = data.get("assigned", [])
        for p in paths:
            self.assign(p, None)
        UNDO_FILE.unlink(missing_ok=True)
        self.refresh_all()
        self.notify(t('{0} dosya kartlardan çıkarıldı (masaüstünde duruyorlar).').format(len(paths)))
        self.panel.refresh_plan()

    # ---- Seçenekler
    def set_auto_sort(self, on):
        self.config["auto_sort"] = on
        self.save()
        if on:
            self._auto_timer.start(500)

    def set_hide_icons(self, on):
        self.config["hide_icons"] = on
        self.save()
        set_desktop_icons_visible(not on)
        if self.rest:  # simgeler gizliyken kartsız öğeler "Diğer" kartında görünür
            self.rest.refresh()
            self.rest.setVisible(self.should_show(self.rest))

    # ---- Kartları geçici olarak gizleme, kısayollar ve yapıştırma
    def set_cards_hidden(self, hidden: bool):
        """Tüm kartları gizler ya da geri getirir. Karttaki öğeler masaüstünde gizli kalır: temiz masaüstü."""
        self.cards_hidden = hidden
        self.close_popups()
        for f in self.fences:
            f.setVisible(self.should_show(f))

    def should_show(self, fence) -> bool:
        """Kart şu an ekranda mı olmalı? Sekme grubunda yalnızca seçili sekmenin kartı görünür."""
        if self.cards_hidden or self.fullscreen_hidden:
            return False
        if fence.kind == "rest" and not self.config.get("hide_icons"):
            return False
        if not self.in_schedule(fence):
            return False
        return not fence.data.get("group") or bool(fence.data.get("tab_active"))

    @staticmethod
    def in_schedule(fence, now=None) -> bool:
        """Kartın zamanlaması varsa şu an gösterilmesi gereken gün ve saatte miyiz?"""
        sch = fence.data.get("schedule")
        if not sch or not sch.get("on"):
            return True
        lt = time.localtime(now)
        minute = lt.tm_hour * 60 + lt.tm_min
        days = sch.get("days", list(range(7)))

        def minutes(text, default):
            try:
                h, m = text.split(":")
                return int(h) * 60 + int(m)
            except (ValueError, AttributeError):
                return default

        start, end = minutes(sch.get("from"), 9 * 60), minutes(sch.get("to"), 18 * 60)
        if start <= end:
            return lt.tm_wday in days and start <= minute < end
        # Gece yarısını aşan aralık (örn. 22:00–02:00): ertesi günün sabahı önceki güne sayılır
        return (lt.tm_wday in days and minute >= start) or ((lt.tm_wday - 1) % 7 in days and minute < end)

    def refresh_visibility(self):
        for f in self.fences:
            f.setVisible(self.should_show(f))

    def check_fullscreen(self):
        busy = fullscreen_busy()
        if busy != self.fullscreen_hidden:
            self.fullscreen_hidden = busy
            if busy:
                self.close_popups()
            self.refresh_visibility()

    def set_fullscreen_hide(self, on):
        self.config["fullscreen_hide"] = on
        self.save()
        if on and not _override:
            self._fullscreen_timer.start()
        else:
            self._fullscreen_timer.stop()
            self.fullscreen_hidden = False
            self.refresh_visibility()

    def reveal(self, fence):
        """Kartı görünür hale getirir: gizliyse geri getirir, sekme grubundaysa öne alır, kapalıysa açar."""
        if self.cards_hidden:
            self.set_cards_hidden(False)
        if fence.data.get("group") and not fence.data.get("tab_active"):
            self.activate_tab(fence)
        fence.begin_peek()

    # ---- Sekmeli kartlar: aynı gruptaki kartlar aynı yerde durur, sekmelerle aralarında geçilir
    def group_of(self, fence) -> list:
        gid = fence.data.get("group")
        return [f for f in self.fences if gid and f.data.get("group") == gid]

    def normalize_groups(self):
        """Tek kartı kalan grupları dağıtır; her grupta tam bir seçili sekme bırakır."""
        groups = {}
        for f in self.fences:
            if f.data.get("group") and f.kind != "rest":
                groups.setdefault(f.data["group"], []).append(f)
            else:
                f.data.pop("group", None)
                f.data.pop("tab_active", None)
        for members in groups.values():
            if len(members) < 2:
                members[0].data.pop("group", None)
                members[0].data.pop("tab_active", None)
                continue
            active = next((m for m in members if m.data.get("tab_active")), members[0])
            for m in members:
                m.data["tab_active"] = m is active

    def refresh_tabs(self):
        for f in self.fences:
            f.update_tabs()

    def _apply_groups(self):
        self.normalize_groups()
        for f in self.fences:
            f.setVisible(self.should_show(f))
        self.refresh_tabs()
        self.save()
        self.panel.editor.load()
        for f in self.fences:
            if f.settings:
                f.settings.load()

    def activate_tab(self, target):
        """Gruptaki başka bir kartı öne alır; kart, o an görünen sekmenin yerini ve boyutunu devralır."""
        members = self.group_of(target)
        current = next((m for m in members if m.data.get("tab_active")), None)
        if not members or current is target:
            return
        if current:
            current.store_note()
            for key in ("x", "y", "w", "h"):
                target.data[key] = current.data.get(key, target.data.get(key))
            target.move(current.pos())
            target.resize(current.width(), target.height() if target.is_folded() else current.data.get("h", 230))
        for m in members:
            m.data["tab_active"] = m is target
        self.close_popups()
        self._apply_groups()

    def set_grouped(self, fence, other, on: bool):
        """`other` kartını `fence` ile aynı sekme grubuna alır ya da gruptan çıkarır."""
        if fence.kind == "rest" or other.kind == "rest" or fence is other:
            return
        if on:
            gid = fence.data.get("group") or os.urandom(4).hex()
            if not fence.data.get("group"):
                fence.data["group"], fence.data["tab_active"] = gid, True
            other.data["group"], other.data["tab_active"] = gid, False
        elif other.data.get("group"):
            was_active = other.data.get("tab_active")
            rest = [m for m in self.group_of(other) if m is not other]
            other.data.pop("group", None)
            other.data.pop("tab_active", None)
            if was_active and rest:
                rest[0].data["tab_active"] = True
                for key in ("x", "y", "w", "h"):
                    rest[0].data[key] = other.data.get(key, rest[0].data.get(key))
                rest[0].move(other.pos())
            # Ayrılan kart, grubun yanında kendi yerinde açılır
            other.move(other.x() + 40, other.y() + 40)
            other.data["x"], other.data["y"] = other.x(), other.y()
        self._apply_groups()

    def toggle_cards(self):
        self.set_cards_hidden(not self.cards_hidden)

    def set_dblclick_hide(self, on):
        self.config["dblclick_hide"] = on
        self.save()
        self.click_watcher.set_enabled(on and not _override)

    def set_hotkeys(self, on):
        self.config["hotkeys"] = on
        self.save()
        self.hotkeys.set_enabled(on and not _override)

    def set_magnet(self, on):
        self.config["magnet"] = on
        self.save()

    def icon_for(self, path) -> QIcon:
        """Dosyanın simgesi; dosya değişmediyse önbellekten gelir."""
        try:
            stamp = path.stat().st_mtime
        except OSError:
            stamp = 0
        hit = self._icons.get(str(path))
        if hit and hit[0] == stamp:
            return hit[1]
        icon = self._icon_provider.icon(QFileInfo(str(path)))
        self._icons[str(path)] = (stamp, icon)
        return icon

    @property
    def animations(self) -> bool:
        return bool(appearance(self.config).get("animations", True))

    def close_popups(self, keep=None):
        """Açık kart ayarı pencerelerini kapatır (aynı anda yalnızca biri açık kalır)."""
        for f in self.fences:
            if f is not keep and f.popup and f.popup.isVisible():
                f.popup.dismiss()

    # ---- Bildirim sayıları
    def set_badges(self, on):
        self.config["badges"] = on
        self.save()
        if on:
            self.watcher.start(ask_permission=True)
        else:
            self.watcher.stop()

    def on_badges(self, counts):
        if counts != self.badges:
            self.badges = counts
            for f in self.fences:
                f.apply_badges()

    def on_badges_denied(self):
        self.watcher.stop()
        if self.config.get("badges"):
            self.config["badges"] = False
            self.save()
            self.notify(t("Bildirim sayıları için Windows izni verilmedi. Ayarlar > Gizlilik > Bildirimler "
                        "bölümünden izin verip yeniden açabilirsiniz."), warn=True)

    # ---- Görünüm
    def set_appearance(self, key, value):
        """Bir görünüm ayarını değiştirir; kartlar ve panel kısa bir gecikmeyle yeniden çizilir."""
        appearance(self.config)[key] = value
        self._look_timer.start()

    def reset_appearance(self):
        self.config["appearance"] = {}
        self.apply_look()
        self.panel.reload_appearance()

    def apply_look(self):
        self._sync_widget_colors()
        for f in self.fences:
            f.apply_settings()
        self.panel.apply_look()
        self.tray_menu.setStyleSheet(base_style(make_look(appearance(self.config))))
        self.save()

    def _sync_widget_colors(self):
        ap = appearance(self.config)
        look = make_look(ap)
        Toggle.on_color = QColor(TOGGLE_ON) if ap["accent"] == "mono" else look.accent
        Toggle.fg = look.fg_color
        StyleTile.accent = QColor(TOGGLE_ON) if ap["accent"] == "mono" else look.accent

    # ---- Monitör düzeni
    @staticmethod
    def screen_signature() -> str:
        return "|".join(sorted(f"{g.x()},{g.y()},{g.width()}x{g.height()}"
                               for g in (s.geometry() for s in QGuiApplication.screens())))

    def _on_screen_added(self, screen):
        screen.geometryChanged.connect(lambda *_: self._screen_timer.start())
        self._screen_timer.start()

    def on_screens_changed(self):
        """Monitör takıldı, çıkarıldı ya da yeri değişti: kartları bu düzende en son durdukları yere taşır.
        Bu düzen ilk kez görülüyorsa kartlar yerinde kalır; ekran dışında kalanlar ana ekrana alınır."""
        new = self.screen_signature()
        if new == self._screen_sig:
            return
        self._screen_sig = new
        saved = self.config.get("screen_layouts", {}).get(new) if self.config.get("screen_memory", True) else None
        geo = QGuiApplication.primaryScreen().availableGeometry()
        stray = 0
        for fence in self.fences:
            d = fence.data
            g = (saved or {}).get(d.get("id"))
            if g:
                d["x"], d["y"], d["w"], d["h"] = g
            fence.move(d.get("x", 100), d.get("y", 100))
            fence.resize(d.get("w", 340), fence.height() if fence.is_folded() else d.get("h", 230))
            if QGuiApplication.screenAt(fence.frameGeometry().center()) is None:
                fence.move(geo.left() + 40 + 30 * stray, geo.top() + 40 + 30 * stray)
                stray += 1
            d["x"], d["y"] = fence.x(), fence.y()
        self.save()

    def set_screen_memory(self, on):
        self.config["screen_memory"] = on
        self.save()

    # ---- Düzen yedekleri: kartların yeri, boyutu ve içeriği adla saklanır
    def save_layout(self, name=""):
        layouts = self.config.setdefault("layouts", [])
        name = name.strip()
        if not name:
            i = len(layouts) + 1
            while any(entry["name"] == t("Düzen {0}").format(i) for entry in layouts):
                i += 1
            name = t("Düzen {0}").format(i)
        for fence in self.fences:
            fence.store_note()
            fence.data["x"], fence.data["y"] = fence.x(), fence.y()
        entry = {"name": name, "saved": int(time.time()), "fences": copy.deepcopy(self.config["fences"])}
        same = next((i for i, e in enumerate(layouts) if e["name"] == name), None)
        if same is None:
            layouts.append(entry)
        else:
            layouts[same] = entry  # aynı adla yeniden kaydetmek eskisinin yerini alır
        self.save()
        self.panel.reload_layouts()
        self.notify(t('“{0}” düzeni kaydedildi.').format(name))
        return entry

    def load_layout(self, index):
        layouts = self.config.get("layouts", [])
        if not 0 <= index < len(layouts):
            return
        entry = layouts[index]
        if self.hide_assigned:
            self.sync_hidden(False)  # şimdiki kartlardaki simgeler masaüstüne dönsün
        for fence in self.fences:
            fence.store_note()
        notes = {d.get("id"): d.get("text", "") for d in self.config["fences"] if d.get("kind") == "note"}
        fences = copy.deepcopy(entry["fences"])
        for d in fences:  # notların güncel metni korunur: eski düzen yeni yazılanı silmesin
            if d.get("kind") == "note" and d.get("id") in notes:
                d["text"] = notes[d["id"]]
        self.config["fences"] = fences
        self.close_popups()
        self.rebuild_cards()
        if self.hide_assigned:
            self.sync_hidden(True)
        self.refresh_all()
        self.save()
        self.notify(t('“{0}” düzeni yüklendi. Dosyalara dokunulmadı.').format(entry["name"]))

    def delete_layout(self, index):
        layouts = self.config.get("layouts", [])
        if 0 <= index < len(layouts):
            del layouts[index]
            self.save()
            self.panel.reload_layouts()

    def check_reminders(self):
        now = time.time()
        for fence in list(self.fences):
            when = fence.data.get("remind")
            if fence.kind != "note" or not when or when > now:
                continue
            fence.data["remind"] = None
            first = next((ln.strip() for ln in fence.note.toPlainText().splitlines() if ln.strip()), "")
            # Not görünsün: kartlar gizliyse geri getir, sekme grubundaysa öne al
            if self.cards_hidden:
                self.set_cards_hidden(False)
            if fence.data.get("group") and not fence.data.get("tab_active"):
                self.activate_tab(fence)
            self.fence_changed(fence)
            self.notify(t("Hatırlatıcı — {0}").format(fence.data["name"]) + (": " + first[:80] if first else ""))

    def check_wallpaper(self):
        if appearance(self.config).get("accent") != "wallpaper":
            return
        now = wallpaper_key()
        if now != self._wallpaper:
            self._wallpaper = now
            self.apply_look()

    def set_locked(self, on):
        self.locked = on
        self.config["locked"] = on
        self.save()
        for f in self.fences:
            f.apply_settings()

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    @staticmethod
    def launch_command() -> str:
        """Tuckly'yi başlatan komut: derlenmiş exe ya da (kaynak koddan çalışırken) pythonw + run.py."""
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        return f'"{exe}" "{Path(__file__).resolve().parent.parent / "run.py"}"'

    def autostart_command(self):
        return self.launch_command() + " --arkaplan"

    # ---- Sağ tık menüsü ve başka kopyalardan gelen istekler
    def set_context_menu(self, on):
        self.config["context_menu"] = on
        self.save()
        if not _override:
            register_context_menu(on, self.launch_command(), str(resource("tuckly.ico")))

    def handle_message(self, data: bytes):
        """İkinci kez başlatılan Tuckly'nin (ya da sağ tık menüsünün) ilettiği istek."""
        text = data.decode("utf-8", "replace")
        if text == "quit":
            self.quit()
        elif text == "new":
            self.new_card_at_cursor()
        elif text.startswith("add\n"):
            # Çoklu seçimde Gezgin her öğe için ayrı istek yollar: kısa süre bekleyip hepsini topla
            self._incoming.append(text[4:])
            self._incoming_timer.start()
        else:
            self.show_panel()

    def new_card_at_cursor(self, paths=()):
        f = self.new_fence(pos=QCursor.pos())
        for p in paths:
            self.assign(p, f)
        self.refresh_all()
        self.panel.reload_cards()
        QTimer.singleShot(250, lambda: f.show_settings(True))  # hemen adını verebilsin
        return f

    def show_add_menu(self):
        """Sağ tıkla seçilen masaüstü öğeleri için imlecin yanında "hangi karta?" menüsü açar."""
        paths, self._incoming = [Path(p) for p in dict.fromkeys(self._incoming)], []
        ok = [p for p in paths if p.exists() and on_desktop(p)]
        if not ok:
            self.notify(t("Yalnızca masaüstündeki öğeler karta eklenebilir."))
            return
        m = QMenu()
        m.setStyleSheet(base_style(make_look(appearance(self.config))))
        head = m.addAction(ok[0].name if len(ok) == 1 else t('{0} öğe').format(len(ok)))
        head.setEnabled(False)
        m.addSeparator()
        m.addAction(t("+  Yeni kart"), lambda: self.new_card_at_cursor(ok))
        cards = [f for f in self.fences if f.kind == "desktop" and not f.data.get("lock_content")]
        if cards:
            m.addSeparator()
        for f in cards:
            m.addAction(f.data["name"], lambda f=f: self.add_to_card(ok, f))
        self._add_menu = m  # menü açıkken silinmesin
        m.popup(QCursor.pos())
        m.activateWindow()

    def add_to_card(self, paths, fence):
        for p in paths:
            self.assign(p, fence)
        self.refresh_all()

    def is_autostart(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                try:  # eski addaki kayıt varsa Tuckly'ye çevir
                    winreg.QueryValueEx(k, LEGACY_ID)
                    winreg.DeleteValue(k, LEGACY_ID)
                    winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, self.autostart_command())
                except OSError:
                    pass
                winreg.QueryValueEx(k, APP_ID)
                return True
        except OSError:
            return False

    def set_autostart(self, on):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, self.autostart_command())
                else:
                    try:
                        winreg.DeleteValue(k, APP_ID)
                    except FileNotFoundError:
                        pass
        except OSError as ex:
            self.notify(t('Başlangıç ayarı değiştirilemedi: {0}').format(ex), warn=True)

    def quit(self):
        self.quitting = True
        self.qapp.exit(0)

    def on_quit(self):
        for f in self.fences:
            f.store_note()  # yazılıp henüz kaydedilmemiş not kaybolmasın
            f.data["x"], f.data["y"] = f.x(), f.y()
        self.save()
        if self.config.get("hide_icons"):
            set_desktop_icons_visible(True)
        if self.hide_assigned:  # çıkınca masaüstü eski haline dönsün
            self.sync_hidden(False)
            self.save()
        self.tray.hide()
        self.hotkeys.set_enabled(False)
        self.click_watcher.set_enabled(False)


def run_cleanup(delete_settings=False):
    """Kaldırma sırasında (`--temizle`) arayüz açmadan çalışır: gizlenen simgeleri geri getirir, sağ tık
    menüsü ve başlangıç kayıtlarını siler. delete_settings: ayar klasörünü de siler."""
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    marked = set(config.get("system_marked", []))
    for d in config.get("fences", []):
        if d.get("kind", "desktop") == "desktop":
            for p in d.get("items", []):
                set_file_hidden(p, False, p in marked)
    if not _override:  # testler gerçek masaüstüne ve kayıt defterine dokunmasın
        set_desktop_icons_visible(True)
        register_context_menu(False)
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FencesApp.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, APP_ID)
        except OSError:
            pass
    if delete_settings:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    elif config:
        config["system_marked"] = []
        CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_exception(kind, v, tb):
    import traceback
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(kind, v, tb)) + "\n")
    except OSError:
        pass
    if sys.stderr:
        sys.__excepthook__(kind, v, tb)


def main():
    sys.excepthook = _log_exception
    if not _override:
        register_app_identity()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    qapp.setWindowIcon(make_app_icon())  # kartlar ve açılır pencereler dahil tüm pencereler için
    qapp.setStyle("Fusion")

    # Komut satırı isteği: --cik (düzgünce kapat), --yeni-kart, --ekle <yol>; yoksa paneli göster
    argv = sys.argv
    msg = b"show"
    if "--cik" in argv:
        msg = b"quit"
    elif "--yeni-kart" in argv:
        msg = b"new"
    elif "--ekle" in argv and argv.index("--ekle") + 1 < len(argv):
        msg = b"add\n" + argv[argv.index("--ekle") + 1].encode("utf-8")

    # Kaldırma programı için: çalışan kopyayı kapat, Windows'taki izleri temizle ve çık
    if "--temizle" in argv:
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        if sock.waitForConnected(300):
            sock.write(b"quit")
            sock.flush()
            sock.waitForBytesWritten(300)
            time.sleep(2.5)  # çalışan kopya simgeleri geri getirip ayarlarını kaydetsin
        run_cleanup(delete_settings="--ayarlari-sil" in argv)
        return 0

    # Tek kopya: zaten çalışıyorsa isteği ona ilet ve çık
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        allow_foreground()
        sock.write(msg)
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    if "--cik" in sys.argv:
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    app = FencesApp(qapp)

    def on_conn():
        c = server.nextPendingConnection()
        c.readyRead.connect(lambda: app.handle_message(bytes(c.readAll().data())))

    server.newConnection.connect(on_conn)
    if msg != b"show":  # Tuckly kapalıyken sağ tık menüsünden başlatıldı: açıldıktan sonra isteği uygula
        QTimer.singleShot(700, lambda: app.handle_message(msg))
    elif "--arkaplan" not in sys.argv:
        QTimer.singleShot(300, app.show_panel)
        if not app.config.get("tour_seen"):  # rehber turu, bir kez gösterilene kadar ilk açılışta açılır
            app.config["tour_seen"] = True
            app.save()
            QTimer.singleShot(1200, app.start_tour)
    if "--bildirim-testi" in sys.argv:  # bildirimin hangi adla göründüğünü denemek için
        QTimer.singleShot(1500, lambda: app.notify(t("Bildirim denemesi.")))
    code = qapp.exec()
    server.close()
    return code
