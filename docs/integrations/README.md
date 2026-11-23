# Integrations research log

Before building a tool from scratch, look for a proven open-source project or API. Record every
evaluation here (accepted or rejected) so nobody repeats it.

**Criteria:** license compatible with SaaS use · maintained (recent releases, issues answered) ·
fits our stack (Python service or language-agnostic API) · works multi-user · cost · security.

## Evaluated

| Name | URL | License | Purpose | Verdict | Spec | Date |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |

## Candidates to evaluate

| Area | Candidates | Spec |
|---|---|---|
| MT5 EA bridge (MQL5 `WebRequest`/socket bridges, trade copiers) | Open-source MT5 bridge EAs and REST/ZeroMQ bridges on GitHub | 002 |
| Cloud MT5 access (fallback adapter) | MetaApi | 002 |
| Backtesting engines | backtesting.py, vectorbt, backtrader, NautilusTrader, QuantConnect Lean | 003 |
| Live execution | NautilusTrader adapters, Interactive Brokers API (`ib_async`) | 003 |
| Market data | Broker feeds via EA, free/paid data vendors | 003 |
| AI journaling | MCP Python SDK, Claude API | 004 |
