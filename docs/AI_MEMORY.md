# AI Memory

Last updated: 2026-07-02
Security risk level: high-risk
MCP project id: `C-Users-asus-OneDrive-Masa-st-ahin-hisse-takip`

## Project Purpose
- Streamlit app for BIST stock screening and ML-assisted radar signals.
- Current product language must remain decision-support only: candidate, watch, risk, follow-up; never buy/sell/investment advice.
- Freemium model: screener tabs free for everyone; Akıllı Radar (Pro), Notlar (login), Favoriler (login).
- Public launch planned soon with Supabase auth + subscription + payment.

## Stack
- Python 3.11, Streamlit, pandas, numpy, plotly, requests, scikit-learn, joblib, supabase>=2.0.
- Local runtime data uses SQLite: `data/cache.sqlite` generated from committed read-only `data/seed.sqlite`.
- Optional persistent cloud store uses Upstash Redis REST for blacklist/favorites/notes (legacy, being superseded by Supabase).
- ML radar uses `ml_signals/model.joblib` and model kind `absolute_upside_v4`.
- Auth and subscription: `data/supabase_store.py` — requires `SUPABASE_URL` + `SUPABASE_ANON_KEY` secrets.

## Current Architecture
- `app.py` is the Streamlit UI and orchestration layer.
- `data/cache.py` manages local SQLite cache, snapshot, favorites, notes, settings, and ML radar persistence tables.
- `data/fetch.py` pulls adjusted EOD price/turnover history from Is Yatirim.
- `data/universe.py` pulls live symbol/snapshot data from Mynet.
- `data/store.py` optionally syncs blacklist/favorites/notes to Upstash Redis (legacy).
- `data/supabase_store.py` NEW: Supabase auth (login/logout), subscription check (is_pro).
- `screeners/` contains rule-based scans: dip dönüş, hacim/fiyat, 52 hafta, mevsimsellik, sessizlik/hareketlenme.
- `ml_signals/` contains feature generation, labels, training, prediction, radar classification, daily snapshots, and outcome tracking.
- `tests/test_ml_signals.py` covers ML feature leakage, labels, missing model behavior, radar text, snapshot/outcome behavior.
- `supabase/schema.sql` NEW: SQL to run in Supabase SQL Editor to create subscriptions/notes/favorites/blacklist tables.

## Auth + Subscription Gate (Updated 2026-06-29)
- Sidebar shows login form + signup form when Supabase is configured and user is not logged in.
- Radar tab AND Favoriler/Notlar/Devre Dışı: ALL gated behind `is_pro()` (Pro-only). Free/anonymous users do not see favorite/note/blacklist UI at all.
- `is_pro()` computed once per render via `_is_pro_now()` helper in app.py, cached in `st.session_state["_pro_now"]`; cache cleared on login/logout.
- If Supabase is NOT configured (SUPABASE_URL / SUPABASE_ANON_KEY missing): app runs in anonymous mode — all tabs visible, backwards compatible with local dev.
- Data ops (favorites/notes/blacklist/is_pro) use direct Supabase REST API with JWT in Authorization header (NOT supabase-py set_session, which silently failed to authenticate PostgREST).
- ROOT CAUSE of earlier "favorites not saving" was deployment lag: REST rewrite existed only locally; live repo (last commit d9fc55f, 2026-06-28) still ran old set_session code.

## Per-user Data Layer (Implemented 2026-06-29)
- `data/supabase_store.py` has per-user CRUD: `fav_list/add/remove`, `note_all/set/delete`, `blacklist_list/add/remove`, `signup`.
- `app.py` has thin wrapper helpers (`_get_favs`, `_add_fav`, `_remove_fav`, `_get_notes`, `_set_note`, `_delete_note`, `_get_blacklist`, `_add_blacklist`, `_remove_blacklist`) that route to Supabase if user logged in, else fall back to local SQLite/Upstash.
- All call sites in `app.py` (render_table, _row_detail, _render_radar_tab, tabs) use these wrappers.
- Supabase tables used: `favorites(user_id, symbol)`, `notes(user_id, symbol, note_text, updated_at)`, `blacklist(user_id, symbol)` — all with RLS.

## Supabase DB Schema (supabase/schema.sql)
- `subscriptions(user_id, provider, provider_customer_id, provider_subscription_id, plan, status, current_period_end)` — provider-agnostic design.
- `notes(user_id, symbol, note_text)`, `favorites(user_id, symbol)`, `blacklist(user_id, symbol)` — all with RLS.
- `webhook_events(provider, event_name, event_hash UNIQUE, payload jsonb, received_at)` NEW (2026-07-01): idempotency + audit log for payment webhooks. RLS on, zero policies — only `service_role` (Edge Function) can touch it, same pattern as `subscriptions`. **Not yet created in the live Supabase project** — SQL is in the repo, needs to be run manually in SQL Editor.
- Manual subscription rows can be added via Supabase dashboard to test pro access.

## Data Pipeline + Persistence (VPS) (2026-06-29)
- Is Yatirim blocks foreign datacenter IPs (GitHub Actions Azure → ConnectTimeout, proven). Streamlit Cloud IP is allowed.
- A Turkish VPS (Istanbul) runs `scripts/refresh_data.py` daily via cron (weekdays 19:00 TRT): fetches EOD prices (+ monthly on days 1-5), updates SQLite, VACUUM+gzip, uploads to Supabase Storage bucket `market-data/cache.sqlite.gz`.
- Live app downloads that public asset on boot (`cache.py::_try_storage_download`) → falls back to committed seed on any failure. Keeps data fresh with no visits/logins.
- Storage write uses the **Supabase service_role key** stored ONLY in a root-only env file on the VPS (never in repo/logs). Reason: robot-account RLS write policy did not work in Storage context (auth.uid() unresolved); service_role bypasses RLS and is the standard backend approach.
- Storage bucket is public-READ (market data is non-sensitive); write is effectively service_role-only.

## Legal Pages (Aşama 2 — Implemented 2026-06-29, DRAFT)
- `legal/*.md`: disclaimer, terms, privacy (KVKK), pricing (aylık+yıllık), refunds (Model A cayma feragati). Loaded via `app.py::load_legal()` (Path-based, cloud-safe).
- Public ungated "📄 Bilgi & Yasal" tab renders them; global short disclaimer under hero every render.
- ALL DRAFT — lawyer review required before launch. SPK licensing question + VERBİS applicability flagged for Barış. Placeholders ([İŞLETME ADI], e-posta, VKN, fiyat tutarı, KDV) unfilled.

## Landing Site — valysera.com (Aşama 3, başladı 2026-06-29)
- Yeni ayrı proje: `../valysera-web` (Next.js 16 + Tailwind v4 + TypeScript, App Router). Python repo'ya dokunulmadı.
- Tier 0: uygulama Streamlit'te kalır (`hisse-tarama.streamlit.app`); landing tanıtır + linkler.
- Sayfalar: `/` (hero/özellikler/SSS/CTA), `/terms /privacy /refunds /pricing /disclaimer` (legal `content/legal/*.md`'den, react-markdown+gfm). Global disclaimer footer'da.
- Marka: indigo→sky gradyan, Inter — Streamlit ile tutarlı.
- ÖNEMLİ: `dev`/`build` script'leri `--webpack` (Turbopack, Türkçe yol Masaüstü/Şahin'de panik veriyor). Webpack build temiz (9 route static). Vercel'de sorun yok.
- ✅ CANLI (2026-06-29): https://valysera.com (+ www) Vercel'de yayında, HTTPS doğrulandı. Repo: github.com/barisalkan0/valysera-web (private). DNS Squarespace'te (A @ → 216.198.79.1, CNAME www → vercel-dns); e-posta yönlendirme (Mailgun MX/SPF/DKIM/DMARC) korundu, mail testi geçti.
- ✅ REDESIGN (2026-06-29): Claude Design "Valysera Hero" birebir port edildi (dark/elit). Hero =
  statik HTML+CSS (perspektif 3D ızgara, glassmorphism yüzen paneller, fare parallax, ambient bloom,
  seeded-RNG mum/radar/sparkline) → `src/components/Hero.tsx` (dangerouslySetInnerHTML, SSR-uyumlu).
  Türkçe nav (Özellikler/SSS/İletişim + Uygulamayı Aç). Yeni bölümler: Özellikler(6)/SSS/İletişim.
  Yasal sayfalar dark `LegalShell` + prose-invert. Fontlar Schibsted Grotesk + IBM Plex Mono (Google @import).
  Kaynak dosya: `valysera-web/design/Valysera Hero (standalone).html`. Push edildi → Vercel auto-deploy.
- ✅ CONVERSION OVERHAUL (2026-06-29, Codex brief): premium nav (Özellikler/Fiyatlandırma/SSS/Giriş/
  Kayıt Ol/Uygulamaya Git, mobil sadeleştirme vh-hide-sm). Yeni rotalar `/login` `/signup` (cilalı
  placeholder, AuthPlaceholder.tsx), `/fiyat`→`/pricing` (next.config redirect). Hero CTA "Hemen
  Kayıt Ol"→/signup + geçici "Uygulamaya Git"; mikro-değer satırı. Yeni bölümler: Neden Valysera(4),
  ML Radar + mock panel (tek kart satırlar, "demo veri" etiketli), Sonuç Takibi (demo sparkline).
  PricingComparison (Free vs Pro, check/cross) ana sayfa + yeniden tasarlanan /pricing. SSS 8 soru
  iddialı+uyumlu. İletişim rafine (e-posta link). UYUM: "Canlı veri akışı"→"Gün sonu"; tüm mock'lar
  demo etiketli; kâr/garanti ifadesi YOK (grep doğrulandı). Commit 681ea5b.

## Payment — Lemon Squeezy, 3-tier pricing (In Progress, 2026-07-01)
- Provider: **Lemon Squeezy**. Store currently shows **"not activated"** (identity/business review pending on Lemon Squeezy's side) — blocks real end-to-end checkout testing, does not block code/deploy work.
- **3 paid tiers** (revised from an initial single "Pro" plan after user feedback that Free vs entry-tier felt too similar): **Basic $9/mo**, **Premium $19/mo ("En Popüler")**, **Studio $45/mo**. Yearly option = monthly × 9 (25% off, framed as "12 ay yerine 9 ay öde"). Feature matrix (11 rows, fixed order across all 4 cards) lives in `valysera-web/src/components/PricingComparison.tsx`.
- `data/supabase_store.py`: tier hierarchy `free < basic < premium < studio` via `current_tier()` / `has_tier()`. `is_pro()` kept for backward compat (= `has_tier(..., "basic")`, i.e. any paid tier). Radar/Favoriler/Notlar gating in `app.py` unchanged (all paid tiers, Basic included, get everything except Premium/Studio-only extras like Telegram — see roadmap note below).
- **Checkout moved out of Streamlit**: `data/lemonsqueezy_store.py::pricing_url()` now just builds a link to `valysera.com/pricing?uid=<user_id>&email=<email>` (sidebar button "💎 Planları Gör"). The actual 6 checkout links (3 tiers × monthly/yearly) are built client-side in valysera-web's `/pricing` page from `NEXT_PUBLIC_LEMONSQUEEZY_STORE_SLUG` + `NEXT_PUBLIC_LEMONSQUEEZY_VARIANT_ID_{BASIC,PREMIUM,STUDIO}_{MONTHLY,YEARLY}` env vars, reading `uid`/`email` from the URL query string to prefill `checkout[custom][user_id]`/`checkout[email]`.
- Webhook receiver: `supabase/functions/lemonsqueezy-webhook/index.ts` — **DEPLOYED and ACTIVE** (2026-07-01, `--no-verify-jwt`, function id `0b4e2e2b-1a76-4caf-b45d-1d2893b9fe6c`). Verifies `X-Signature` (HMAC-SHA256 over raw body) against `LEMONSQUEEZY_WEBHOOK_SECRET`, logs every event to `webhook_events` (idempotency via `event_hash` UNIQUE), maps `payload.data.attributes.variant_id` → tier via `LEMONSQUEEZY_VARIANT_ID_*` secrets, and upserts `subscriptions`. **`LEMONSQUEEZY_WEBHOOK_SECRET` and all 6 `LEMONSQUEEZY_VARIANT_ID_*` secrets are NOT YET SET** on the function (nothing to configure with until Barış creates the Premium/Studio products + yearly variants in Lemon Squeezy and the store is activated) — until then the function fails closed (missing secret → HTTP 500; unmapped variant → logs a warning and skips the DB write, does not guess a tier).
- Supports 8 events: `subscription_created/updated/cancelled/expired/paused/unpaused/payment_success/payment_failed`. Key product decision: `subscription_cancelled` intentionally keeps `status='active'` (Lemon Squeezy semantics: still valid until `ends_at`) — `is_pro()`/`current_tier()` already check `current_period_end`, so no extra code needed for graceful downgrade at period end.
- **ROADMAP — promised on the pricing page but not built yet:** Telegram notifications (Premium+, labeled "(yeni)") and team-shared favorite lists (Studio, labeled "(yakında)"). See `[[bist-hisse-tarama-projesi]]` project memory for details — these are real sales promises now, should be prioritized.
- REMAINING: Barış creates Premium/Studio Lemon Squeezy products (+ yearly variant for all 3 tiers) once the store is activated → shares 6 variant IDs → Claude sets them as Supabase secrets + Vercel `NEXT_PUBLIC_LEMONSQUEEZY_*` env vars → Barış adds the webhook in Lemon Squeezy dashboard (URL from the deployed function, 8 events) → shares the signing secret → Claude sets `LEMONSQUEEZY_WEBHOOK_SECRET` → end-to-end test via Lemon Squeezy "Simulate event" → switch to Live mode before real launch.

## Akıllı Radar — Bekletme + Tarih Etiketleme Düzeltmesi (2026-07-01)
Kullanıcı iki şikayet bildirdi: (1) login'de 612 hissenin verisi çekilirken bekletiliyor, Radar'ın
günde 1 kez merkezi hesaplanmasını istiyor; (2) Radar tablosunda "bugün 1 Temmuz ama 5 günlük
sonuç 8 Temmuz görünüyor, saçma" dedi. 3 paralel Explore ajanıyla araştırıldı, sonra düzeltildi:

- **Tarih hesaplaması BUG DEĞİLDİ** — matematiksel olarak doğrulandı (`data_date`=2026-07-01 baz
  alınarak `pandas.bdate_range` ile 5/10 iş günü ileri gidiliyor, 08.07/15.07 tam olarak doğru).
  Asıl sorun etiketlemeydi: "5G/10G Sonuç Günü" adı "sonuç zaten oldu" izlenimi veriyordu, oysa bu
  henüz gerçekleşmemiş bir HEDEF tarihti. **Düzeltme:** sütun adları "5G/10G Hedef Tarih" oldu
  (`ml_signals/radar.py` DISPLAY_COLUMNS, `ml_signals/daily.py::_with_result_dates`/`_display`),
  `app.py::render_radar_table`'a `column_config` ile "henüz gerçekleşmedi" açıklaması eklendi.
- **612 hisse bekletmesinin gerçek kaynağı Radar DEĞİLDİ** — `app.py::_auto_catchup` (günlük fiyat
  senkronizasyonu, "maintainer" yorumuna rağmen gerçek bir yetki kontrolü yoktu, günün ilk giren
  HERHANGİ bir kullanıcısını ~1 dk bekletebiliyordu). VPS cron zaten günlük veriyi Storage'a
  yüklüyor; bu senkron/bekletici kod **tamamen kaldırıldı**. Manuel "🔄 Verileri Güncelle" butonu
  (opt-in) ve bayatlık uyarısı (`business_days_behind`) korundu.
- **Radar hesaplaması zaten büyük ölçüde paylaşımlıydı** (`ml_radar_snapshot` PK
  `data_date+symbol+model_kind`, `INSERT OR IGNORE` dedup) ama VPS bunu hiç tetiklemiyordu — ilk
  Streamlit kullanıcısı günün ilk `score_latest()` çağrısını (tüm evren, ~600 sembol) yapıyordu.
  **Düzeltme:** `scripts/refresh_data.py`'ye Storage upload'dan ÖNCE `ml_daily.today_radar(...)`
  precompute adımı eklendi (`ml_signals/` tamamen Streamlit-bağımsız olduğu için kod tekrarı
  gerekmedi) — artık VPS günde 1 kez hesaplıyor, hiçbir Streamlit kullanıcısı ilk-hesaplama
  tetiklemiyor (mevcut dedup sayesinde `app.py` tarafında kod değişikliği gerekmedi).
- **Küçük ek optimizasyon:** `ml_signals/daily.py::_append_watch_symbols` (bir kullanıcının o
  günün listesinde olmayan favorisini eklerken) artık TÜM evreni değil sadece eksik sembol(ler)i
  skorluyor (`score_latest`'e daraltılmış `data` dict veriliyor) — her sembolün özellikleri kendi
  geçmişinden bağımsız hesaplandığı için (çapraz-sembol bağımlılık yok) sonuç aynı, sadece hızlı.
- **Testler (kullanıcı unit+integration açıkça istedi):** 3 yeni test eklendi, mevcutlarla birlikte
  11/11 yeşil: `test_target_date_is_independent_of_wall_clock` (tarih hesabının `datetime.now()`'a
  bağlı olmadığının regresyon kanıtı), `test_append_watch_symbols_only_scores_missing_subset`
  (optimizasyonun `score_latest`'i sadece eksik sembolle çağırdığının spy testi),
  `RadarPipelineIntegrationTest::test_vps_precompute_then_user_visit_does_not_rescore` (repoda
  İLK integration test — gerçek model + `data.cache.connect()` bellek-içi DB'ye patch'lenerek VPS
  precompute → kullanıcı ziyareti → favori ekleme akışının uçtan uca, gerçek yeniden hesaplama
  yapmadan çalıştığını kanıtlıyor).

## Login Duvarı + Oturum Kalıcılığı + Tier Metni (2026-07-02)
Kullanıcı 3 şey daha istedi: (1) kayıt olmadan uygulamanın HİÇ kullanılamaması (önceden temel
taramalar herkese açıktı), (2) F5'te oturumun düşmemesi, (3) manuel verilen üst-katman
aboneliğin sabit "Pro" değil gerçek tier adıyla ("Profesyonel" vb.) görünmesi.

- **Login duvarı:** `app.py`'de `st.tabs(...)`'dan hemen önce bir kapı — Supabase yapılandırılmışsa
  ve kullanıcı giriş yapmamışsa hiçbir sekme render edilmiyor, sadece "kayıt ol/giriş yap" mesajı +
  Bilgi & Yasal içeriği gösterilip `st.stop()` ile durduruluyor. Yerel geliştirmede (secrets yoksa)
  davranış değişmedi.
- **F5 oturum kalıcılığı — `extra-streamlit-components` yeni bağımlılık:** `CookieManager` ile
  `refresh_token` bir tarayıcı cookie'sinde (`sb_refresh`, ~30 gün) tutuluyor, sayfa açılışında
  `data/supabase_store.py::restore_session()` ile oturum yenileniyor. **Önemli tuzak (bulunup
  düzeltildi):** `CookieManager` ilk denemede `st.cache_resource` ile önbelleklenmişti — bu YANLIŞ,
  çünkü nesne çerezleri sadece `__init__`'te okuyor ve `st.cache_resource` TÜM kullanıcılar arasında
  paylaşılıyor (nesne donup kalıyor + teorik kullanıcılar-arası veri karışması riski). Düzeltme:
  önbellekleme kaldırıldı, her rerun'da taze nesne oluşturuluyor. Login sonrası `st.rerun()`'dan
  önce `time.sleep(0.5)` eklendi (cookie yazma talimatının tarayıcıya ulaşması için — bu süre
  olmadan bazı denemelerde cookie hiç yazılmamış gibi davranıyordu).
- **Tier-duyarlı metin:** Sidebar artık `current_tier()`'ı çağırıp `st.session_state["_tier_now"]`'da
  önbellekliyor; caption `TIER_DISPLAY_NAMES` eşlemesiyle ("basic"→"Başlangıç", "premium"→"Premium",
  "studio"→"Profesyonel") gösteriliyor.
- Kullanıcı tarafından yerelde (`streamlit run app.py`, localhost:8501) elle test edildi: giriş→F5→
  oturum korunuyor, çıkış→F5→login formuna düşüyor, giriş yapmadan sekmeler görünmüyor, tier metni
  doğru gösteriliyor. Detay: `docs/SECURITY_NOTES.md`.

## Current Verification
- `python -B -m unittest discover -v` passed on 2026-06-29: 8 tests OK.
- `python -B -m unittest discover -v` passed on 2026-07-01 (after Radar fix): **11/11 tests OK**
  (8 eski + 3 yeni, bkz. yukarıdaki "Akıllı Radar" bölümü).
- `python -B -c "import ast; ast.parse(open('app.py').read())"` — syntax OK.
- MCP index status is ready, file-tree level coverage.
- Static review confirmed note-card HTML escapes user note text before `unsafe_allow_html=True` rendering.

## Active Work / Next Steps
1. ✅ Supabase auth + per-user favorites/notes/blacklist live; Pro-only gating for those features.
2. ✅ Automatic daily data pipeline live (Turkish VPS cron → Supabase Storage → app downloads).
   **2026-07-01'de genişletildi:** VPS artık Akıllı Radar'ı da günde 1 kez precompute ediyor
   (bkz. "Akıllı Radar" bölümü) — hem fiyat hem radar verisi tek gzip'te, tek pipeline'da.
3. ✅ Marka/landing sitesi CANLI: valysera.com (Next.js+Vercel, ayrı repo `valysera-web`), conversion
   yapısı + dark/elit hero + yasal sayfalar + /login /signup placeholder + /pricing. Uygulama Tier 0:
   hâlâ Streamlit'te, landing'den linklenir (`SITE.appUrl`, tek satırda değişir).
4. Aşama 4 = ödeme entegrasyonu **İLERLEDİ (2026-07-01)**: sağlayıcı Lemon Squeezy, 3 katmanlı
   fiyatlandırma (Başlangıç $9 / Premium $19 / Profesyonel $45 + yıllık %25 indirim, tier isimleri
   Türkçe — iç `plan` değerleri `basic/premium/studio` aynen kalıyor). Checkout valysera-web
   `/pricing`'te; webhook Edge Function **deploy edildi (ACTIVE)**; `webhook_events` tablosu
   canlıda; **6 gerçek Lemon Squeezy varyant ID'si Supabase secrets + Vercel env'e işlendi**
   (Barış'tan geldi: Basic 1859221/1859852, Premium 1859858/1859863, Studio 1859864/1859867).
   Her iki repo push edildi (hisse-takip `9d25f0e`, valysera-web `835ee6c`).
   SIRADAKI: `LEMONSQUEEZY_WEBHOOK_SECRET` hâlâ eksik — Barış mağaza aktive olunca Lemon
   Squeezy'de webhook'u ekleyip signing secret'ı paylaşacak → Claude Supabase'e set edecek →
   Lemon Squeezy "Simulate event" ile uçtan uca test → Live mode.
5. SIRADAKI (henüz YOK): (a) yasal placeholder'ları doldur + hukukçu + SPK/VERBİS kontrolü;
   (b) Telegram bildirimleri + takım paylaşımlı favoriler (pricing sayfasında vaat edildi, kodu
   henüz yok); (c) Aşama 5 = uygulamayı Streamlit'ten kendi domain'ine taşı (Barış bunu istiyor —
   Tier 1 self-host önce).
6. Future: Supabase e-posta şablonları (Türkçe kayıt onayı); 2 hesapla canlı izolasyon testi.
7. ✅ **Login duvarı + F5 oturum kalıcılığı + tier-duyarlı metin (2026-07-02)** — bkz. yukarıdaki
   ilgili bölüm. Yerelde test edildi, henüz push EDİLMEDİ (bir sonraki adım).
8. **AÇIK KARAR — model eğitimi otomasyonu (henüz planlanmadı, sadece konuşuldu 2026-07-02):**
   Barış "model her gün nasıl yeniden eğitilecek" diye sordu. VDS'in 2GB RAM'i eğitim için
   (günlük veri çekmekten daha ağır) riskli/sınırda olabilir; Barış kendi bilgisayarından da
   yapmak istemiyor. Claude'un önerisi: GitHub Actions (ücretsiz, ~7GB RAM'li runner) —
   VDS'in zaten Storage'a yüklediği `cache.sqlite.gz`'yi indirip (Is Yatirim'a hiç gerek yok,
   IP engeli bu adımı etkilemiyor) haftalık/2 haftada bir yeniden eğitip yeni `model.joblib`'i
   yine Storage'a yükler; Streamlit açılışta onu da indirir (git push otomasyonuna gerek kalmaz).
   Günlük eğitim ÖNERİLMEDİ (5/10 iş günü sonuç ufku nedeniyle günlük yeni etiketli veri
   anlamlı miktarda birikmiyor). Karar bekleniyor — henüz kod yazılmadı.

## Günün Kapanışı (2026-06-30)
- Bugün TAMAMEN frontend/marka işi (`valysera-web`): landing redesign + conversion overhaul. Python
  uygulamasına (hisse-takip) dokunulmadı. **Auth/payment/database/subscription/user-data davranışı
  DEĞİŞMEDİ** → güvenlik etkisi yok (detay SECURITY_NOTES). /login /signup yalnız UI placeholder
  (gerçek auth/veri toplama yok, mailto). Build temiz, canlı doğrulandı, kâr/garanti ifadesi yok.

## Known Constraints and Risks
- Financial/regulatory risk is high: app must not imply guaranteed returns or investment advice.
- Supabase gate is NOT enabled in local dev (or when secrets missing) — full access for backwards compat.
- Per-user isolation IS implemented (favorites/notes/blacklist via Supabase RLS, user_id=auth.uid()); not yet stress-tested with 2 live accounts.
- Service_role key now lives on the VPS (root-only env). It bypasses ALL RLS → high-value secret; VPS is a new attack surface (keep SSH hardened; never put the key in repo/logs).
- Streamlit Community Cloud /tmp is ephemeral; durability now comes from the VPS→Storage pipeline, not the runtime FS.
- Upstash keys are secret-bearing; never write their values into docs, prompts, logs, or memory.
- Dependency versions are minimum ranges, not locked exact versions.

## Security Status
- ✅ **RESOLVED (2026-06-29, Aşama 1):** `subscriptions` paywall-bypass açığı kapatıldı. Eski `for all` policy → tek `SELECT`-only policy. Canlı `pg_policies` ile doğrulandı; yazma yalnızca service_role'a kaldı. Repo `schema.sql` de güncellendi. Detay `docs/SECURITY_NOTES.md` üstte.
- Aşama 1 results: secret scan of tree+git history = clean (no secret values committed); fav/note/blacklist RLS isolation = design sound; dependency versions current but reqs use unpinned `>=` ranges; real `pip-audit` CVE scan + 2-account live test still pending.
- Risk level: high-risk.
- Auth gate implemented (Supabase), but not yet deployed/tested with real Supabase project.
- Payment/subscription/database launch is not verified yet.
- Existing local tests pass, but they are not a security test suite.
- Dependency audit, secret scan, payment/webhook verification, database RLS/access rules, backup/restore test, rate limiting, and legal disclaimer review remain pending.

## Recent Changes
- 2026-07-01 (Akıllı Radar): Fixed user-perceived "date bug" (was actually just confusing column
  labels — "5G/10G Sonuç Günü" → "5G/10G Hedef Tarih" + help tooltip). Removed `app.py::_auto_catchup`
  entirely (legacy synchronous per-user price fetch that blocked whoever triggered it; VPS cron +
  Storage already keeps data fresh). Added radar precompute step to `scripts/refresh_data.py`
  (before Storage upload) so VPS computes the day's Akıllı Radar snapshot once, centrally — no
  Streamlit user ever triggers the first `score_latest()` call anymore. Optimized
  `ml_signals/daily.py::_append_watch_symbols` to score only missing personal-favorite symbols
  instead of the whole ~600-symbol universe. Added 3 new tests (2 unit + repo's first integration
  test), full suite 11/11 green. Renamed pricing tiers to Turkish (Basic→Başlangıç,
  Studio→Profesyonel, Premium unchanged) and wired in the 6 real Lemon Squeezy variant IDs.
- 2026-07-01 (later): Expanded Lemon Squeezy integration from a single "Pro" plan to **3 paid tiers** (Basic $9/Premium $19/Studio $45 + yearly 25% off) after user feedback. `data/supabase_store.py` gained `current_tier()`/`has_tier()` tier hierarchy. `data/lemonsqueezy_store.py` simplified to just link to valysera-web's `/pricing` page (checkout UI moved there — `PricingComparison.tsx` rewritten as 4 cards × 11 fixed-order feature rows + monthly/yearly toggle). Webhook Edge Function updated to map `variant_id` → tier via new `LEMONSQUEEZY_VARIANT_ID_*` secrets, then **deployed and verified ACTIVE** on the live Supabase project (via `supabase functions deploy --no-verify-jwt`, using a user-provided Personal Access Token passed through a local file, never typed into a command literal — Claude Code's auto-mode classifier blocks literal secrets in Bash commands). `webhook_events` table created live by Barış. Logged 2 new features (Telegram notifications, team-shared favorites) as roadmap items — promised on the pricing page, not built yet.
- 2026-07-01: Started Lemon Squeezy payment integration (code only, not deployed yet). Added `data/lemonsqueezy_store.py` (checkout URL builder), sidebar "Pro'ya Geç" link in `app.py`, `.streamlit/secrets.toml` placeholder keys (`LEMONSQUEEZY_STORE_SLUG`/`LEMONSQUEEZY_VARIANT_ID`), `webhook_events` table in `supabase/schema.sql`, and `supabase/functions/lemonsqueezy-webhook/index.ts` (signature verification + idempotency + 8-event handling). valysera-web `/pricing` Pro CTA now redirects to the app instead of a dead `/signup` placeholder. See "Payment — Lemon Squeezy" section above for what's still pending (deploy, secrets, live webhook, testing).
- 2026-06-28: Added Claude/Codex project memory workflow, security notes, and MCP project indexing.
- 2026-06-29: Implemented Supabase auth layer (`data/supabase_store.py`), sidebar login form + signup form, Radar tab subscription gate, Favoriler/Notlar/Devre Dışı login gates, per-user favorites/notes/blacklist via Supabase CRUD, `supabase/schema.sql`, and `supabase>=2.0` in requirements.txt.
- 2026-06-29 (later): Deployed live. Favorites/notes/blacklist now Pro-only (`_is_pro_now()`), per-user via direct Supabase REST + JWT. Performance fixes (removed `bump_version()` from fav/note actions; memoized Supabase reads with login/logout/write invalidation; gated `evaluate_outcomes` once/day). Notlar three-dot edit/delete menu. Added Supabase Storage persistence + Turkish VPS daily cron pipeline (`scripts/refresh_data.py`, `supabase/storage_policies.sql`). Started planning migration off Streamlit to own domain (VPS data layer + Supabase + Next.js).
