# BIST Hisse Tarama

Borsa İstanbul hisselerini tarayan basit bir Streamlit uygulaması:

- **Dipten Dönüş:** Uzun süredir düşüp son günlerde toparlamaya başlayan hisseler
- **Hacim / Fiyat:** Hacim artarken fiyatı düşen hisseler
- **Tüm Hisseler:** Anlık Son / Fark% / Hacim tablosu
- **Devre Dışı:** İstenmeyen hisseleri gizleme

## Veri kaynakları

- Hisse listesi + anlık fiyatlar: **mynet canlı borsa**
- Geçmiş günlük veriler (düzeltilmiş fiyat): **Yahoo Finance** (`yfinance`)

Veriler gün sonu (EOD) bazlıdır. Bedelsiz/bölünme etkileri düzeltilmiş fiyatla
otomatik düzeltilir.

## Çalıştırma

### İnternette (Streamlit Community Cloud)
Ana dosya: `app.py`. Depo bağlandığında otomatik çalışır.

### Yerelde (Windows)
`calistir.bat` dosyasına çift tıklayın (Python 3.11 + `requirements.txt` gerekir).

```
pip install -r requirements.txt
streamlit run app.py
```
