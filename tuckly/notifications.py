"""Bildirim sayıları: Windows bildirim merkezinde bekleyen bildirimleri uygulama başına sayar.

Windows'un UserNotificationListener arayüzünü kullanır (isteğe bağlı `winrt` paketleri). Paketler
kurulu değilse ya da kullanıcı izin vermezse özellik sessizce devre dışı kalır.

Not: Bu, bir uygulamanın kendi "okunmamış" sayısı değildir; bildirim merkezinde duran bildirim
sayısıdır. Kullanıcı bildirimi kapatınca sayı da düşer.
"""

import asyncio
import threading

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from winrt.windows.ui.notifications import NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
    AVAILABLE = True
except Exception:  # noqa: BLE001 - paket yok ya da bu Windows sürümünde desteklenmiyor
    AVAILABLE = False


def matches(stem: str, name: str, aumid: str) -> bool:
    """Bir kısayol adı (küçük harf) bildirimin uygulama adıyla ya da kimliğiyle eşleşiyor mu."""
    if not stem:
        return False
    if stem == name:
        return True
    if len(stem) >= 4 and name and (stem in name or name in stem):
        return True
    return len(stem) >= 4 and stem.replace(" ", "") in aumid.replace(" ", "")


class NotificationWatcher(QObject):
    """Belirli aralıklarla bildirimleri sayar. Sorgu arka plan iş parçacığında çalışır."""

    counts = Signal(list)   # [(uygulama adı, uygulama kimliği, sayı), ...] — hepsi küçük harf
    denied = Signal()       # kullanıcı izin vermedi

    def __init__(self, interval_ms=6000):
        super().__init__()
        self._timer = QTimer(self, interval=interval_ms, timeout=self.poll)
        self._busy = False
        self._ask = False

    def start(self, ask_permission=False):
        """ask_permission: izin yoksa Windows'un izin penceresini göster (kullanıcı özelliği açtığında)."""
        if not AVAILABLE:
            return
        self._ask = ask_permission
        self._timer.start()
        self.poll()

    def stop(self):
        self._timer.stop()
        self.counts.emit([])

    def poll(self):
        if self._busy or not AVAILABLE:
            return
        self._busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            result = asyncio.run(self._fetch())
            if result is None:
                self.denied.emit()
            else:
                self.counts.emit(result)
        except Exception:  # noqa: BLE001 - bildirim sayısı kritik değil; bir sonraki turda yeniden dene
            pass
        finally:
            self._busy = False

    async def _fetch(self):
        listener = UserNotificationListener.current
        status = listener.get_access_status()
        if status != UserNotificationListenerAccessStatus.ALLOWED and self._ask:
            self._ask = False
            status = await listener.request_access_async()
        if status != UserNotificationListenerAccessStatus.ALLOWED:
            return None
        totals = {}
        for n in await listener.get_notifications_async(NotificationKinds.TOAST):
            try:
                info = n.app_info
                key = ((info.display_info.display_name or "").lower(), (info.app_user_model_id or "").lower())
            except Exception:  # noqa: BLE001 - bazı bildirimlerin uygulama bilgisi okunamıyor
                continue
            totals[key] = totals.get(key, 0) + 1
        return [(name, aumid, c) for (name, aumid), c in totals.items()]
