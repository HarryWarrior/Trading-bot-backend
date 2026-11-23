# 0002 — MT5 connectivity through an EA bridge

- **Status:** accepted
- **Date:** 2026-11-23
- **Spec:** `specs/002-mt5-ea-bridge-sync/`

## Context

Journals must fill automatically from executions; manual uploads do not work for users. The official
`MetaTrader5` Python package only runs on Windows with a terminal logged in to one account at a time,
which does not scale to many users and requires storing broker passwords. Options:

1. **EA bridge** — an Expert Advisor in the user's own terminal pushes executions to our API.
2. Windows workers running terminals with users' investor passwords.
3. Third-party cloud bridge (e.g. MetaApi), paid per account.

## Decision

Option 1. The user installs our EA in MT5 and pastes a per-user **ingest token**. The EA sends deals
(`OnTradeTransaction`), history backfill and heartbeats via `WebRequest` to the `mt5-bridge` service.
We never store broker passwords. Options 2–3 remain possible later as additional adapters behind the
same port.

## Consequences

- Scales to many users at near-zero infrastructure cost; strong security posture.
- Requires a one-time setup by the user (allow WebRequest URL, attach EA) — the UI must guide it.
- Data arrives only while the user's terminal runs; backfill on reconnect covers gaps.
- Live order execution (spec 003) can reuse the bridge as a command channel.
- Legacy `app/` MT5 code (password storage, simulated deals) is removed in spec 001/002.
