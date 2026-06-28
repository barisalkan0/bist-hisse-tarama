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

## Auth + Subscription Gate (Implemented 2026-06-29)
- Sidebar shows login form when Supabase is configured and user is not logged in.
- Radar tab: gated behind `is_pro()` check (requires active pro subscription row in Supabase `subscriptions` table).
- Favoriler tab: gated behind login (any account, no subscription required).
- Notlar tab: gated behind login (any account, no subscription required).
- If Supabase is NOT configured (SUPABASE_URL / SUPABASE_ANON_KEY missing): app runs in anonymous mode — all tabs visible, backwards compatible with local dev.
- Notes/favorites/blacklist data: still stored in local SQLite + Upstash Redis (per-user Supabase migration is a future step).

## Supabase DB Schema (supabase/schema.sql)
- `subscriptions(user_id, provider, provider_customer_id, provider_subscription_id, plan, status, current_period_end)` — provider-agnostic design.
- `notes(user_id, symbol, note_text)`, `favorites(user_id, symbol)`, `blacklist(user_id, symbol)` — all with RLS.
- Manual subscription rows can be added via Supabase dashboard to test pro access.

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
1. User creates Supabase project and runs `supabase/schema.sql`.
2. Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to Streamlit secrets.
3. Install `supabase>=2.0` (`pip install supabase` / `requirements.txt` updated).
4. Test auth flow: login, logout, subscription gate.
5. Future: migrate notes/favorites/blacklist to per-user Supabase tables.
6. Future: choose payment provider, implement webhook, add legal pages.

## Known Constraints and Risks
- Financial/regulatory risk is high: app must not imply guaranteed returns or investment advice.
- Supabase gate is NOT enabled in local dev (or when secrets missing) — full access for backwards compat.
- Notes/favorites/blacklist currently shared (SQLite + Upstash) — no per-user isolation yet.
- Upstash keys are secret-bearing; never write their values into docs, prompts, logs, or memory.
- Streamlit Community Cloud/runtime filesystem is not a durable database.
- Dependency versions are minimum ranges, not locked exact versions.

## Security Status
- Risk level: high-risk.
- Auth gate implemented (Supabase), but not yet deployed/tested with real Supabase project.
- Payment/subscription/database launch is not verified yet.
- Existing local tests pass, but they are not a security test suite.
- Dependency audit, secret scan, payment/webhook verification, database RLS/access rules, backup/restore test, rate limiting, and legal disclaimer review remain pending.

## Recent Changes
- 2026-06-28: Added Claude/Codex project memory workflow, security notes, and MCP project indexing.
- 2026-06-29: Implemented Supabase auth layer (`data/supabase_store.py`), sidebar login form, Radar tab subscription gate, Favoriler/Notlar login gates, `supabase/schema.sql`, and `supabase>=2.0` in requirements.txt.
