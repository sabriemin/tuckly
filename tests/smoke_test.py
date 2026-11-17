"""Uçtan uca duman testi: sahte bir masaüstü ve ayrı bir veri klasörüyle uygulamayı çalıştırır.

Kullanım:  python tests/smoke_test.py [çıktı_klasörü]
Gerçek masaüstüne ve gerçek ayarlara dokunmaz (TUCKLY_DATA_DIR ile yalıtılır).
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="tuckly_test_"))
shutil.rmtree(base, ignore_errors=True)
base.mkdir(parents=True)
os.environ["TUCKLY_DATA_DIR"] = str(base)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tuckly import config  # noqa: E402
from tuckly.app import FencesApp  # noqa: E402
from tuckly.utils import is_hidden  # noqa: E402
from tuckly.winapi import desktop_dir  # noqa: E402

desk = desktop_dir()
for n in ["Rapor.pdf", "Notlar.txt", "Bütçe.xlsx", "foto.png", "tatil.jpg", "kurulum.exe", "garip.xyz"]:
    (desk / n).write_text("x")

# Eski sürümün (Masaüstü Kutuları) ayarı: dosyaları kart klasörüne taşınmış bir "Medya" kartı
old = config.FENCE_ROOT / "Medya"
old.mkdir(parents=True)
for n in ["Claude.lnk", "Gemini.lnk"]:
    (old / n).write_text("l")
(config.FENCE_ROOT / "Belgeler").mkdir()
config.LEGACY_DATA_DIR.mkdir(parents=True)
(config.LEGACY_DATA_DIR / "ayarlar.json").write_text(json.dumps({"fences": [
    {"name": "Belgeler", "folder": str(config.FENCE_ROOT / "Belgeler"), "rules": ["pdf", "txt", "xlsx"],
     "x": 900, "y": 20, "w": 340, "h": 220, "color": "#10141c"},
    {"name": "Medya", "folder": str(old), "rules": ["png", "jpg"], "x": 900, "y": 260, "w": 340, "h": 220,
     "theme": "ocean"}]}, ensure_ascii=False), encoding="utf-8")

qapp = QApplication([])
qapp.setQuitOnLastWindowClosed(False)
qapp.setStyle("Fusion")
app = FencesApp(qapp)
belge, medya = app.fences[0], app.fences[1]

# 1) Eski ayarlar devralındı; eski klasördeki kısayollar masaüstüne döndü
assert config.CONFIG_FILE.exists(), "yeni ayar dosyası yazılmadı"
assert (config.LEGACY_DATA_DIR / "ayarlar.json").exists(), "eski ayar dosyasına dokunulmamalı"
assert (desk / "Claude.lnk").exists() and (desk / "Gemini.lnk").exists()
assert not old.exists() and not config.FENCE_ROOT.exists()
assert medya.kind == "desktop" and medya.list.count() == 2
assert app.rest and app.rest.kind == "rest"

# 2) Düzenleme dosyaları taşımaz, yalnızca kartlara yerleştirir; geri alınabilir
app.execute_sort(app.plan_sort())
assert (desk / "Rapor.pdf").exists() and belge.list.count() == 3 and medya.list.count() == 4
assert is_hidden(desk / "Rapor.pdf"), "karta konan dosyanın masaüstü simgesi gizlenmeli"
assert not is_hidden(desk / "garip.xyz"), "kartsız dosya görünür kalmalı"
app.undo_last()
assert belge.list.count() == 0 and medya.list.count() == 2
assert not is_hidden(desk / "Rapor.pdf"), "karttan çıkan dosya yeniden görünmeli"
app.execute_sort(app.plan_sort())

# 3) Dışarıdan bırakılan dosya masaüstüne gelir; masaüstündeki dosya yerinden oynamaz
ext = base / "dis.docx"
ext.write_text("y")
belge.receive([str(ext)])
assert (desk / "dis.docx").exists() and belge.list.count() == 4
medya.receive([str(desk / "Rapor.pdf")])
assert (desk / "Rapor.pdf").exists() and belge.list.count() == 3 and medya.list.count() == 5

# 4) "Diğer" kartı kartsız öğeleri gösterir
app.rest.refresh()
rest = sorted(app.rest.list.item(i).text() for i in range(app.rest.list.count()))
assert rest == ["garip.xyz", "kurulum.exe"], rest

# 5) Kartı kaldırmak dosyalara dokunmaz; yeni kart "Diğer"den önce eklenir
app.remove_fence(belge)
assert (desk / "Notlar.txt").exists() and len(app.fences) == 2
app.new_fence()
assert app.fences[-1] is app.rest

# 5b) Kategoriler, sıralama ve bildirim rozetleri
(desk / "Projeler").mkdir()
(desk / "Discord.lnk").write_text("l")
yeni = app.fences[-2]
yeni.data["categories"] = ["folders", "shortcuts"]
plan = {p.name: f for p, f in app.plan_sort()}
assert plan.get("Projeler") is yeni and plan.get("Discord.lnk") is yeni, plan
app.execute_sort(app.plan_sort())
names = [yeni.list.item(i).text() for i in range(yeni.list.count())]
assert names == ["Projeler", "Discord"], names           # ada göre: klasörler önce
yeni.reorder([str(desk / "Discord.lnk")], 0)               # sürükleyip başa al -> serbest sıralama
assert yeni.data["sort"] == "manual"
assert [yeni.list.item(i).text() for i in range(yeni.list.count())] == ["Discord", "Projeler"]
yeni.data["sort"] = "type"
yeni.refresh()
assert yeni.list.item(0).text() == "Projeler"
app.on_badges([("discord", "com.squirrel.discord.discord", 3), ("whatsapp", "x!app", 1)])
from tuckly.card import BADGE_ROLE  # noqa: E402
badge = {yeni.list.item(i).text(): (yeni.list.item(i).data(BADGE_ROLE) or 0) for i in range(yeni.list.count())}
assert badge == {"Projeler": 0, "Discord": 3}, badge
assert (desk / "Discord.lnk").exists()
yeni.resize(340, 230)
yeni.grab().save(str(base / "badge.png"))

# 5c) Kilitler: içerik kilitliyken karta öğe eklenemez, düzenleme de o kartı atlar
yeni.data["lock_content"] = True
app.fence_changed(yeni)
(desk / "Spotify.lnk").write_text("l")
before = yeni.list.count()
yeni.receive([str(desk / "Spotify.lnk")])
assert yeni.list.count() == before, "içerik kilitli karta öğe eklenmemeli"
assert all(f is not yeni for _, f in app.plan_sort()), "düzenleme kilitli kartı atlamalı"
assert not yeni.list.dragEnabled()
yeni.data["lock_content"] = False
yeni.data["lock_size"] = True
app.fence_changed(yeni)
assert yeni.list.dragEnabled() and yeni.grip.isHidden() and not yeni.title.lock.isHidden()
yeni.data["lock_size"] = False
app.fence_changed(yeni)

# 5d) Sağ tık menüsü istekleri: "yeni kart" ve "karta ekle" (çoklu seçim tek menüde toplanır)
n_before = len(app.fences)
app.handle_message(b"new")
assert len(app.fences) == n_before + 1 and app.fences[-1] is app.rest
from PySide6.QtTest import QTest  # noqa: E402

QTest.qWait(400)  # yeni kartın ayar penceresi kısa bir gecikmeyle kendiliğinden açılır
assert app.fences[-2].popup and app.fences[-2].popup.isVisible()
app.close_popups()
app.handle_message(("add\n" + str(desk / "Spotify.lnk")).encode("utf-8"))
app.handle_message(("add\n" + str(desk / "garip.xyz")).encode("utf-8"))
assert len(app._incoming) == 2
app._incoming_timer.stop()
paths, app._incoming = [Path(p) for p in app._incoming], []
app.add_to_card(paths, yeni)
assert is_hidden(desk / "garip.xyz") and yeni.list.count() == before + 2

# 5e) Kalem düğmesi: kartın adı ayarlara girmeden, başlıkta değişir
yeni.title.start_rename()
assert yeni.title.edit.isVisible() and yeni.title.text.isHidden()
yeni.title.edit.setText("Oyunlar")
yeni.title.finish_rename(True)
assert yeni.data["name"] == "Oyunlar" and yeni.title.text.text() == "Oyunlar" and yeni.title.edit.isHidden()
yeni.title.start_rename()
yeni.title.edit.setText("iptal")
yeni.title.finish_rename(False)
assert yeni.data["name"] == "Oyunlar"

# 5f) Uzun ad dar kartta "…" ile kısalır, tam ad ipucunda kalır
yeni.resize(210, 230)
yeni.data["name"] = "Çok Uzun Bir Kart Adı - Deneme Amaçlı"
app.fence_changed(yeni)
qapp.processEvents()
assert yeni.title.text.text().endswith("…") and yeni.title.text.toolTip() == yeni.data["name"]
yeni.data["name"] = "Oyunlar"
yeni.resize(340, 230)
app.fence_changed(yeni)

# 5g) Gezgin yeniden başlarsa kartlar yeniden kurulur (burada doğrudan çağrılır)
old_ids = [id(f) for f in app.fences]
names = [f.data["name"] for f in app.fences]
app.rebuild_cards()
assert [f.data["name"] for f in app.fences] == names and all(id(f) not in old_ids for f in app.fences)
belge = None
medya, yeni = app.fences[0], app.fences[-3]
assert medya.data["name"] == "Medya" and yeni.data["name"] == "Oyunlar"
assert medya.list.count() == 5 and not yeni.isHidden()

# 6) Kart ayarları kartın yanında ayrı bir pencerede açılır; aynı anda yalnızca biri açık kalır
app.show_panel(medya)
medya.show_settings(True)
assert medya.popup.isVisible() and medya.settings.fence is medya
yeni.show_settings(True)
qapp.processEvents()
assert yeni.popup.isVisible()

# 7) Görünüm: her stil ve mod hatasız uygulanır, ayar dosyasına yazılır
from tuckly.theme import STYLES, appearance  # noqa: E402

shots = []


def step(i=0):
    combos = [(s, m) for s, _ in STYLES for m in ("dark", "light")]
    if i < len(combos):
        style, mode = combos[i]
        app.set_appearance("style", style)
        app.set_appearance("mode", mode)
        app.set_appearance("theme", "ocean" if mode == "dark" else "#c0742d")
        QTimer.singleShot(120, lambda: (shots.append((style, mode, medya.grab())), step(i + 1)))
    else:
        finish()


def finish():
    from PySide6.QtGui import QPainter, QPixmap
    w, h = shots[0][2].width(), shots[0][2].height()
    sheet = QPixmap(w * 4, h * 2)
    sheet.fill("#808890")
    p = QPainter(sheet)
    for k, (style, mode, pm) in enumerate(shots):
        p.drawPixmap((k // 2) * w, (k % 2) * h, pm)
    p.end()
    sheet.save(str(base / "styles.png"))
    yeni.popup.grab().save(str(base / "popup.png"))
    yeni.show_settings(False)
    yeni.set_collapsed(True)   # animasyonlu daraltma başlar; kayıtlı yükseklik bozulmamalı
    assert yeni.data["h"] >= 130, yeni.data["h"]
    app.set_appearance("style", "frosted")
    app.set_appearance("mode", "dark")
    app.set_appearance("font_size", 11)
    app.set_appearance("font_bold", True)
    app.set_appearance("accent", "custom")
    app.set_appearance("accent_color", "#ff8a5c")
    app.apply_look()
    assert appearance(json.loads(config.CONFIG_FILE.read_text(encoding="utf-8")))["font_size"] == 11
    medya.grab().save(str(base / "card.png"))
    app.panel.set_page(1)
    qapp.processEvents()
    app.panel.grab().save(str(base / "panel_appearance.png"))
    app.set_appearance("mode", "light")
    app.apply_look()
    qapp.processEvents()
    app.panel.grab().save(str(base / "panel_light.png"))
    app.reset_appearance()
    assert appearance(app.config)["font_size"] == 9
    app.quit()


QTimer.singleShot(500, step)
rc = qapp.exec()
left = sorted(p.name for p in desk.iterdir())
assert len(left) == 13, left
assert not any(is_hidden(p) for p in desk.iterdir()), "çıkışta tüm simgeler geri gelmeli"
print("TAMAM — çıkış kodu", rc, "| görüntüler:", base)
