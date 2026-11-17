"""Güncelleme denetimi: projenin GitHub deposundaki en son sürümü sorar.

Yalnızca `REPO_URL` tanımlıysa ve kullanıcı açık bıraktıysa çalışır. GitHub'a yapılan istekte
uygulama adı ve sürümü dışında hiçbir bilgi gönderilmez. İndirme yalnızca kullanıcı "İndir ve kur"a
bastığında ve yalnızca GitHub adreslerinden yapılır.
"""

import json
import re
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import __version__
from .config import REPO_URL

_TRUSTED = ("https://github.com/", "https://objects.githubusercontent.com/",
            "https://release-assets.githubusercontent.com/")


def version_tuple(text: str) -> tuple:
    """"v1.2.3" -> (1, 2, 3); sayı olmayan kısımlar yok sayılır."""
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def is_newer(candidate: str, current: str = __version__) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def repo_api_url(repo_url: str = REPO_URL):
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", repo_url or "")
    return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases/latest" if m else None


class UpdateChecker(QObject):
    """Sorgu ve indirme arka plan iş parçacığında çalışır; sonuç sinyalle bildirilir."""

    finished = Signal(dict)   # {"version", "page", "asset"} ya da {"error": metin}
    downloaded = Signal(str)  # indirilen kurulum dosyasının yolu; başarısızsa ""

    def check(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        api = repo_api_url()
        if not api:
            self.finished.emit({"error": "no repository"})
            return
        try:
            req = urllib.request.Request(api, headers={"User-Agent": f"Tuckly/{__version__}",
                                                       "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.load(resp)
            asset = next((a["browser_download_url"] for a in data.get("assets", [])
                          if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()), "")
            self.finished.emit({"version": data["tag_name"].lstrip("vV"), "page": data.get("html_url", REPO_URL),
                                "asset": asset})
        except Exception as ex:  # noqa: BLE001 - ağ yok, depo yok, sürüm yok...
            self.finished.emit({"error": str(ex)})

    def download(self, url: str):
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url: str):
        try:
            if not url.startswith(_TRUSTED):
                raise ValueError("untrusted download address")
            target = Path(tempfile.mkdtemp(prefix="tuckly_update_")) / url.rsplit("/", 1)[-1]
            req = urllib.request.Request(url, headers={"User-Agent": f"Tuckly/{__version__}"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as out:
                final = resp.geturl()
                if not final.startswith(_TRUSTED):  # yönlendirme GitHub dışına çıktıysa indirme
                    raise ValueError("untrusted redirect")
                while chunk := resp.read(1 << 16):
                    out.write(chunk)
            self.downloaded.emit(str(target))
        except Exception:  # noqa: BLE001
            self.downloaded.emit("")
