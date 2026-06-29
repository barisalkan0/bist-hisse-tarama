# AI Memory

Last updated: 2026-06-29
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
- Manual subscription rows can be added via Supabase dashboard to test pro access.

## Data Pipeline + Persistence (VPS) (2026-06-29)
- Is Yatirim blocks foreign datacenter IPs (GitHub Actions Azure → ConnectTimeout, proven). Streamlit Cloud IP is allowed.
- A Turkish VPS (Istanbul) runs `scripts/refresh_data.py` daily via cron (weekdays 19:00 TRT): fetches EOD prices (+ monthly on days 1-5), updates SQLite, VACUUM+gzip, uploads to Supabase Storage bucket `market-data/cache.sqlite.gz`.
- Live app downloads that public asset on boot (`cache.py::_try_storage_download`) → falls back to committed seed on any failure. Keeps data fresh with no visits/logins.
- Storage write uses the **Supabase service_role key** stored ONLY in a root-only env file on the VPS (never in repo/logs). Reason: robot-account RLS write policy did not work in Storage context (auth.uid() unresolved); service_role bypasses RLS and is the standard backend approach.
- Storage bucket is public-READ (market data is non-sensitive); write is effectively service_role-only.

## Payment (Not Implemented Yet)
- Provider not confirmed (Paddle, Stripe, or Iyzico).
- DB schema is provider-agnostic (provider + provider_subscription_id columns).
- Domain and legal pages (/pricing, /terms, /privacy, /refunds) needed before launch.
- Payment webhook handler: Supabase Edge Function (to be implemented when provider chosen).

## Current Verification
- `python -B -m unittest discover -v` passed on 2026-06-29: 8 tests OK.
- `python -B -c "import ast; ast.parse(open('app.py').read())"` — syntax OK.
- MCP index status is ready, file-tree level coverage.
- Static review confirmed note-card HTML escapes user note text before `unsafe_allow_html=True` rendering.

## Active Work / Next Steps
1. ✅ Supabase auth + per-user favorites/notes/blacklist live; Pro-only gating for those features.
2. ✅ Automatic daily data pipeline live (Turkish VPS cron → Supabase Storage → app downloads).
3. Planned migration OFF Streamlit to own domain: Phase 2 = Next.js frontend on own domain (reads Supabase); Phase 3 = payment (iyzico/Paddle) + legal pages. Heavy data/ML stays on the VPS.
4. Future: email templates in Supabase (Türkçe kayıt onayı); test account isolation with 2 users.

## Known Constraints and Risks
- Financial/regulatory risk is high: app must not imply guaranteed returns or investment advice.
- Supabase gate is NOT enabled in local dev (or when secrets missing) — full access for backwards compat.
- Per-user isolation IS implemented (favorites/notes/blacklist via Supabase RLS, user_id=auth.uid()); not yet stress-tested with 2 live accounts.
- Service_role key now lives on the VPS (root-only env). It bypasses ALL RLS → high-value secret; VPS is a new attack surface (keep SSH hardened; never put the key in repo/logs).
- Streamlit Community Cloud /tmp is ephemeral; durability now comes from the VPS→Storage pipeline, not the runtime FS.
- Upstash keys are secret-bearing; never write their values into docs, prompts, logs, or memory.
- Dependency versions are minimum ranges, not locked exact versions.

## Security Status
- Risk level: high-risk.
- Auth gate implemented (Supabase), but not yet deployed/tested with real Supabase project.
- Payment/subscription/database launch is not verified yet.
- Existing local tests pass, but they are not a security test suite.
- Dependency audit, secret scan, payment/webhook verification, database RLS/access rules, backup/restore test, rate limiting, and legal disclaimer review remain pending.

## Recent Changes
- 2026-06-28: Added Claude/Codex project memory workflow, security notes, and MCP project indexing.
- 2026-06-29: Implemented Supabase auth layer (`data/supabase_store.py`), sidebar login form + signup form, Radar tab subscription gate, Favoriler/Notlar/Devre Dışı login gates, per-user favorites/notes/blacklist via Supabase CRUD, `supabase/schema.sql`, and `supabase>=2.0` in requirements.txt.
- 2026-06-29 (later): Deployed live. Favorites/notes/blacklist now Pro-only (`_is_pro_now()`), per-user via direct Supabase REST + JWT. Performance fixes (removed `bump_version()` from fav/note actions; memoized Supabase reads with login/logout/write invalidation; gated `evaluate_outcomes` once/day). Notlar three-dot edit/delete menu. Added Supabase Storage persistence + Turkish VPS daily cron pipeline (`scripts/refresh_data.py`, `supabase/storage_policies.sql`). Started planning migration off Streamlit to own domain (VPS data layer + Supabase + Next.js).
