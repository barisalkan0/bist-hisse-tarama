# Security Notes

Security risk level: high-risk
Last reviewed: 2026-06-28

## Why This Repo Is High-Risk
- It is a financial-market decision-support app that can influence investment behavior.
- Public launch is planned soon with subscription and database features.
- Current code has no real auth/account boundary, no subscription enforcement, and no production database isolation model yet.
- It stores user-like preferences/notes/favorites locally and optionally in Upstash Redis.
- It depends on external market-data sources and ML scoring that must not be presented as financial advice.

## Sensitive Areas
- Financial output language: all radar/screener output must remain candidate/watch/risk/decision-support wording, not buy/sell advice.
- Secrets: Upstash REST URL/token, future DB URLs, payment secrets, webhook secrets, auth provider secrets.
- User data: notes, favorites, disabled symbols, future account/subscription state, future payment/customer identifiers.
- Persistence: current SQLite cache is local/runtime; Upstash stores shared blacklist/favorites/notes keys without per-user isolation.
- ML/model integrity: `ml_signals/model.joblib`, backtest report, model kind, radar snapshots/outcomes.
- External data: Is Yatirim and Mynet endpoints may change, fail, rate-limit, or raise licensing/terms questions.

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
| 2026-06-29 | Launch security | Subscription/database/auth production readiness | Not verified yet | Supabase project not yet created; no live test performed |

## Rules
- Never store secrets, credentials, payment data, customer data, raw PII, private keys, live API keys, DB URLs, Redis tokens, or webhook secrets in this file.
- Do not say "secure", "production-ready", or "safe to launch" unless the relevant checks were actually performed.
- If checks were not run, say: "Not verified yet."
