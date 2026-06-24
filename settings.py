"""Uygulama genel ayarlari ve varsayilan esik degerleri."""

# Veritabani dosyasi (data klasoru altinda)
DB_PATH = "data/cache.sqlite"

# mynet canli borsa sayfasi (sembol listesi + gunluk snapshot kaynagi)
MYNET_URL = "https://finans.mynet.com/borsa/canliborsa/"

# Yahoo Finance icin BIST sembol soneki
YAHOO_SUFFIX = ".IS"

# Ilk indirmede kac yillik gecmis cekilecek
BACKFILL_PERIOD = "2y"

# Donem secenekleri: etiket -> islem gunu sayisi (yaklasik)
PERIODS = {
    "1 Ay": 21,
    "2 Ay": 42,
    "3 Ay": 63,
    "4 Ay": 84,
    "5 Ay": 105,
    "6 Ay": 126,
    "1 Yil": 252,
}

# Toparlanma (son zamanda yukselme) penceresi secenekleri: etiket -> gun
RECOVERY_WINDOWS = {
    "Son 2 Gun": 2,
    "Son 3 Gun": 3,
    "Son 5 Gun": 5,
}

# --- Dipten Donus varsayilan esikleri ---
DEFAULT_DECLINE_PCT = 15.0        # Trend yontemi: donemde en az bu kadar % dusus
DEFAULT_DOWN_DAY_RATIO = 0.55     # Kati yontem: dusus gunlerinin en az bu orani
                                  # (uzun donemde %60+ neredeyse hic gorulmez)

# --- Hacim/Fiyat taramasi varsayilanlari ---
DEFAULT_VOLUME_WINDOW = 3         # Son kac gune bakilacak
DEFAULT_VOLUME_MULTIPLE = 1.5     # Hacim, 20 gunluk ortalamanin bu kati uzerinde olmali

# Hareketli ortalama pencereleri
SMA_SHORT = 20
SMA_LONG = 50

# Veri "bayat" sayilma esigi (gun) - bundan eskiyse uyari gosterilir
STALE_DAYS = 4
