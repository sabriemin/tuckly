"""Masaüstüne çift tıklamayı ve genel kısayol tuşlarını izler.

Çift tıklama için fare kancası kullanılmaz: sistem genelinde fareyi yavaşlatabilir. Bunun yerine fare
düğmesinin durumu kısa aralıklarla okunur; bu yalnızca özellik açıkken çalışır.
"""

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

from .winapi import desktop_listview, user32

VK_LBUTTON = 0x01
LVM_GETSELECTEDCOUNT = 0x1032
DESKTOP_CLASSES = {"SysListView32", "SHELLDLL_DefView", "Progman", "WorkerW"}
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000

user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def _on_desktop(pt: wintypes.POINT) -> bool:
    """İmlecin altındaki pencere masaüstünün kendisi mi (bir kart ya da başka pencere değil)?"""
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return False
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, name, 64)
    if name.value not in DESKTOP_CLASSES:
        return False
    if name.value == "SysListView32":  # Gezgin pencerelerindeki listeler sayılmaz
        return hwnd == desktop_listview()
    return True


class DesktopClickWatcher(QObject):
    """Masaüstünde boş bir yere çift tıklanınca `double_clicked` sinyalini yayar."""

    double_clicked = Signal()

    def __init__(self):
        super().__init__()
        self._timer = QTimer(self, interval=25, timeout=self._poll)
        self._down = False
        self._last = None  # (zaman, x, y) son masaüstü tıklaması

    def set_enabled(self, on: bool):
        if on:
            self._down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            self._timer.start()
        else:
            self._timer.stop()
            self._last = None

    def _poll(self):
        down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        if down == self._down:
            return
        self._down = down
        if not down:
            return
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        if not _on_desktop(pt):
            self._last = None
            return
        now = time.monotonic()
        last, self._last = self._last, (now, pt.x, pt.y)
        if (last and now - last[0] <= user32.GetDoubleClickTime() / 1000
                and abs(pt.x - last[1]) <= 4 and abs(pt.y - last[2]) <= 4):
            self._last = None
            QTimer.singleShot(80, self._confirm)  # Gezgin seçimi güncellesin

    def _confirm(self):
        lv = desktop_listview()
        # Bir simgeye çift tıklandıysa o simge seçilidir: bu bir "aç" isteğidir, gizleme değil
        if lv and user32.IsWindowVisible(lv) and user32.SendMessageW(lv, LVM_GETSELECTEDCOUNT, 0, 0) > 0:
            return
        self.double_clicked.emit()


class Hotkeys(QAbstractNativeEventFilter):
    """Genel kısayol tuşları: Ctrl+Alt+<harf>. Başka bir program aynı tuşu almışsa o tuş atlanır."""

    def __init__(self, qapp, actions: dict):
        super().__init__()
        self.qapp = qapp
        self.actions = actions  # {"H": işlev, ...}
        self._ids = {}
        qapp.installNativeEventFilter(self)

    def set_enabled(self, on: bool):
        for ident in self._ids:
            user32.UnregisterHotKey(None, ident)
        self._ids = {}
        if on:
            for i, (key, action) in enumerate(self.actions.items(), start=1):
                if user32.RegisterHotKey(None, 0xB000 + i, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)):
                    self._ids[0xB000 + i] = action

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam in self._ids:
                    QTimer.singleShot(0, self._ids[msg.wParam])
                    return True, 0
        except Exception:  # noqa: BLE001
            pass
        return False, 0
