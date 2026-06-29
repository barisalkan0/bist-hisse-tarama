# Security Notes

Security risk level: high-risk
Last reviewed: 2026-06-29

## Why This Repo Is High-Risk
- It is a financial-market decision-support app that can influence investment behavior.
- Public launch is planned soon with subscription and database features.
- Current code has no real auth/account boundary, no subscription enforcement, and no production database isolation model yet.
- It stores user-like preferences/notes/favorites locally and optionally in Upstash Redis.
- It depends on external market-data sources and ML scoring that must not be presented as financial advice.

## Sensitive Areas
- Financial output language: all radar/screener output must remain candidate/watch/risk/decision-support wording, not buy/sell advice.
- Secrets: Supabase URL/anon key (semi-public), **Supabase service_role key (now on the data VPS, root-only env)** — service_role BYPASSES all RLS = full DB access; highest-value secret. Also Upstash REST URL/token, future payment/webhook secrets.
- Infrastructure: a Turkish VPS now runs the daily data pipeline and holds the service_role key. New attack surface — keep SSH hardened (ufw + fail2ban set up; SSH key-auth + disable root password login still recommended). Root password was once exposed in a shared screenshot and was changed.
- User data: per-user notes/favorites/disabled symbols (Supabase, RLS by user_id), account/subscription state, future payment/customer identifiers. Auth emails are PII.
- Persistence: durable data file (`cache.sqlite.gz`) in Supabase Storage bucket `market-data` — public READ (non-sensitive market data), write effectively service_role-only. Local SQLite cache is runtime-only.
- ML/model integrity: `ml_signals/model.joblib`, backtest report, model kind, radar snapshots/outcomes.
- External data: Is Yatirim and Mynet endpoints may change, fail, rate-limit, or raise licensing/terms questions. Daily VPS cron adds repeated load on Is Yatirim (monthly throttled to days 1-5 to reduce request volume).

## Verified From Source
- `data/store.py` reads Upstash credentials from environment or Streamlit secrets and does not print token values.
- `store.secret_keys()` exposes secret key names only, not values.
- `note_card_html()` escapes symbol, date, and note text before rendering with `unsafe_allow_html=True`.
- `.gitignore` excludes generated `data/cache.sqlite`.
- Existing unit tests passed: 8/8 on 2026-06-28.
- `.streamlit/config.toml` exists; no `.streamlit/secrets.toml` file was observed during this setup.

## Not Verified Yet
- Full dependency vulnerability audit (`pip-audit`, Snyk, Dependabot, or equivalent).
- Secret scan of the entire repo with a dedicated scanner.
- Production auth/session design.
- Subscription/payment provider implementation.
- Payment webhook signature verification and idempotency.
- Database row-level access rules or tenant isolation.
- Backup/restore procedure for production database.
- Rate limiting and abuse controls for data refresh and user actions.
- Legal/financial disclaimer review for public launch.
- Data-provider terms/licensing review for commercial/subscription use.

## Mandatory Launch Gate Before Subscription/Public Release
- Add real authentication and account model.
- Enforce subscription status server-side; never trust client-only gating.
- Use a production database with per-user ownership rules and backups.
- If Stripe/Iyzico/other payment provider is used: verify webhook signatures, implement idempotency, handle failed payment, cancellation, refund, expired subscription, and plan downgrade states.
- Do not store raw card data; rely on the payment provider.
- Store payment/customer ids minimally and treat them as sensitive.
- Add financial disclaimer in the app and terms: no investment advice, no guaranteed return, data may be delayed/incorrect.
- Review data source terms for commercial use.
- Add monitoring/logging without leaking secrets or private user data.
- Add dependency audit and secret scan to release checklist.
- Test account isolation with at least two users before launch.

## Verification Log
| Date | Area | Check | Result | Evidence |
| --- | --- | --- | --- | --- |
| 2026-06-28 | Tests | Unit tests | Passed | `python -B -m unittest discover -v` ran 8 tests OK |
| 2026-06-28 | Secret handling | Upstash code path source review | Partially verified | `data/store.py` reads secrets and exposes names only in diagnostics |
| 2026-06-28 | XSS/input | Note HTML rendering source review | Partially verified | `note_card_html()` escapes note fields before unsafe HTML render |
| 2026-06-28 | MCP memory | Repo indexed | Verified | Project id `C-Users-asus-OneDrive-Masa-st-ahin-hisse-takip` |
| 2026-06-29 | Auth gate | Supabase login + subscription gate code review | Partially verified | `data/supabase_store.py` reads secrets, never prints values; is_pro() checks plan='pro' AND status='active' AND period_end server-side; gate degrades gracefully when Supabase not configured |
| 2026-06-29 | Tests | Unit tests after auth changes | Passed | 8/8 tests OK, app.py syntax OK |
| 2026-06-29 | Auth | Live login + Pro gate on real Supabase | Verified working | login/logout/signup work live; Pro account unlocks Radar; favorites/notes Pro-only |
| 2026-06-29 | Per-user data | Favorites/notes/blacklist write to Supabase per user | Verified working | RLS user_id=auth.uid(); session-cache invalidated on login/logout to avoid cross-user leak. NOT yet stress-tested with 2 concurrent live accounts |
| 2026-06-29 | Storage | Bucket public-read + restricted write | Partially verified | `market-data` public read = HTTP 200; write works via service_role from VPS; robot-uuid RLS write policy did NOT take effect (auth.uid() unresolved in Storage context) |
| 2026-06-29 | Secret handling | service_role key placement | Verified placement | Stored only in root-only `/etc/hisse.env` on the VPS; not in repo/logs/docs. VPS SSH: ufw+fail2ban on; key-auth + root-login-disable still pending |
| 2026-06-29 | Launch security | Payment/webhook/2-user isolation/dep-audit | Not verified yet | Payment not implemented; account-isolation 2-user test and dependency/secret scan still pending |

## Rules
- Never store secrets, credentials, payment data, customer data, raw PII, private keys, live API keys, DB URLs, Redis tokens, or webhook secrets in this file.
- Do not say "secure", "production-ready", or "safe to launch" unless the relevant checks were actually performed.
- If checks were not run, say: "Not verified yet."
