# 004 — AI-filled journal via MCP / API (design)

- **Status:** draft
- **Date:** 2026-11-23
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/004-ai-journal-ui/design.md`
- **Services touched:** new `journal-ai` (MCP server + API); `journal` (entries, notes, tags); `auth` (API tokens)
- **Depends on:** 001 (journal), ideally 002 (auto-synced executions)

## 1. Intent

Filling a journal by hand does not happen. Executions arrive automatically (002); this spec lets an
AI agent (Claude, ChatGPT, a custom agent) read the user's trades and write the human part of the
journal — setup, reasons, emotions, mistakes, lessons, screenshots — through an MCP server or API.

## 2. Goals, non-goals, anti-goals

**Goals**
- Journal entries linked to trades: notes, tags (setup, mistake, emotion), rating, screenshots/links.
- **MCP server** exposing tools such as `list_trades`, `get_trade`, `annotate_trade`,
  `create_journal_entry`, `get_stats`, scoped to the authenticated user.
- Public REST API with **personal API tokens** (scoped, revocable) for other agents/automations.
- Every AI-written field is marked with its source (`ai:<client>`) and editable by the user.

**Non-goals** — our own chat UI with an LLM (later), trade signals/advice.

**Anti-goals** — AI overwriting user-written notes; tokens that can do more than journaling; leaking one
user's trades to another through the agent.

## 3. Constraints

- Tokens follow `.agents/rules/security.md` (hashed, scoped `journal:read` / `journal:write`, revocable).
- The human stays the owner of edits: AI writes are additive or suggestions unless the user allows overwrite.

## 4. Research (first task of the plan)

| Candidate | Purpose | Verdict |
|---|---|---|
| MCP Python SDK (official) | Build the MCP server | TBD |
| Remote MCP transport (streamable HTTP) + OAuth vs. token | How users connect clients | TBD |
| Existing open-source trading-journal MCP servers | Reuse tool design | TBD |

## 5. Approaches

1. Separate `journal-ai` service hosting MCP + token API, calling `journal` over HTTP (recommended).
2. MCP endpoints inside `journal`. Rejected: mixes protocol adapters with the domain service.

## 6. Design sketch

- `journal` gains `JournalEntry` (trade_ids, body, tags, rating, attachments, source, created_by).
- `journal-ai`: inbound adapters MCP + REST; outbound `JournalGateway`; use cases map 1:1 to MCP tools.
- `auth`: `ApiToken` (hash, scopes, name, last_used_at, revoked_at).

## 7. Open questions

- Which AI clients matter first (Claude Desktop/Code, ChatGPT, custom)? Affects transport/auth choice.
- Screenshots: store files (object storage) or links only at first?

## 8. Done when

From an MCP client, an authenticated user asks the agent to review today's trades and the journal
shows the AI-written entries linked to those trades, marked as AI, editable, and invisible to others.
