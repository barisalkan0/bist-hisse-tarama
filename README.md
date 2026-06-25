# BIST Hisse Tarama

Borsa İstanbul hisselerini tarayan basit bir Streamlit uygulaması:

- **Dipten Dönüş:** Uzun süredir düşüp son günlerde toparlamaya başlayan hisseler
- **Hacim / Fiyat:** Hacim artarken fiyatı düşen hisseler
- **Tüm Hisseler:** Anlık Son / Fark% / Hacim tablosu
- **Devre Dışı:** İstenmeyen hisseleri gizleme

## Veri kaynakları

- Hisse listesi + isimler: **mynet canlı borsa**
- Geçmiş veriler (düzeltilmiş kapanış + TL ciro): **İş Yatırım** (`HGDG_KAPANIS` / `HGDG_HACIM`)

Veriler gün sonu (EOD) bazlıdır. Bedelsiz/bölünme etkileri İş Yatırım'ın BİST-uyumlu
**düzeltilmiş** serisiyle otomatik giderilir (Yahoo BİST'te bunu yapmadığı için bırakıldı).

## Çalıştırma

### İnternette (Streamlit Community Cloud)
Ana dosya: `app.py`. Depo bağlandığında otomatik çalışır.

### Yerelde (Windows)
`calistir.bat` dosyasına çift tıklayın (Python 3.11 + `requirements.txt` gerekir).

```
pip install -r requirements.txt
streamlit run app.py
```
