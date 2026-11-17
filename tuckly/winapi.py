"""Windows API yardımcıları: masaüstü klasörleri, cam efekti, uygulama kimliği."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtGui import QColor

from .config import AUMID, SKIP_NAMES, _override
from .i18n import t
from .utils import is_hidden, norm


user32 = ctypes.windll.user32


shell32 = ctypes.windll.shell32


user32.FindWindowW.restype = wintypes.HWND


user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]


user32.FindWindowExW.restype = wintypes.HWND


user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]


user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


_SetWindowLongPtr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)


_SetWindowLongPtr.restype = ctypes.c_void_p


_SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


WM_WINDOWPOSCHANGING = 0x0046


SWP_NOZORDER = 0x0004


HWND_BOTTOM = 1


GWL_HWNDPARENT = -8


class WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND),
                ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT)]


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def _shell_folder(csidl):
    buf = ctypes.create_unicode_buffer(260)
    shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value) if buf.value else None


def desktop_dir() -> Path:
    if _override:  # test: sahte masaüstü
        d = Path(_override) / "masaustu"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return _shell_folder(0x10) or Path.home() / "Desktop"  # CSIDL_DESKTOPDIRECTORY


def desktop_dirs() -> list:
    """Masaüstünde görünen klasörler: kullanıcının ve tüm kullanıcıların (Public) masaüstü."""
    dirs = [desktop_dir()]
    if not _override:
        pub = _shell_folder(0x19)  # CSIDL_COMMON_DESKTOPDIRECTORY
        if pub and pub.exists() and pub != dirs[0]:
            dirs.append(pub)
    return dirs


def desktop_entries() -> list:
    out = []
    for d in desktop_dirs():
        try:
            out += [p for p in d.iterdir() if p.name.lower() not in SKIP_NAMES and not is_hidden(p)]
        except OSError:
            pass
    return out


def on_desktop(p: Path) -> bool:
    return any(norm(p.parent) == norm(d) for d in desktop_dirs())


def desktop_window():
    """Masaüstünün ana penceresi (Progman); Gezgin kapalıyken 0/None."""
    return user32.FindWindowW("Progman", None)


def desktop_listview():
    progman = user32.FindWindowW("Progman", None)
    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if not defview:
        found = []

        def cb(hwnd, _):
            dv = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if dv:
                found.append(dv)
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        defview = found[0] if found else None
    return user32.FindWindowExW(defview, None, "SysListView32", None) if defview else None


def set_desktop_icons_visible(visible: bool):
    lv = desktop_listview()
    if lv:
        user32.ShowWindow(lv, 5 if visible else 0)


def set_dark_titlebar(widget, dark=True):
    try:
        val = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(widget.winId()), 20, ctypes.byref(val), 4)
    except Exception:  # noqa: BLE001
        pass


def windows_accent():
    """Windows vurgu rengi ("#rrggbb"); okunamazsa None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\DWM") as k:
            v = winreg.QueryValueEx(k, "AccentColor")[0]  # 0xAABBGGRR
        return f"#{v & 0xff:02x}{(v >> 8) & 0xff:02x}{(v >> 16) & 0xff:02x}"
    except OSError:
        return None


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WCADATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENTPOLICY)),
                ("SizeOfData", ctypes.c_size_t)]


def set_acrylic(widget, color: QColor, alpha: int, enable=True) -> bool:
    """Pencerenin arkasını bulanıklaştıran renkli cam (akrilik). Başarısızsa False döner."""
    try:
        hwnd = int(widget.winId())
        ap = ACCENTPOLICY()
        ap.AccentState = 4 if enable else 0  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        ap.GradientColor = (max(2, min(255, alpha)) << 24) | (color.blue() << 16) | (color.green() << 8) | color.red()
        data = WCADATA(19, ctypes.pointer(ap), ctypes.sizeof(ap))  # WCA_ACCENT_POLICY
        fn = user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(WCADATA)]
        fn.restype = wintypes.BOOL
        ok = bool(fn(hwnd, ctypes.byref(data)))
        corner = ctypes.c_int(1)  # Windows kendi köşe yuvarlamasını yapmasın; köşeler bölgeyle kırpılır
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)
        return ok
    except Exception:  # noqa: BLE001
        return False


def set_window_region(widget, radius):
    """Pencereyi yuvarlak köşeli bir bölgeyle kırpar; bulanıklık katmanı da köşelere uyar.
    radius None ya da 0: kırpmayı kaldırır."""
    try:
        hwnd = int(widget.winId())
        fn = user32.SetWindowRgn
        fn.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
        if not radius:
            fn(hwnd, None, True)
            return
        dpr = widget.devicePixelRatioF()
        w, h, d = round(widget.width() * dpr), round(widget.height() * dpr), round(radius * dpr * 2)
        make = ctypes.windll.gdi32.CreateRoundRectRgn
        make.restype = ctypes.c_void_p
        fn(hwnd, make(0, 0, w + 1, h + 1, d, d), True)  # bölgenin sahibi artık pencere
    except Exception:  # noqa: BLE001
        pass


def explorer_view():
    """Gezgin'in görünüm ayarı: (gizli dosyaları gösteriyor mu, korumalı sistem dosyalarını gösteriyor mu)."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced") as k:
            def val(name, default):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except OSError:
                    return default
            return val("Hidden", 2) == 1, val("ShowSuperHidden", 0) == 1
    except OSError:
        return False, False


def file_attrs(path):
    """Dosyanın Windows öznitelikleri; okunamazsa None."""
    k32 = ctypes.windll.kernel32
    k32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    k32.GetFileAttributesW.restype = wintypes.DWORD
    attrs = k32.GetFileAttributesW(str(path))
    return None if attrs == 0xFFFFFFFF else attrs


def set_file_hidden(path, hidden: bool, system: bool = False) -> bool:
    """Dosyanın "gizli" (ve istenirse "sistem") özniteliğini açar/kapatır, Gezgin'e haber verir.
    Dosya yerinde kalır. system: Gezgin gizli dosyaları gösteriyorsa simgenin gerçekten
    kaybolması için gereken ek işaret."""
    try:
        attrs = file_attrs(path)
        if attrs is None:
            return False
        bits = 0x2 | (0x4 if system else 0)
        new = (attrs | bits) if hidden else (attrs & ~bits)
        if new == attrs:
            return True
        k32 = ctypes.windll.kernel32
        k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        if not k32.SetFileAttributesW(str(path), new):
            return False  # örn. tüm kullanıcıların masaüstündeki kısayollar: yetki yok
        shell32.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_void_p]
        shell32.SHChangeNotify(0x00002000, 0x0005, str(path), None)  # SHCNE_UPDATEITEM, SHCNF_PATHW
        return True
    except Exception:  # noqa: BLE001
        return False


def register_app_identity():
    """Bildirim başlığında ve görev çubuğunda doğru adın görünmesini sağlar.

    Derlenmiş Tuckly.exe'de Windows adı ve simgeyi exe dosyasından alır; özel bir kimlik vermek
    bunu bozduğu için hiçbir şey yapılmaz. Kaynak koddan (python.exe ile) çalışırken ise başlıkta
    "Python" yerine bu kimlik yazısı görünür."""
    if getattr(sys, "frozen", False):
        return
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
    except Exception:  # noqa: BLE001
        pass


def recycle(paths) -> bool:
    """Geri Dönüşüm Kutusuna gönderir (geri alınabilir, onay penceresi açmaz)."""
    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = "\0".join(str(p) for p in paths) + "\0"
    op.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return shell32.SHFileOperationW(ctypes.byref(op)) == 0


# Gezgin'in sağ tık menüsündeki Tuckly girdileri (yalnızca geçerli kullanıcı için, yönetici izni gerekmez)
_MENU_BACKGROUND = "Software\\Classes\\DesktopBackground\\Shell\\Tuckly"
_MENU_ITEMS = "Software\\Classes\\AllFilesystemObjects\\shell\\Tuckly"


def register_context_menu(enable: bool, command: str = "", icon: str = "") -> bool:
    """Masaüstünün boş alanına "Yeni Tuckly kartı", dosya ve klasörlere "Tuckly kartına ekle"
    sağ tık girdilerini ekler ya da kaldırır. command: Tuckly'yi başlatan komut (tırnaklı)."""
    import winreg
    try:
        if not enable:
            for key in (_MENU_BACKGROUND, _MENU_ITEMS):
                for sub in (key + "\\command", key):
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                    except OSError:
                        pass
            return True
        entries = (
            (_MENU_BACKGROUND, t("Yeni Tuckly kartı"), "--yeni-kart", {}),
            # MultiSelectModel=Player: çok sayıda öğe seçiliyken de komut her öğe için çalışsın
            (_MENU_ITEMS, t("Tuckly kartına ekle"), '--ekle "%1"', {"MultiSelectModel": "Player"}),
        )
        for key, title, args, extra in entries:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, title)
                if icon:
                    winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
                for name, value in extra.items():
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + "\\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{command} {args}")
        # Çalışan Gezgin yeni girdileri hemen okusun (SHCNE_ASSOCCHANGED)
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        return True
    except OSError:
        return False


def allow_foreground():
    """Zaten çalışan Tuckly'nin öne pencere/menü açabilmesi için bu sürecin ön plan hakkını devreder."""
    try:
        user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:  # noqa: BLE001
        pass


_class_icons = []  # yüklenen simge tutamaçları; pencere sınıfı kullandığı sürece yaşamalı


def set_class_icon(widget, ico_path) -> bool:
    """Pencere sınıfının simgesini uygulama logosu yapar.

    Qt pencere sınıfını Windows'un genel uygulama simgesiyle kaydeder; pencere simgesini ayrıca verir.
    Simgeyi sınıftan okuyan dock ve görev çubuğu araçları bu yüzden boş simge gösterir.
    """
    try:
        hwnd = int(widget.winId())
        get = getattr(user32, "SetClassLongPtrW", user32.SetClassLongW)
        get.restype = ctypes.c_void_p
        get.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, wintypes.UINT]
        done = False
        for index, size in ((-14, 48), (-34, 16)):  # GCLP_HICON, GCLP_HICONSM
            icon = user32.LoadImageW(None, str(ico_path), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if icon:
                _class_icons.append(icon)
                get(hwnd, index, icon)
                done = True
        return done
    except (OSError, AttributeError, ValueError):
        return False


def wallpaper_key():
    """Geçerli duvar kâğıdı: (dosya yolu, değişiklik zamanı); okunamazsa None."""
    try:
        buf = ctypes.create_unicode_buffer(520)
        if not user32.SystemParametersInfoW(0x0073, 520, buf, 0) or not buf.value:  # SPI_GETDESKWALLPAPER
            return None
        return buf.value, Path(buf.value).stat().st_mtime
    except OSError:
        return None


def fullscreen_busy() -> bool:
    """Tam ekran bir uygulama (oyun, sunum, tam ekran video) çalışıyor mu?"""
    try:
        state = ctypes.c_int(0)
        if shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
        return state.value in (2, 3, 4)  # QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
    except (OSError, AttributeError):
        return False
