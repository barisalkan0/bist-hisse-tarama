# Claude Proje Notu

Bu proje BIST hisseleri için Streamlit tabanlı tarama ve radar uygulamasıdır. Akıllı Radar katmanı al/sat tavsiyesi vermez; fiyat, düzeltilmiş kapanış ve TL ciro geçmişinden 5-10 iş günlük karar destek sinyali üretir.

## Veri Kaynakları

- Günlük fiyat/ciro: İş Yatırım `HisseTekil` endpoint'i.
- `adj_close`: İş Yatırım `HGDG_KAPANIS`; bedelsiz/bölünme etkilerine karşı düzeltilmiş kapanış kabul edilir.
- `volume`: İş Yatırım `HGDG_HACIM`; uygulamada TL ciro gibi kullanılır.
- Sembol/snapshot: Mynet canlı borsa sayfası.
- Mevsimsellik: aynı günlük kaynak 15 yıllık aylık veriye indirgenir.

Önemli ayarlar:

- `settings.BACKFILL_YEARS = 15`
- `settings.MONTHLY_YEARS = 15`
- Normal güncelleme kısa pencereyle eksik günleri tamamlar.
- Sidebar `ML veri bakımı > Uzun geçmişi yenile` tam günlük ve aylık geçmişi yeniden çeker.

## ML Radar

Aktif model sürümü:

- `absolute_upside_v4`

Ana hedef:

- 5 iş günü sonra en az `+2%` yükseliş: `y_up_5`
- 10 iş günü sonra en az `+3%` yükseliş: `y_up_10`

Yardımcı hedef:

- Aynı gün BIST evreninde üst yüzde 30 göreli performansa girme: `y_5`, `y_10`

Model tipi:

- `scikit-learn` `HistGradientBoostingClassifier`
- Tek sınıflı fold güvenliği için `DummyClassifier` fallback'i var.

Canlı uygulama eğitim yapmaz. Sadece `ml_signals/model.joblib` dosyasını yükleyip skor üretir.

## Feature Set

Temel fiyat/hacim feature'ları:

- kısa/orta vade getiriler: `ret_1`, `ret_3`, `ret_5`, `ret_10`, `ret_20`, `ret_60`
- ciro oranları: `vol_ratio_2_20`, `vol_ratio_5_20`, `vol_ratio_10_20`
- volatilite: `volatility_10`, `volatility_20`, `volatility_60`, `volatility_ratio_20_60`
- trend: `sma20_gap`, `sma50_gap`, `sma20_slope_5`
- dip/zirve: `drawdown_60`, `drawdown_252`, `low_distance_60`

Profesyonel güven/risk feature'ları:

- `history_days`, `history_years`
- `turnover_ma20`, `turnover_ma20_log`, `turnover_ma60_log`
- `turnover_stability_20_60`
- `price_range_20`
- `quiet_volume_pressure`
- `seasonality_mean`, `seasonality_hit`, `seasonality_years`

Mevsimsellik feature'ı sızıntısızdır: her gün için sadece o tarihten önce tamamlanmış aylık getirileri kullanır.

## Radar UI

Akıllı Radar sekmesi şunları gösterir:

- `Yükseliş Puanı`: 5G ve 10G mutlak yükseliş olasılığı ortalaması.
- `Göreli Güç`: BIST evrenine göre güçlü kalma yardımcı skoru.
- `Güven`: model skoru + veri/likidite temkin düzeltmesi.
- `Veri Güveni`: hisse geçmişi uzunluğuna göre.
- `Likidite`: 20 günlük ortalama TL ciroya göre.
- `Trend`: SMA ve momentum davranışına göre.
- `Hacim`: son hacim/ciro teyidine göre.

Güçlü aday olmak için yalnızca puan yetmez; yeterli geçmiş ve minimum likidite de gerekir.

## Sonuçlar Hafızası

`ml_radar_snapshot`:

- Günlük radar kararını saklar.
- Primary key: `(data_date, symbol, model_kind)`
- Aynı kapanış tarihi ve model sürümü için ikinci snapshot yazılmaz.

`ml_radar_outcome`:

- 5 ve 10 iş günü dolunca sonucu saklar.
- Getiri, en yüksek/en düşük vade içi hareket, başarı etiketi, sinyal anındaki neden/risk ve skorları içerir.
- Bu tablo gelecekte model kalitesinin hafızasıdır.

## Eğitim ve Doğrulama Komutları

Modeli yeniden eğit:

```powershell
cd "C:\Users\asus\OneDrive\Masaüstü\Şahin\hisse-takip"
python -B -m ml_signals.train
```

Testleri çalıştır:

```powershell
python -B -m unittest discover -v
```

Streamlit:

```powershell
streamlit run app.py
```

## Son Uzun Veri Eğitimi

Uzun günlük cache yenilendi:

- Günlük fiyat aralığı: `2011-06-27` - `2026-06-26`
- Günlük satır: yaklaşık `1.546M`
- Sembol: `611`
- Aylık aralık: `2011-06-30` - `2026-06-30`

`absolute_upside_v4` backtest sonucu:

- Backtest: geçti
- Top20 10G ortalama mutlak getiri: `+2.30%`
- Top20 10G göreli getiri: `+0.79%`
- Momentum baseline: `+3.55%`
- Hacim baseline: `+0.45%`
- Sıkışma baseline: `+0.80%`
- Baseline geçme sayısı: `2`

Dürüst not: uzun veriyle salt momentum baseline, ML skorundan daha yüksek çıktı. Bu nedenle radar ekranı "kusursuz tahmin" gibi sunulmamalı. ML katmanı hacim, mevsimsellik, likidite, veri yaşı ve risk açıklamasıyla karar destek sağlar. Gelecekte `Sonuçlar` hafızası büyüdükçe kalibrasyon ve model seçim kriterleri sıkılaştırılmalıdır.

## Dikkat Edilecekler

- Finansal tavsiye dili kullanma; "aday", "izle", "risk" dili korunmalı.
- Random train/test split kullanma; zaman sıralı walk-forward yaklaşımı korunmalı.
- Feature tarafına gelecek veri sızdırma.
- Model sürümü değişince `MODEL_KIND` artırılmalı; aksi halde eski snapshot yeni modelle karışabilir.
- Lokal SQLite nihai kalıcı sistem değildir. Ürünleşmede PostgreSQL/Supabase/Neon + backup gerekir.
