"""assets/tuckly.svg dosyasından PNG boyutlarını, tuckly.ico'yu, yazılı logoyu ve önizlemeyi üretir.

Kullanım:  python tools/build_icons.py      (Gereksinim: PySide6, Pillow)
"""
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(renderer, size) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def wordmark(renderer, text_color, name):
    h, pad = 256, 24
    font = QFont("Segoe UI Variable Display", 1)
    font.setPixelSize(150)
    font.setWeight(QFont.DemiBold)
    font.setLetterSpacing(QFont.PercentageSpacing, 97)
    from PySide6.QtGui import QFontMetrics
    tw = QFontMetrics(font).horizontalAdvance("Tuckly")
    w = pad + h - 2 * pad + 44 + tw + pad
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    renderer.render(p, QRectF(pad, pad, h - 2 * pad, h - 2 * pad))
    p.setFont(font)
    p.setPen(QColor(text_color))
    p.drawText(QRectF(h - pad + 44, 0, tw + pad, h - 10), Qt.AlignVCenter | Qt.AlignLeft, "Tuckly")
    p.end()
    img.save(str(ASSETS / name))
    return img


def preview(renderer):
    """Koyu ve açık zeminde küçük boyutları ve yazılı logoyu yan yana gösterir."""
    W, H = 1200, 560
    img = QImage(W, H, QImage.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    p.fillRect(0, 0, W, H // 2, QColor("#15161D"))
    p.fillRect(0, H // 2, W, H // 2, QColor("#EEF0F4"))
    for row, (dark, wm) in enumerate(((True, "tuckly-wordmark-dark.png"), (False, "tuckly-wordmark-light.png"))):
        y0 = row * H // 2
        x = 40
        for s in (160, 96, 64, 48, 32, 24, 16):
            p.drawImage(QRectF(x, y0 + (H // 2 - s) / 2, s, s), render(renderer, s if s <= 64 else s * 2))
            x += s + 34
        w = QImage(str(ASSETS / wm))
        tw = 420
        th = tw * w.height() / w.width()
        p.drawImage(QRectF(W - tw - 40, y0 + (H // 2 - th) / 2, tw, th), w)
    p.end()
    img.save(str(ASSETS / "preview.png"))


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(str(ASSETS / "tuckly.svg"))
    (ASSETS / "png").mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        render(renderer, s).save(str(ASSETS / "png" / f"tuckly-{s}.png"))
    Image.open(ASSETS / "png" / "tuckly-256.png").save(
        ASSETS / "tuckly.ico", sizes=[(s, s) for s in ICO_SIZES])
    wordmark(renderer, "#FFFFFF", "tuckly-wordmark-dark.png")
    wordmark(renderer, "#14151F", "tuckly-wordmark-light.png")
    preview(renderer)
    print("ok:", sorted(p.name for p in ASSETS.iterdir()))


if __name__ == "__main__":
    main()
