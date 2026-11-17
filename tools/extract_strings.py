"""Çevrilecek metinleri kaynak koddan toplar ve çeviri dosyalarını denetler.

Kaynak kodda `t("...")` ve `mark("...")` ile işaretlenmiş tüm metinleri bulur, sonra
`tuckly/i18n/<dil>.json` dosyalarında eksik, fazla ya da yer tutucusu ({0}, {1}) bozuk çevirileri listeler.

Kullanım:
    python tools/extract_strings.py            # denetle
    python tools/extract_strings.py --template  # tuckly/i18n/_template.json dosyasını yaz (çevirmenler için)

Çıkış kodu: eksik ya da bozuk çeviri varsa 1, yoksa 0.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "tuckly"
I18N = PKG / "i18n"
sys.path.insert(0, str(ROOT))
from tuckly.i18n import LANGUAGES, SOURCE_LANGUAGE  # noqa: E402


def collect() -> list:
    found = {}
    for path in sorted(PKG.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("t", "mark")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, f"{path.name}:{node.lineno}")
    return list(found)


def placeholders(text: str) -> list:
    return sorted(re.findall(r"\{\d+\}", text))


def main() -> int:
    strings = collect()
    print(f"{len(strings)} çevrilebilir metin")
    if "--template" in sys.argv:
        I18N.mkdir(exist_ok=True)
        (I18N / "_template.json").write_text(
            json.dumps({s: "" for s in strings}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("yazıldı:", I18N / "_template.json")
    bad = 0
    for code, name in LANGUAGES:
        if code == SOURCE_LANGUAGE:
            continue
        path = I18N / f"{code}.json"
        if not path.exists():
            print(f"  {code} ({name}): dosya yok")
            bad += 1
            continue
        table = json.loads(path.read_text(encoding="utf-8"))
        missing = [s for s in strings if not table.get(s)]
        extra = [s for s in table if s not in strings]
        broken = [s for s in strings if table.get(s) and placeholders(s) != placeholders(table[s])]
        print(f"  {code} ({name}): {len(strings) - len(missing)}/{len(strings)} çevrildi"
              + (f", {len(extra)} kullanılmayan" if extra else "")
              + (f", {len(broken)} yer tutucusu bozuk" if broken else ""))
        for s in missing[:8]:
            print("      eksik:", repr(s)[:90])
        for s in broken[:8]:
            print("      bozuk:", repr(s)[:60], "->", repr(table[s])[:60])
        bad += len(missing) + len(broken)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
