# 0004 — MT5 terminal adapter

- **Status:** accepted
- **Date:** 2026-11-24
- **Spec:** `specs/001-service-migration/` (plan 3)

## Context

The owner needs real MT5 data in the journal before the EA bridge ([ADR 0002](0002-mt5-ea-bridge.md),
spec 002) exists. Options for the interim:

1. **Attach to the terminal already open and logged in** on the host, through the official
   `MetaTrader5` Python package.
2. Log in from our service with broker credentials.
3. Wait for the EA bridge.

The package only works on Windows with a running terminal. Option 2 means storing broker passwords,
which ADR 0002 rules out.

## Decision

Option 1, as a new `mt5` service (port 8004, `mt5_db`) and the first adapter behind a broker port.
It never receives or stores credentials: it only reads the account the terminal is logged in to
(initialize without login). Link, sync and unlink are admin-only. Closed trades are sent to the
journal ingest endpoint with a service key (`INGEST_SERVICE_KEY`, shared with journal). The service
also serves candles (`/rates`). ADR 0002 still stands: the EA bridge remains the target for
multi-user, hosted use and becomes a second adapter in spec 002.

## Consequences

- Works today for the owner with no EA and no credentials stored.
- Windows host only, one account at a time (whatever the terminal has open); the terminal must be
  running and logged in, otherwise the API answers 409 `TERMINAL_NOT_AVAILABLE`.
- Admin-only, so it is not a multi-user feature.
- Terminal times are in broker server time: configure `MT5_SERVER_TIMEZONE` (IANA zone, DST aware,
  works on weekends); without it a single UTC offset (tick-detected or
  `MT5_SERVER_UTC_OFFSET_MINUTES`) is applied to the whole history, so DST changes can shift old
  timestamps by an hour.
- The adapter never launches the terminal: it probes running `terminal64.exe` processes first and
  attaches with `initialize(path=...)` only when exactly one runs (`MULTIPLE_TERMINALS` otherwise).
- Tests use a fake terminal; real-terminal tests carry the `live` marker and are deselected by default.
- Spec 002 adds the EA bridge as a second adapter behind the same port.
