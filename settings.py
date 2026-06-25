"""Uygulama genel ayarlari ve varsayilan esik degerleri."""

# Calisma veritabani (yazilabilir; commit EDILMEZ, .gitignore'da)
DB_PATH = "data/cache.sqlite"
# Salt-okunur tohum (seed) veritabani - repoda durur, calisma kopyasi bundan uretilir.
# Uygulama bu dosyaya ASLA yazmaz (bulutta git pull ile cakisip bozulmasin diye).
SEED_PATH = "data/seed.sqlite"

# mynet canli borsa sayfasi (sembol listesi + isimler kaynagi)
MYNET_URL = "https://finans.mynet.com/borsa/canliborsa/"

# Gecmis veri kaynagi: Is Yatirim (BIST-uyumlu DUZELTILMIS kapanis + TL ciro).
# HGDG_KAPANIS = duzeltilmis kapanis (bedelsiz/bolunme yansitilmis), HGDG_HACIM = TL ciro.
# NOT: Yahoo BIST'te bedelsizi DUZELTMEDIGI icin birakildi (sahte cokus/sicrama uretiyordu).
ISYATIRIM_URL = (
    "https://www.isyatirim.com.tr/_layouts/15/"
    "IsYatirim.Website/Common/Data.aspx/HisseTekil"
)

# Gunluk backfill derinligi (yil) ve mevsimsellik icin aylik gecmis derinligi (yil)
BACKFILL_YEARS = 2
MONTHLY_YEARS = 15

# Donem secenekleri: etiket -> islem gunu sayisi (yaklasik)
PERIODS = {
    "1 Ay": 21,
    "2 Ay": 42,
    "3 Ay": 63,
    "4 Ay": 84,
    "5 Ay": 105,
    "6 Ay": 126,
    "1 Yıl": 252,
}

# Toparlanma (son zamanda yukselme) penceresi secenekleri: etiket -> gun
RECOVERY_WINDOWS = {
    "Son 2 Gün": 2,
    "Son 3 Gün": 3,
    "Son 5 Gün": 5,
    "Son 7 Gün": 7,
    "Son 10 Gün": 10,
    "Son 15 Gün": 15,
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

# Veri "bayat" sayilma esigi (IS GUNU) - bundan fazla geride ise uyari gosterilir.
# Is gunu bazli oldugu icin hafta sonu/tatil yanlis uyari vermez.
STALE_DAYS = 3
