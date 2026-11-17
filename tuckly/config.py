"""Uygulama sabitleri, dosya yolları ve varsayılanlar."""

import os
import sys
from pathlib import Path


APP_NAME = "Tuckly"


APP_ID = "Tuckly"


AUMID = "Tuckly"  # kaynak koddan çalışırken bildirim başlığında görünen kimlik


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


ICON_SIZES = (("Küçük", 28), ("Orta", 36), ("Büyük", 48))


TOGGLE_ON = "#34c759"


DEFAULT_FONT = "Segoe UI Variable Text"


THEMES = [
    ("graphite", "Grafit", "#8e8e93", 0.04, "#0a84ff"),
    ("midnight", "Gece", "#5e8bff", 0.40, "#7aa2ff"),
    ("ocean", "Okyanus", "#2ec4d6", 0.45, "#35d0e0"),
    ("forest", "Orman", "#34c77b", 0.28, "#4ade80"),
    ("plum", "Mor", "#c77dff", 0.30, "#c58bff"),
    ("rose", "Gül", "#ff5e8a", 0.30, "#ff6b95"),
    ("ember", "Kor", "#ff7a45", 0.32, "#ff8a5c"),
    ("crimson", "Kızıl", "#ff453a", 0.34, "#ff6b61"),
    ("gold", "Altın", "#f5b942", 0.30, "#f7c95f"),
    ("sky", "Gökyüzü", "#38bdf8", 0.42, "#5cc8fa"),
]


THEME_KEYS = [t[0] for t in THEMES]

# Dosya kategorileri: (anahtar, görünen ad, uzantılar). "folders" klasörleri kapsar.
CATEGORIES = [
    ("shortcuts", "Kısayollar", ("lnk", "url")),
    ("folders", "Klasörler", ()),
    ("documents", "Belgeler", ("pdf", "doc", "docx", "txt", "rtf", "odt", "md")),
    ("sheets", "Tablolar", ("xls", "xlsx", "csv", "ods")),
    ("slides", "Sunumlar", ("ppt", "pptx", "odp")),
    ("images", "Resimler", ("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "heic", "tif", "tiff", "psd")),
    ("video", "Videolar", ("mp4", "mkv", "avi", "mov", "webm", "wmv")),
    ("audio", "Ses ve müzik", ("mp3", "wav", "flac", "ogg", "m4a")),
    ("archives", "Arşivler", ("zip", "rar", "7z", "tar", "gz", "iso")),
    ("installers", "Kurulum dosyaları", ("exe", "msi")),
    ("code", "Kod", ("py", "js", "ts", "html", "css", "json", "cpp", "cs", "java")),
]
CATEGORY_EXTS = {key: exts for key, _, exts in CATEGORIES}

# Karttaki öğelerin sıralanma biçimleri: (anahtar, görünen ad)
SORT_MODES = (("name", "Ad"), ("type", "Tür"), ("date", "Tarih"), ("manual", "Serbest"))

# İlk çalıştırmada oluşturulan kartlar: (ad, kategoriler)
DEFAULT_FENCES = [
    ("Kısayollar", ["shortcuts"]),
    ("Belgeler", ["documents", "sheets", "slides"]),
    ("Resimler", ["images"]),
    ("Medya", ["video", "audio"]),
    ("Arşiv ve Kurulum", ["archives", "installers"]),
]
