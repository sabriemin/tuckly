# Tuckly

Windows için Fences tarzı masaüstü düzenleyici (Python + PySide6). Görünüşü Nectar dock'unun
tasarım diline uygun: koyu cam kartlar, yuvarlak simge karoları, gruplanmış ayar satırları.

## Başlatma
- `calistir.bat` dosyasına çift tıklayın (PySide6 yoksa kurar), ya da
- `exe_olustur.bat` ile tek dosyalık `dist\Tuckly.exe` oluşturun.
- Uygulama zaten açıkken tekrar başlatırsanız kontrol paneli öne gelir.

## Nasıl çalışır
- **Dosyalar masaüstünde kalır.** Kartlar onları yalnızca gruplayıp gösterir; uygulamadan
  çıkınca masaüstünüz olduğu gibidir.
- Masaüstünden bir dosyayı karta sürükleyin: o karta yerleşir (dosya taşınmaz).
  Başka bir klasörden sürüklerseniz dosya masaüstüne alınır ve karta yerleşir (Ctrl: kopyala).
- **Klasör kartı:** Kontrol panelinden "Klasörü kart olarak ekle" ile herhangi bir klasörü
  gösterebilirsiniz; bu karta bırakılan dosyalar o klasöre taşınır.
- **Diğer kartı:** "Masaüstü simgelerini gizle" açıkken, hiçbir karta yerleşmemiş öğeleri gösterir.

## Kart üzerinde
- ⚙ düğmesi: ad, tema, opaklık, simge boyutu, uzantı kuralları, kartı kaldırma.
- ⌄ düğmesi veya başlığa çift tık: daralt / genişlet.
- Başlıktan sürükleyerek taşıyın, sağ alt köşeden boyutlandırın.
- Dosyaya sağ tık: aç, konumunu göster, yeniden adlandır, karttan çıkar, Geri Dönüşüm Kutusu.

## Kontrol paneli (tepsi simgesine tıklayın)
- **Kartlar:** tüm kartları seçip düzenleyin, yeni kart ekleyin.
- **Masaüstünü düzenle:** kartsız dosyaları kurallara göre listeler; seçtiklerinizi kartlara
  yerleştirir. "Son düzenlemeyi geri al" ile geri alınır. Hiçbir dosya taşınmaz.
- **Seçenekler:** otomatik düzenleme, masaüstü simgelerini gizleme, kartları kilitleme,
  Windows ile başlatma.

Ayarlar: `%APPDATA%\MasaustuKutulari\ayarlar.json`
