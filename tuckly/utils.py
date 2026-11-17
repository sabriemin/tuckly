"""Dosya adı ve yol yardımcıları."""

import os
from pathlib import Path

from .config import SNAP


def norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def unique_dest(folder: Path, name: str) -> Path:
    dst = folder / name
    if not dst.exists():
        return dst
    p = Path(name)
    stem, suf = (p.stem, p.suffix) if p.suffix and len(p.suffix) <= 6 else (name, "")
    i = 2
    while (folder / f"{stem} ({i}){suf}").exists():
        i += 1
    return folder / f"{stem} ({i}){suf}"


def safe_name(name: str) -> str:
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip().rstrip(".") or "Kart"


def is_hidden(p: Path) -> bool:
    try:
        return bool(os.stat(p).st_file_attributes & 0x2)
    except OSError:
        return True


def snap(v: int) -> int:
    return int(round(v / SNAP) * SNAP)
