# -*- mode: python ; coding: utf-8 -*-
# PyInstaller tarifi: `python -m PyInstaller --noconfirm --clean tuckly.spec`  ->  dist\Tuckly\Tuckly.exe
#
# Tuckly yalnızca Qt Widgets kullanır. PySide6 ile birlikte gelen ve kullanılmayan büyük parçalar
# (yazılım OpenGL, Quick/QML, PDF, çeviri dosyaları...) dağıtıma alınmaz; klasör yaklaşık yarıya iner.

EXCLUDED_MODULES = [
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtOpenGL", "PySide6.QtSvg",
    "PySide6.QtSvgWidgets", "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDBus", "PySide6.QtDesigner", "PySide6.Qt3DCore",
    "tkinter", "unittest", "pydoc", "PIL",
]
# Dosya adında bunlardan biri geçen ikili ve veri dosyaları atılır
EXCLUDED_FILES = (
    "opengl32sw", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6OpenGL", "Qt6Svg", "Qt6VirtualKeyboard",
    "Qt6Multimedia", "Qt6Sql", "Qt6Test", "Qt6DBus", "d3dcompiler", "qtwebengine",
    "\\translations\\", "\\qml\\", "\\plugins\\sqldrivers", "\\plugins\\multimedia", "\\plugins\\qmltooling",
    "\\plugins\\generic", "\\plugins\\networkinformation", "\\plugins\\tls", "\\plugins\\platforminputcontexts",
    "qsvg", "qpdf", "qtiff", "qwebp", "qicns", "qtga", "qwbmp", "qgif", "qjpeg",
)


def keep(entry):
    name = (entry[0] + "|" + str(entry[1])).replace("/", "\\").lower()
    return not any(x.lower() in name for x in EXCLUDED_FILES)


a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("tuckly/assets", "assets"), ("tuckly/i18n", "i18n")],
    hiddenimports=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tuckly",
    console=False,
    icon="assets/tuckly.ico",
    version="tools/version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Tuckly")
