# Agent Instructions for hisse-takip

Always answer the user in Turkish unless they explicitly ask for another language.

## Memory Workflow
- Claude Code is the primary target for this repo; Codex should follow the same rules as a compatible fallback.
- Read `docs/AI_MEMORY.md` first in every fresh/resumed chat.
- Prefer `codebase-memory-mcp` before broad file reads or recursive search.
- MCP project id: `C-Users-asus-OneDrive-Masa-st-ahin-hisse-takip`.
- Current graph coverage is mostly file-tree level; use it for orientation and then read targeted files only.
- Keep `docs/AI_MEMORY.md` short and current after significant changes.
- Preserve existing project truth in `CLAUDE.md`; do not overwrite it with generic assumptions.

## Security and Launch Gate
- Treat this repo as `high-risk`: financial-market decision support, public launch planned, subscription/database planned.
- Never present model output as investment advice. Preserve candidate/watch/risk wording.
- Do not claim a change is secure, production-ready, or launch-ready unless relevant checks were actually performed. If not, say: `Not verified yet.`
- Do not read or expose secret-bearing files unless explicitly required. Never store/repeat secrets, Redis tokens, DB URLs, API keys, payment data, customer data, private notes, or raw PII.
- Before payment/subscription/database launch, require server-side auth, server-side subscription checks, payment webhook signature verification, webhook idempotency, database access isolation, backups, rate limiting, audit logs, dependency audit, and financial/legal disclaimers.
