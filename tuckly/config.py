"""Uygulama sabitleri, dosya yolları ve varsayılanlar."""

import os
import sys
from pathlib import Path

from .i18n import mark


APP_NAME = "Tuckly"


APP_ID = "Tuckly"


AUMID = "Tuckly"  # kaynak koddan çalışırken bildirim başlığında görünen kimlik


# Projenin GitHub deposu. Boşken "yıldız ver", "sorun bildir" ve "sürümler" düğmeleri gizlenir.
REPO_URL = "https://github.com/sabriemin/tuckly"
# Hakkında sayfasının altında gösterilen geliştirici ve profil bağlantısı
AUTHOR = "sabriemin"
AUTHOR_URL = "https://github.com/sabriemin"
# Windows simge yazı tipleri (Windows 11: Fluent, Windows 10: MDL2); simgeler özel kullanım kod noktalarıdır
ICON_FONT = '"Segoe Fluent Icons", "Segoe MDL2 Assets"'
LEGACY_ID = "MasaustuKutulari"  # uygulamanın eski adı; ayarlar buradan devralınır


_override = os.environ.get("TUCKLY_DATA_DIR")  # testler için ayrı veri klasörü


if _override:
    DATA_DIR = Path(_override) / "ayarlar"
    LEGACY_DATA_DIR = Path(_override) / "eski_ayarlar"
    FENCE_ROOT = Path(_override) / "kutular"
else:
    DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_ID
    LEGACY_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / LEGACY_ID
    FENCE_ROOT = Path.home() / LEGACY_ID  # yalnızca eski sürümden kalan klasörleri geri taşımak için


CONFIG_FILE = DATA_DIR / "settings.json"


UNDO_FILE = DATA_DIR / "last_sort.json"


LOG_FILE = DATA_DIR / "error.log"


def resource(name: str) -> Path:
    """Paketle gelen dosyanın (simge vb.) yolu; PyInstaller ile paketlenmiş exe'de de çalışır."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


SERVER_NAME = APP_ID + "_" + os.environ.get("USERNAME", "u") + ("_test" if _override else "")


SNAP = 10


TITLE_H = 40


PARTIAL_EXT = {".crdownload", ".part", ".tmp", ".partial", ".download", ".opdownload"}


SKIP_NAMES = {"desktop.ini", "thumbs.db"}


ICON_SIZES = ((mark("Küçük"), 28), (mark("Orta"), 36), (mark("Büyük"), 48))


TOGGLE_ON = "#34c759"


# Not kartı kâğıt renkleri (yapışkan not görünümü) ve yazı boyutu farkları (punto)
PAPERS = ("#ffe680", "#ffc2d1", "#a8d8ff", "#b9ebb4", "#d9c8ff", "#ffd3a1")
NOTE_SIZES = ((mark("Küçük"), 0), (mark("Orta"), 2), (mark("Büyük"), 4))


# Haftanın günleri (kısa); sıra Python'un tm_wday sırasıdır: 0 = Pazartesi
DAYS = (mark("Pzt"), mark("Sal"), mark("Çar"), mark("Per"), mark("Cum"), mark("Cmt"), mark("Paz"))


# Kart şablonları: (anahtar, ad, kartlar); kart: (ad, tür, kategoriler, simge, ad kuralları)
TEMPLATES = (
    ("work", mark("İş"), (
        (mark("Belgeler"), "desktop", ("documents", "sheets", "slides"), "💼", ()),
        (mark("Projeler"), "desktop", ("folders",), "📁", ()),
        (mark("Yapılacaklar"), "note", (), "", ()))),
    ("game", mark("Oyun"), (
        (mark("Oyunlar"), "desktop", (), "🎮",
         ("steam", "epic", "riot", "ubisoft", "battle.net", "gog", "xbox", "ea app", "rockstar")),
        (mark("Medya"), "desktop", ("video", "audio"), "🎵", ()))),
    ("design", mark("Tasarım"), (
        (mark("Görseller"), "desktop", ("images",), "🎨", ()),
        (mark("Arşivler"), "desktop", ("archives",), "📁", ()),
        (mark("Fikirler"), "note", (), "", ()))),
    ("student", mark("Öğrenci"), (
        (mark("Dersler"), "desktop", ("documents",), "📚", ()),
        (mark("Sunumlar"), "desktop", ("slides",), "💻", ()),
        (mark("Yapılacaklar"), "note", (), "", ()))),
)


# Kart başlığına eklenebilen simgeler
EMOJIS = ("📁", "🎮", "💼", "🎨", "🎵", "📷", "📚", "💻", "⭐")


DEFAULT_FONT = "Segoe UI Variable Text"


THEMES = [
    ("graphite", mark("Grafit"), "#8e8e93", 0.04, "#0a84ff"),
    ("midnight", mark("Gece"), "#5e8bff", 0.40, "#7aa2ff"),
    ("ocean", mark("Okyanus"), "#2ec4d6", 0.45, "#35d0e0"),
    ("forest", mark("Orman"), "#34c77b", 0.28, "#4ade80"),
    ("plum", mark("Mor"), "#c77dff", 0.30, "#c58bff"),
    ("rose", mark("Gül"), "#ff5e8a", 0.30, "#ff6b95"),
    ("ember", mark("Kor"), "#ff7a45", 0.32, "#ff8a5c"),
    ("crimson", mark("Kızıl"), "#ff453a", 0.34, "#ff6b61"),
    ("gold", mark("Altın"), "#f5b942", 0.30, "#f7c95f"),
    ("sky", mark("Gökyüzü"), "#38bdf8", 0.42, "#5cc8fa"),
]


THEME_KEYS = [t[0] for t in THEMES]

# Dosya kategorileri: (anahtar, görünen ad, uzantılar). "folders" klasörleri kapsar.
CATEGORIES = [
    ("shortcuts", mark("Kısayollar"), ("lnk", "url")),
    ("folders", mark("Klasörler"), ()),
    ("documents", mark("Belgeler"), ("pdf", "doc", "docx", "txt", "rtf", "odt", "md")),
    ("sheets", mark("Tablolar"), ("xls", "xlsx", "csv", "ods")),
    ("slides", mark("Sunumlar"), ("ppt", "pptx", "odp")),
    ("images", mark("Resimler"), ("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "heic", "tif", "tiff", "psd")),
    ("video", mark("Videolar"), ("mp4", "mkv", "avi", "mov", "webm", "wmv")),
    ("audio", mark("Ses ve müzik"), ("mp3", "wav", "flac", "ogg", "m4a")),
    ("archives", mark("Arşivler"), ("zip", "rar", "7z", "tar", "gz", "iso")),
    ("installers", mark("Kurulum dosyaları"), ("exe", "msi")),
    ("code", mark("Kod"), ("py", "js", "ts", "html", "css", "json", "cpp", "cs", "java")),
]
CATEGORY_EXTS = {key: exts for key, _, exts in CATEGORIES}

# Karttaki öğelerin sıralanma biçimleri: (anahtar, görünen ad)
SORT_MODES = (("name", mark("Ad")), ("type", mark("Tür")), ("date", mark("Tarih")), ("manual", mark("Serbest")))

# İlk çalıştırmada oluşturulan kartlar: (ad, kategoriler)
DEFAULT_FENCES = [
    (mark("Kısayollar"), ["shortcuts"]),
    (mark("Belgeler"), ["documents", "sheets", "slides"]),
    (mark("Resimler"), ["images"]),
    (mark("Medya"), ["video", "audio"]),
    (mark("Arşiv ve Kurulum"), ["archives", "installers"]),
]
