# Security Notes

Security risk level: high-risk
Last reviewed: 2026-07-01

## 2026-07-01 (later) — 3-tier pricing expansion + Edge Function DEPLOYED
- Expanded from a single "Pro" plan to 3 paid tiers (Basic/Premium/Studio) per user request. `webhook_events` table was created on the LIVE Supabase project by Barış (SQL from `supabase/schema.sql` run in SQL Editor) — the "not yet created" caveat below is now resolved for that table.
- `lemonsqueezy-webhook` Edge Function **deployed and confirmed ACTIVE** (`supabase functions deploy --no-verify-jwt`, function id `0b4e2e2b-1a76-4caf-b45d-1d2893b9fe6c`, `verify_jwt: false` confirmed via `supabase functions list`). It is reachable but **fails closed**: `LEMONSQUEEZY_WEBHOOK_SECRET` is unset ⇒ any request gets HTTP 500 "webhook not configured" (checked in source: `if (!WEBHOOK_SECRET) return 500` before any signature check runs) — no unsigned/unverified request can reach the `subscriptions` write path. Variant→tier mapping (`LEMONSQUEEZY_VARIANT_ID_*`) is also unset ⇒ even once the secret is set, unmapped variants log a warning and skip the DB write rather than guessing a tier.
- **Credential-handling note (process, not code):** the user provided a Supabase Personal Access Token in chat to enable this deploy. Claude Code's own auto-mode safety classifier **blocked** an initial attempt to pass the token as a literal `SUPABASE_ACCESS_TOKEN=sbp_...` argument in a Bash command (reason: shell-history/process-listing exposure risk). Resolved by having the user save the token to a local file (`%USERPROFILE%\.supabase_token`, outside the repo, not git-tracked) themselves, then Claude referenced it via `$(tr -d '\r\n' < path)` shell substitution — the literal token value never appeared in any Claude-authored command, file, or output. This is the correct pattern for any future secret-requiring CLI operation in this project.
- Still not verified: real Lemon Squeezy signed requests have never hit the deployed function (store not activated yet); the 6 checkout variant IDs and webhook signing secret do not exist yet since Barış has not created the Premium/Studio Lemon Squeezy products.

## 2026-07-01 — Lemon Squeezy payment integration (code written, NOT deployed/live-tested)
- Provider decided: Lemon Squeezy. Wrote (did not deploy): `data/lemonsqueezy_store.py` (checkout link builder, no secret material — store slug + variant id are not sensitive), `supabase/functions/lemonsqueezy-webhook/index.ts` (Edge Function), `webhook_events` table in `supabase/schema.sql`.
- **Not verified yet (code review only, no live traffic through it):**
  - Webhook signature verification: implemented as HMAC-SHA256 over the raw (pre-`JSON.parse`) request body using Web Crypto, compared with a constant-time byte comparison against `X-Signature`. Correct by source review; not yet exercised against a real Lemon Squeezy signed request.
  - Idempotency: implemented via `webhook_events.event_hash UNIQUE` (sha256 of raw body); a duplicate delivery hits a unique-violation (`23505`) and is skipped, still returns HTTP 200 so Lemon Squeezy does not retry-storm. Not yet tested with an actual duplicate delivery.
  - `subscriptions` upsert keyed on `provider_subscription_id`; `user_id` sourced from `meta.custom_data.user_id` (set at checkout time via `data/lemonsqueezy_store.py`). If that custom data is ever missing on the very first event for a subscription, the insert fails (NOT NULL `user_id`) and is logged, not silently swallowed — but this failure path has not been tested either.
  - `webhook_events` RLS follows the same pattern already verified safe for `subscriptions` (2026-06-29 fix below): RLS enabled, zero policies ⇒ only `service_role` can read/write. Same reasoning applies; not yet confirmed on live Supabase because the table has not been created there yet.
- **Deliberate product/security decision:** `subscription_cancelled` webhook event does NOT immediately downgrade the user — `status` stays `'active'` and `current_period_end` is set to Lemon Squeezy's `ends_at`. `is_pro()` already gates on `current_period_end > now()`, so access lapses automatically at period end with no extra code. This is intentional (matches Lemon Squeezy's own "cancelled but still valid" semantics) and should not be "fixed" to downgrade immediately.
- **Nothing is live yet:** the Edge Function is not deployed, `LEMONSQUEEZY_WEBHOOK_SECRET` is not set anywhere, the `webhook_events` migration has not been run on the live Supabase project, and the checkout button is invisible in production until `LEMONSQUEEZY_STORE_SLUG`/`LEMONSQUEEZY_VARIANT_ID` secrets are filled in. Until deploy + a real Lemon Squeezy "Simulate event" test pass, treat this whole payment path as **not verified in production**.

## 2026-06-30 — Marketing/landing site (no security-sensitive change)
- Today's work was entirely in the SEPARATE marketing repo `valysera-web` (Next.js, static, on Vercel).
  The Python app (`hisse-takip`) and its auth/payment/database/subscription/user-data code were NOT touched.
- `/login` and `/signup` are **UI placeholders only** — no authentication, no form, no data collection;
  they link via `mailto:` to the contact address. No PII is gathered, no secrets are present in the repo.
- No payment flow exists (pricing shows "Yakında"). No new backend, DB, or secret surface.
- Net: **no change to security posture.** The full launch gate below remains pending and applies when real
  auth/payment/subscription functionality is actually implemented (Aşama 4).

## ✅ RESOLVED 2026-06-29 — subscriptions self-insert / paywall bypass
- **Fixed on LIVE Supabase:** dropped the `for all` policy; `subscriptions` now has a single policy `user reads own subscription` (`cmd=SELECT`, `qual=auth.uid()=user_id`). No insert/update/delete policy ⇒ authenticated role cannot write (RLS default-deny); only `service_role` (future webhook) can write. Confirmed via `pg_policies` query output.
- Repo `supabase/schema.sql` updated to match (SELECT-only + warning comment), so the bad policy cannot be re-introduced from repo.
- Optional extra confidence (not yet run): write-path test — POST `/rest/v1/subscriptions` as a non-pro authenticated user should now return 4xx.
- Original finding kept below for the record.

## ⚠️ Original Finding (now resolved) — subscriptions self-insert / paywall bypass
- **What:** `supabase/schema.sql` defines `subscriptions` with one policy: `for all using (auth.uid() = user_id)`. In Postgres, when `WITH CHECK` is omitted it is copied from `USING` for INSERT. So the *only* constraint on an insert is `user_id = auth.uid()`; nothing constrains `plan` or `status`.
- **Impact:** Any authenticated (signed-up) user can `POST /rest/v1/subscriptions` with `{user_id: <their own id>, plan: "pro"}` (status defaults to `'active'`; null `current_period_end` → `is_pro()` returns True as perpetual) and self-grant Pro. This fully bypasses the paywall on Akıllı Radar / Favoriler / Notlar. The table is reachable by the authenticated role because `is_pro()` already reads it over REST with anon key + user JWT.
- **Severity:** Blocks public launch. Not currently causing harm (pre-launch; subscription rows added manually), so it is a launch blocker, not an active incident.
- **Why the original plan's test missed it:** "delete the row, see Radar close" exercises the READ path. The discriminating test is the WRITE path: from a throwaway authenticated session, POST a pro row for your own user_id and see if `is_pro()` flips.
- **Fix (mirror the existing `storage_policies.sql` pattern — there the author correctly restricts writes and warns "authenticated rolüne AÇMA"):** make `subscriptions` SELECT-only for authenticated; add no insert/update/delete policy so only `service_role` (the future webhook) writes it.
  ```sql
  drop policy if exists "user owns subscription" on public.subscriptions;
  create policy "user reads own subscription"
    on public.subscriptions for select using (auth.uid() = user_id);
  ```
- **Repo-vs-live caveat:** above is read from repo `schema.sql`. The DEPLOYED policy in the Supabase dashboard is what actually gates — confirm it matches before declaring fixed (this repo was already bitten once by repo≠live drift: the set_session deployment lag).
- **Status:** Documented, NOT yet fixed. Applying the fix is a live-Supabase action — awaiting Barış's choice: hotfix now vs fold into Aşama 3 (payment) since no live paying users yet.

## Secondary Findings (non-blocking)
- `is_pro()` (`data/supabase_store.py`) **fails open** on a malformed `current_period_end` (`except Exception: return True`) and treats a null `period_end` as perpetual Pro. Fine for manual rows; the future webhook must always set `status` + `current_period_end`.
- fav/note/blacklist isolation is **genuinely sound** — the same `for all using(auth.uid()=user_id)` is *correct* there, because users owning/writing only their own rows is the intent. (Distinct from the subscriptions finding above.)

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
- Full dependency vulnerability audit with a real scanner (`pip-audit`/Snyk). `pip-audit` is NOT installed locally; not installed to avoid an unrequested system change. A lightweight pattern/version review was done instead (see log 2026-06-29).
- Live (deployed-Supabase) confirmation that the `subscriptions` policy matches the SELECT-only fix above.
- Production auth/session design.
- Lemon Squeezy webhook signature verification and idempotency: implemented in code (2026-07-01), NOT yet deployed or exercised against real Lemon Squeezy traffic — see log entry above.
- `webhook_events` RLS (service_role-only, no policies) on the LIVE Supabase project — table not created there yet.
- Database row-level access rules or tenant isolation.
- Backup/restore procedure for production database.
- Rate limiting and abuse controls for data refresh and user actions.
- Legal/financial disclaimer review for public launch.
- Data-provider terms/licensing review for commercial/subscription use.

## Mandatory Launch Gate Before Subscription/Public Release
- Add real authentication and account model.
- Enforce subscription status server-side; never trust client-only gating.
- Use a production database with per-user ownership rules and backups.
- Lemon Squeezy is the chosen provider: verify webhook signatures (done in code, not yet live-deployed), implement idempotency (done in code, not yet live-deployed), handle failed payment, cancellation, refund, expired subscription, and plan downgrade states (all 8 events mapped — see "Payment — Lemon Squeezy" in `docs/AI_MEMORY.md`).
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
| 2026-06-29 | Launch security | Payment/webhook/2-user isolation/dep-audit | Not verified yet | Payment not implemented; account-isolation 2-user test still pending |
| 2026-06-29 | RLS / paywall | `subscriptions` write policy source review | Found CRITICAL | `for all using(auth.uid()=user_id)` w/o WITH CHECK ⇒ authenticated user could self-insert plan='pro' and bypass paywall |
| 2026-06-29 | RLS / paywall | `subscriptions` fix applied + verified on LIVE | **Resolved** | Live `pg_policies` shows single `SELECT`-only policy; no write policy ⇒ authenticated cannot write, only service_role. Repo `schema.sql` updated to match |
| 2026-06-29 | RLS isolation | fav/note/blacklist policies source review | Verified (design sound) | `auth.uid()=user_id` correct for owner-only tables; matches REST CRUD in `data/supabase_store.py`. Still pending: 2-account live stress test |
| 2026-06-29 | Secret scan | Repo working tree + full git history (`git log -S`) | Verified clean | No secret VALUES in tree or history; only key NAMES + secret-reading code + docs. `.streamlit/secrets.toml` not tracked (in `.gitignore`). No JWT/`eyJ…`/upstash-host/service_role value found |
| 2026-06-29 | Dependency audit | `requirements.txt` ranges vs installed versions (no scanner) | Partially verified | Installed: pandas 3.0.2, numpy 1.26.4, streamlit 1.56.0, requests 2.33.1, scikit-learn 1.9.0, supabase 2.31.0 — all recent, no obviously-vulnerable old pins. RISK: reqs use `>=` min-ranges (not locked) ⇒ deploy may resolve different versions; e.g. local pandas 3.0 vs `pandas>=2.0`. Real CVE scan still pending |
| 2026-07-01 | Payment webhook | Lemon Squeezy Edge Function signature verification + idempotency source review | Partially verified (code only) | HMAC-SHA256 over raw body, constant-time compare, `event_hash` UNIQUE for idempotency — correct by reading; not deployed, no real Lemon Squeezy request has hit it yet |
| 2026-07-01 | Payment webhook | `subscription_cancelled` handling — does it downgrade access immediately? | Verified by design | Intentionally does NOT downgrade immediately; `status` stays active, `current_period_end`=`ends_at`, existing `is_pro()` period check handles the eventual downgrade |
| 2026-07-01 | Payment webhook | Edge Function deploy + fail-closed behavior | Verified | `supabase functions list` confirms `status: ACTIVE`, `verify_jwt: false`; source-reviewed fail-closed paths: missing `LEMONSQUEEZY_WEBHOOK_SECRET` → 500 before any write; unmapped `variant_id` → logged + skipped, no guessed tier written |
| 2026-07-01 | Credential handling | Bash tool blocked a literal Supabase PAT in a command | Verified (control worked as intended) | Auto-mode classifier denied `SUPABASE_ACCESS_TOKEN=sbp_...` as a literal arg; resolved via user-created local file + shell substitution, token never appeared in any Claude-authored command/file |

## Manual 2-Account Test Plan (run on live/staging Supabase before launch)
Goal: prove per-user isolation AND that the paywall cannot be self-granted.

1. **Setup:** create two test users A and B (signup form). Note their login tokens stay client-side only.
2. **Isolation — read:** as A, add a favorite/note/blacklist symbol. Log in as B; confirm B sees NONE of A's data and vice-versa.
3. **Isolation — write tamper (RLS WITH CHECK):** as A, attempt to write a row carrying B's `user_id` (e.g. craft a REST POST to `/rest/v1/favorites` with `user_id=<B>`). Expect HTTP 4xx / 0 rows — RLS must reject.
4. **Paywall read path:** give A a manual `subscriptions` row (plan=pro, status=active) via dashboard → Radar/Favoriler/Notlar unlock. Delete the row → after cache invalidation they re-lock.
5. **Paywall WRITE path (the critical test):** as a NON-pro authenticated user, attempt `POST /rest/v1/subscriptions` with `{user_id:<self>, plan:"pro"}`.
   - BEFORE fix: expect it to succeed and `is_pro()` to flip True (demonstrates the hole).
   - AFTER the SELECT-only fix: expect HTTP 4xx (no insert policy) and `is_pro()` stays False.
6. **Logout cross-user cache:** log out A, log in B in same session; confirm no A data leaks via `st.session_state` caches (login/logout already pop `_pro_now`/`_favs_cache`/etc.).

## Legal / Disclaimer Status (Aşama 2, 2026-06-29)
- Added `legal/*.md` drafts: `disclaimer`, `terms`, `privacy` (KVKK aydınlatma), `pricing` (aylık+yıllık), `refunds` (Model A — cayma feragati). Rendered in a PUBLIC (ungated) "Bilgi & Yasal" tab; global short disclaimer shown on every render under the hero.
- **DRAFT — NOT legally verified.** Each file opens with a "TASLAK — hukukçu onayı şarttır" banner. These must be lawyer-reviewed before public launch; do NOT treat as compliant.
- Disclaimer uses the standard SPK "yatırım danışmanlığı kapsamında değildir" formula. **Open question for Barış:** whether running this as a PAID BIST decision-support product needs SPK consideration (yatırım danışmanlığı is a licensed activity). A disclaimer reduces but does not by itself resolve the licensing question.
- KVKK: collecting auth emails makes [İŞLETME ADI] a *veri sorumlusu*; VERBİS registration applicability is a Barış-verify.
- Placeholders still to fill: [İŞLETME ADI], [VKN/MERSİS], [İLETİŞİM E-POSTASI], [İL], [TARİH], price amounts, KDV/yenileme/yurtdışı-aktarım details.

## Rules
- Never store secrets, credentials, payment data, customer data, raw PII, private keys, live API keys, DB URLs, Redis tokens, or webhook secrets in this file.
- Do not say "secure", "production-ready", or "safe to launch" unless the relevant checks were actually performed.
- If checks were not run, say: "Not verified yet."
