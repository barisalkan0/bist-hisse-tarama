"""
BIST sembol evreni + gunluk snapshot kaynagi.

mynet 'canli borsa' sayfasi, tum hisselerin anlik verisini sayfa HTML'i icinde
boru ( | ) ile ayrilmis bir blok olarak server-side gomulu sunuyor. Bu yuzden
JS/websocket'e gerek kalmadan tek bir HTTP istegiyle ~600 hissenin
Son / Fark% / Hacim degerleri ve sembol listesi alinabiliyor.

Her kaydin yapisi (A1CAP ornegi uzerinden cozuldu):
  Son | Yuksek | Dusuk | Fark% | Saat | bayrak | bayrak | Alis | Satis | AOF |
  HacimLot | HacimTL | SEMBOL | ad | hisseler/slug/ | ...
Ticker hemen ardindan gelen `|...|hisseler/slug/` ile sabitlenir; sembolden
onceki 12 alan sayisal veriyi verir.
"""
import re
import requests

import settings

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Sembol + slug capa: tum evreni guvenilir sekilde bulur (~600 kayit)
_TICKER_RE = re.compile(r"\|([A-Z][A-Z0-9]{1,5})\|([^|]*)\|hisseler/([a-z0-9\-]+)/")


def _tr_float(s):
    """Turkce sayi formatini ('1.234,56') float'a cevirir. Bos ise None."""
    s = (s or "").strip()
    if not s or s in ("-", "*null*", "null"):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _tr_int(s):
    f = _tr_float(s)
    return int(f) if f is not None else None


def _name_from_slug(ticker, slug):
    """'a1cap-a1-capital-yatirim' -> 'A1 Capital Yatirim' (sembolu basindan atar)."""
    parts = slug.split("-")
    if parts and parts[0].lower() == ticker.lower():
        parts = parts[1:]
    name = " ".join(p.capitalize() for p in parts)
    return name or ticker


def fetch_universe(timeout=20):
    """
    mynet'ten tum hisseleri ceker.

    Donen: list[dict] -> her biri:
      symbol, name, yahoo, son, fark, yuksek, dusuk, alis, satis, aof,
      hacim_lot, hacim_tl, saat
    Hata olursa istisna firlatir (cagiran taraf yakalar, snapshot opsiyoneldir).
    """
    resp = requests.get(settings.MYNET_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    html = resp.text

    rows = []
    seen = set()
    for m in _TICKER_RE.finditer(html):
        ticker = m.group(1)
        slug = m.group(3)
        if ticker in seen:
            continue
        # Sembolden onceki metni boru ile bol, son 12 alani sayisal veri olarak al
        prefix = html[: m.start()]
        fields = prefix.split("|")[-12:]
        if len(fields) < 12:
            continue
        son, yuksek, dusuk, fark, saat, _f1, _f2, alis, satis, aof, hlot, htl = fields
        seen.add(ticker)
        rows.append(
            {
                "symbol": ticker,
                "name": _name_from_slug(ticker, slug),
                "yahoo": ticker + settings.YAHOO_SUFFIX,
                "son": _tr_float(son),
                "yuksek": _tr_float(yuksek),
                "dusuk": _tr_float(dusuk),
                "fark": _tr_float(fark),
                "saat": saat.strip() if re.match(r"^\d{2}:\d{2}$", saat.strip()) else None,
                "alis": _tr_float(alis),
                "satis": _tr_float(satis),
                "aof": _tr_float(aof),
                "hacim_lot": _tr_int(hlot),
                "hacim_tl": _tr_float(htl),
            }
        )
    return rows


def fetch_symbols():
    """Sadece sembol listesini doner (yedek amacli, snapshot gerekmiyorsa)."""
    return [r["symbol"] for r in fetch_universe()]


if __name__ == "__main__":
    u = fetch_universe()
    print(f"Toplam hisse: {len(u)}")
    for r in u[:5]:
        print(r)
    g = [r for r in u if r["symbol"] == "GOODY"]
    print("GOODY:", g[0] if g else "bulunamadi")
