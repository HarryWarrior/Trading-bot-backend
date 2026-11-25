# 002 — MT5 automatic sync via EA bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** A user's MT5 terminal pushes every deal through our EA to a new `mt5-bridge` service, which forwards to `journal`, which pairs deals into trades.
**Architecture:** EA → `mt5-bridge` (port 8005, `bridge_db`: tokens, accounts, heartbeat) → `journal` service-key endpoint `/ingest/deals` (stores raw deals, pairs by `position_id`, upserts trades). Pairing logic is ported from `services/mt5/src/mt5_service/domain/trades.py`. Copy `services/_template` for the bridge.
**Tech Stack:** Python 3.11, FastAPI, Motor, pytest, httpx, MQL5.
**Spec:** `specs/002-mt5-ea-bridge-sync/design.md` (ADR 0002)

## Global constraints

- Tokens: 32+ random bytes, shown once, SHA-256 hash stored, revocable, scope `ingest:mt5`, `last_used_at` updated; never logged.
- Raw-deal idempotency key `(user_id, account_ref, deal_ticket)`, unique index; `account_ref = login@server`.
- Bridge → journal auth: header `X-Service-Key` = `INGEST_SERVICE_KEY` (>= 32 chars); journal receives `user_id` in the body (no user JWT on this path).
- Heartbeat every 60 s; account `disconnected` after 5 min without one.
- Hexagonal rule, envelope/errors from `trading_shared`, `user_id` on every document, English only, TDD, Ruff clean.
- EA inputs: `ApiUrl`, `IngestToken`. User must whitelist the API URL under Allow WebRequest.

## Review focus

- Same deal sent twice (retry/backfill) → no duplicate raw deal or trade (Tasks 2, 4).
- Position whose exit arrives before entry (out-of-order batch) → trade built once both exist (Task 2).
- Revoked or unknown token → 401, nothing stored; token of user A never writes to user B (Tasks 3, 4).
- Journal down during forward → bridge returns 503 and the EA keeps the batch queued (Tasks 4, 7).
- INOUT/reversal positions → reported as skipped, not guessed (Task 2).

---

### Task 1: Research and integrations record

**Files:**
- Modify: `docs/integrations/README.md`, `docs/adr/0002-mt5-ea-bridge.md` (only if findings change it)

**Interfaces:** Produces: written verdict on reusable MQL5 WebRequest/JSON/queue code (license, maintenance), used by Task 7.

- [ ] **Step 1:** Search GitHub/MQL5 for open-source MQL5 REST/WebRequest bridge EAs, ZeroMQ bridges and MetaApi; fill the table in design §4 with license, maintenance, JSON/queue support and a verdict each.
- [ ] **Step 2:** Record in `docs/integrations/README.md` (mark anything not adopted); name which snippets (if any) Task 7 may reuse and their license.
- [ ] **Step 3:** Commit `docs(integrations): MT5 bridge research`.

### Task 2: Journal — raw deal pairing and `/ingest/deals`

**Files:**
- Create: `services/journal/src/journal_service/domain/deals.py`, `.../domain/deal_pairing.py`, `.../application/use_cases/ingest_deals.py`
- Modify: `.../application/ports/repositories.py` (add `DealRepository`), `.../adapters/outbound/mongo_repositories.py`, `.../adapters/inbound/http/router.py`, `.../adapters/inbound/http/schemas.py`, `.../bootstrap.py`
- Test: `services/journal/tests/unit/test_deal_pairing.py`, `.../test_ingest_deals.py`, `.../tests/integration/test_ingest_deals_api.py`

**Interfaces:**
- Consumes: `build_trade`, `TradeRepository.upsert_many`, `BalanceRepository.upsert_many`, service-key guard `_service_key`.
- Produces: `RawDeal` dataclass (`ticket:int, position_id:int, time:datetime, type:int, entry:int, symbol:str, volume:Decimal, price:Decimal, commission:Decimal, swap:Decimal, profit:Decimal, sl, tp, comment`); `pair_deals(deals: list[RawDeal]) -> PairingResult(trades, balance_events, skipped)`; `DealRepository.upsert_many(user_id, account_ref, deals) -> int` (new count) and `positions_for(user_id, account_ref, position_ids) -> list[RawDeal]`; `IngestDeals.execute(user_id, account_ref, deals) -> IngestDealsResult(received, new, trades_upserted)`; `POST /api/v1/journal/ingest/deals` (service key; body `{user_id, account_ref, deals[]}`).

- [ ] **Step 1:** Write failing `test_deal_pairing.py`: port every case from the `mt5` service tests for `domain/trades.py` (entry+exit closes a trade; partial exit stays open; INOUT → skipped with reason; cancel deals ignored; balance types → events; fee folded into commission), plus `test_exit_before_entry_in_batch_pairs_once_both_present`.
- [ ] **Step 2:** Run `pytest services/journal/tests/unit/test_deal_pairing.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `pair_deals` in `domain/deal_pairing.py` by porting the `mt5_service/domain/trades.py` rules to journal's types (server-time conversion stays out: the bridge sends UTC ISO times).
- [ ] **Step 4:** Write failing `test_ingest_deals.py` with in-memory repos: `test_same_deal_twice_creates_one_raw_deal_and_one_trade`, `test_late_exit_completes_trade_from_stored_entry` (the use case re-reads stored deals of affected `position_id`s before pairing).
- [ ] **Step 5:** Implement `IngestDeals`, the `DealRepository` port + Mongo adapter (collection `deals`, unique index `(user_id, account_ref, ticket)`), schemas and the endpoint (service-key guard; `user_id` from body); wire in `bootstrap.py`.
- [ ] **Step 6:** Write failing `test_ingest_deals_api.py`: 403 without key; 200 with key creates a trade visible to that `user_id` only; repeat call returns `new=0`.
- [ ] **Step 7:** Run `pytest services/journal -q` and `ruff check . && ruff format --check .` → PASS. Commit `feat(journal): ingest raw MT5 deals and pair them`.

### Task 3: `mt5-bridge` service — domain, tokens, accounts

**Files:**
- Create: `services/mt5-bridge/` copied from `services/_template` (package `mt5_bridge_service`, port 8005, `pyproject.toml`, `.env.example` with `JWT_SECRET_KEY`, `INGEST_SERVICE_KEY`, `JOURNAL_URL`, `MONGO_URL`, `MONGO_DB=bridge_db`); `domain/{token.py,account.py,errors.py}`; `application/ports/{tokens.py,accounts.py,journal.py,clock.py,ids.py}`; `application/use_cases/{issue_token.py,revoke_token.py,list_tokens.py,record_heartbeat.py,list_accounts.py}`; `adapters/outbound/mongo_*.py`
- Test: `services/mt5-bridge/tests/unit/` (one file per use case) + architecture test copied from the template

**Interfaces:**
- Produces: `IngestToken(id, user_id, name, hash, created_at, last_used_at, revoked_at)`; `IssueIngestToken.execute(user_id, name) -> (IngestToken, plaintext: str)` (plaintext only here); `TokenRepository.find_active_by_hash(hash) -> IngestToken | None`; `BrokerAccount(user_id, account_ref, login, server, balance, equity, last_heartbeat, last_deal_at)` with `status(now) -> "connected"|"disconnected"` (5 min); `RecordHeartbeat.execute(user_id, hb)`; `ListAccounts.execute(user_id)`.

- [ ] **Step 1:** Copy the template; rename; register `mt5-bridge` in `scripts/dev.ps1` (8005) and in the install line of `AGENTS.md`.
- [ ] **Step 2:** Write failing tests: `test_issue_token_returns_plaintext_once_and_stores_only_hash`, `test_plaintext_is_at_least_32_bytes_of_entropy`, `test_revoked_token_not_found_active`, `test_status_connected_within_5_minutes_else_disconnected`, `test_list_accounts_only_returns_own_user`, `test_heartbeat_upserts_account_by_account_ref`.
- [ ] **Step 3:** Run `pytest services/mt5-bridge -q` → FAIL.
- [ ] **Step 4:** Implement domain, ports, use cases, Mongo adapters (unique index on token hash; `(user_id, account_ref)` unique on accounts).
- [ ] **Step 5:** Run tests + architecture test + Ruff → PASS. Commit `feat(mt5-bridge): tokens, accounts and heartbeat domain`.

### Task 4: `mt5-bridge` HTTP API and journal forwarding

**Files:**
- Create: `adapters/outbound/journal_gateway.py` (httpx, `X-Service-Key`; port `JournalGateway.ingest_deals(user_id, account_ref, deals) -> IngestDealsResult`), `application/use_cases/ingest_deals.py`, `adapters/inbound/http/{router.py,schemas.py,token_auth.py}`
- Test: `tests/unit/test_ingest_deals.py`, `tests/integration/test_bridge_api.py`

**Interfaces:**
- Consumes: Task 3 repos/use cases; journal `/ingest/deals` (Task 2).
- Produces: EA endpoints `POST /api/v1/mt5-bridge/ingest/deals` and `/ingest/heartbeat` (header `Authorization: Bearer <ingest token>`); user endpoints (JWT) `POST/GET/DELETE /api/v1/mt5-bridge/tokens`, `GET /api/v1/mt5-bridge/accounts`, `GET /api/v1/mt5-bridge/ea/download`. Deals body: `{account_login, server, deals:[RawDeal JSON, UTC ISO times]}`.

- [ ] **Step 1:** Write failing tests: `test_unknown_or_revoked_token_returns_401_and_stores_nothing`, `test_token_updates_last_used_at`, `test_deals_forwarded_with_token_owner_user_id`, `test_journal_down_returns_503`, `test_token_of_user_a_never_lists_or_writes_user_b`, `test_plaintext_token_never_in_logs` (caplog), `test_create_token_response_contains_plaintext_but_list_does_not`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement gateway, use case (updates `last_deal_at`), token-auth dependency (hash the bearer, `find_active_by_hash`), routers using the envelope; `ea/download` serves `ea/TradingJournalBridge.ex5` (404 `NOT_FOUND` until built).
- [ ] **Step 4:** Run `pytest services/mt5-bridge -q`, Ruff → PASS. Commit `feat(mt5-bridge): ingest and token API`.

### Task 5: Cross-service acceptance and docs

**Files:**
- Create: `tests/acceptance/test_ea_bridge_flow.py`
- Modify: `docs/services-catalog.md`, `docs/architecture.md`, `docs/CHANGELOG.md`, `docs/adr/0002-mt5-ea-bridge.md` (status accepted)

- [ ] **Step 1:** Write the failing acceptance test (existing acceptance suite style): register user → issue token → POST entry then exit deals with the token → `GET /journal/trades` shows one trade; resend both → still one; revoke token → 401 on the next push; a second user sees no trades.
- [ ] **Step 2:** Wire the new service into the acceptance fixtures; run `pytest tests -q -rs` (needs MongoDB) → PASS.
- [ ] **Step 3:** Update docs (EA marked built only after Task 7); commit `docs: mt5-bridge service and EA flow`.

### Task 6: Frontend — token, EA download and status UI

**Repo:** `trading-bot-frontend` (separate branch and PR). **Spec:** `trading-bot-frontend/specs/002-mt5-connection-ui/design.md` (read it first; add its `plan.md` there).

**Files:** Create `features/mt5-connection/api/bridge.ts`, extend its `stores/`, add token panel and account-status components; Modify `nuxt.config.ts` (`devProxy` `/api/v1/mt5-bridge` → `NUXT_BRIDGE_URL || http://localhost:8005`), `docs/features-catalog.md`; i18n en/es.

- [ ] **Step 1:** Write failing unit tests for the api mapper (snake_case → view types), the store (create token shows plaintext once, then clears) and the proxy entry.
- [ ] **Step 2:** Implement via `useApiClient`; UI: generate/revoke token (copy-once `AppModal`), EA download button, account list with connected / last seen / last deal, and an `AppEmptyState` with setup steps incl. the Allow WebRequest whitelist; available to all users (admin-only applies only to the legacy `mt5` link).
- [ ] **Step 3:** Run `npx vitest run`, `npx nuxi typecheck`, `npm run build` (dev server stopped). Commit `feat(mt5-connection): ingest token and EA bridge UI`.

### Task 7: The EA

**Files:**
- Create: `services/mt5-bridge/ea/TradingJournalBridge.mq5`, `services/mt5-bridge/ea/README.md` (install, whitelist URL, compile with MetaEditor), `services/mt5-bridge/ea/sample_payloads/deals.json`
- Test: `services/mt5-bridge/tests/unit/test_ea_contract.py`

**Interfaces:** Consumes the Task 4 request shapes; reuses only snippets approved in Task 1.

- [ ] **Step 1:** Write failing `test_ea_contract.py`: the fixture payloads the EA must send parse with the bridge request schemas (UTC ISO times, decimals as strings, `ticket` int).
- [ ] **Step 2:** Implement the EA: inputs `ApiUrl`, `IngestToken`; `OnTradeTransaction` sends the new deal; on init `HistorySelect` backfill in batches of 200; `OnTimer(60)` heartbeat; failed batches appended to a file queue and retried with exponential backoff (cap 5 min); never logs the token.
- [ ] **Step 3:** Owner compiles in MetaEditor to produce the `.ex5` (documented in `ea/README.md`). Commit `feat(mt5-bridge): MQL5 EA`.

### Task 8: End-to-end verification on a demo account (owner-run)

- [ ] **Step 1:** Run all services (`scripts/dev.ps1`), generate a token in the UI, install the EA on a demo account, whitelist `ApiUrl`.
- [ ] **Step 2:** Close a demo trade → it appears in the journal within seconds; restart MT5 and stop the API for a few minutes, close another trade, restart the API → no duplicates, no gaps; revoke the token → pushes rejected.
- [ ] **Step 3:** Set spec 002 `done`, write `specs/002-mt5-ea-bridge-sync/report.md`, update `specs/README.md`.

## Rulings

Deviations decided during execution: `Task N: <finding> — <decision> — <cost if wrong>`.

- Task 1: docs-only; controller verified the diff instead of a reviewer seat — accepted — cost: a wrong license note.
- Task 5: acceptance test placed in `tests/acceptance_services/` (existing suite), not `tests/acceptance/` — accepted — cost: none.
- Task 5 fix round: controller verified a doc line and 2 asserts by diff, no re-review seat — accepted — cost: a stale doc line.
- Task 3: DB name `bridge_db` (plan/brief) over `mt5_bridge_db` (older rules text), docs aligned — accepted — cost: rename if the owner prefers.
- Task 7: DST — accepted as a documented limitation for spec 002 (owner-only use; new deals use the correct current offset, only a backfill spanning a DST change is off by 1 h; manual `ServerUtcOffsetMinutes` override exists). Also, the old `mt5` service (DST-aware) and the EA write the same trade document, so use one path per account; if both run, the `mt5` service's times win only until the next EA push. The proper fix (a server-timezone rule like the mt5 service's ZoneConverter, ideally converted server-side) is a follow-up, listed in specs/README.md backlog — cost: hourly/daily stats of old backfilled deals skewed by 1 h until fixed.
- Task 7: 408/429/5xx-other-than-503 retried rather than dropped; zero-volume BUY/SELL skipped client-side — accepted — cost: none expected.

