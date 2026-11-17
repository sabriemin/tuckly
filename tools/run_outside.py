"""Bir programı Gezgin (explorer.exe) üzerinden başlatır.

Neden gerekli: Tuckly, paketlenmiş bir uygulamanın (örn. bir geliştirme aracının) içinden başlatılırsa
Windows onun kayıt defteri ve AppData yazmalarını o pakete özel sanal bir alana yönlendirir. O zaman
sağ tık menüsü kayıtları ve "Windows ile başlat" Gezgin tarafından görülmez. Bu betik programı
masaüstü kabuğuna başlattırır; program, kullanıcı çift tıklamış gibi normal ortamda çalışır.

Kullanım:  python tools/run_outside.py <program> [argümanlar...]
Gereksinim: pywin32
"""
import subprocess
import sys

import win32com.client


def run_outside(program: str, args: str = "", hidden: bool = False):
    windows = win32com.client.Dispatch("{9BA05972-F6A8-11CF-A442-00A0C90A8F39}")  # ShellWindows
    found = windows.FindWindowSW(0, "", 8, 0, 1)  # masaüstü penceresi (SWC_DESKTOP)
    desktop = found[0] if isinstance(found, tuple) else found
    desktop.Document.Application.ShellExecute(program, args, "", "open", 0 if hidden else 1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    run_outside(sys.argv[1], subprocess.list2cmdline(sys.argv[2:]))
