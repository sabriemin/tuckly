"""Çeviri: arayüz metinleri kaynak kodda Türkçe yazılır, `t()` seçili dildeki karşılığını döndürür.

Çeviri dosyaları `tuckly/i18n/<dil>.json` içindedir: {"Türkçe metin": "çevirisi", ...}.
Çevirisi olmayan metin Türkçe gösterilir. Yeni dil eklemek için LANGUAGES'a bir satır ve bir
JSON dosyası eklemek yeterlidir; `python tools/extract_strings.py` eksik metinleri listeler.
"""

import ctypes
import json
import sys
from pathlib import Path

# (dil kodu, dilin kendi adı)
LANGUAGES = (
    ("tr", "Türkçe"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("ru", "Русский"),
)
SOURCE_LANGUAGE = "tr"

_table = {}
_current = SOURCE_LANGUAGE


def _folder() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "i18n"


def system_language() -> str:
    """Windows arayüz diline en yakın desteklenen dil; desteklenmiyorsa İngilizce."""
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except Exception:  # noqa: BLE001
        return "en"
    return {0x1F: "tr", 0x09: "en", 0x07: "de", 0x0A: "es", 0x0C: "fr", 0x19: "ru"}.get(primary, "en")


def set_language(code=None) -> str:
    """Dili seçer (None: Windows'un dili). Seçilen dil kodunu döndürür."""
    global _table, _current
    codes = [c for c, _ in LANGUAGES]
    code = code if code in codes else system_language()
    _table = {}
    if code != SOURCE_LANGUAGE:
        try:
            _table = json.loads((_folder() / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _table = {}
    _current = code
    return code


def current_language() -> str:
    return _current


def t(text: str) -> str:
    """Metnin seçili dildeki karşılığı; çeviri yoksa metnin kendisi."""
    return _table.get(text) or text


def mark(text: str) -> str:
    """Modül düzeyindeki sabitlerde metni çeviri için işaretler; çeviriyi kullanım yerindeki t() yapar."""
    return text
