# 003 — Strategy → backtest → paper → live bot (design)

- **Status:** draft
- **Date:** 2026-11-23
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/003-strategies-ui/design.md`
- **Services touched:** new `strategies`, `backtester`, `execution`; `mt5-bridge` (command channel)
- **Depends on:** 001, 002

## 1. Intent

A trader (or the owner) defines a strategy, backtests it on historical data, runs it on paper in real
time, and — only after passing explicit gates — deploys it with real money, all from the same platform.

## 2. Goals, non-goals, anti-goals

**Goals**
- Strategy definitions versioned per user (code-based first; parameters editable).
- Backtests with standard metrics (reuse analytics KPIs) and equity curve, stored per run.
- Paper trading with the same strategy code and live market data.
- **Promotion gate** paper → live: minimum paper period/trades and explicit user confirmation.
- **Risk limits per strategy**: max daily loss, max position size, max open positions.
- **Global kill switch** per user that flattens/halts all live strategies.
- Live execution through a `BrokerGateway` port: MT5 via EA bridge commands first, IBKR later.

**Non-goals** — visual strategy builder, marketplace, copy-trading for third parties (later specs).

**Anti-goals** — backtest and live using different code paths (results not comparable); any live order
without risk checks; silent failures in live trading.

## 3. Constraints

- Same strategy code must run in backtest, paper and live (engine choice decides how).
- Live trading is opt-in per strategy and per account; every order is logged and journaled.
- No personalized financial advice in product copy.

## 4. Research (first task of the plan)

| Candidate | Strength | Verdict |
|---|---|---|
| backtesting.py | Simple, fast to adopt, good for single-asset | TBD |
| vectorbt | Very fast vectorized research, parameter sweeps | TBD |
| backtrader | Mature, event-driven, live brokers via plugins | TBD |
| NautilusTrader | Same code for backtest and live, production-grade, adapters (IBKR…) | TBD |
| QuantConnect Lean | Full platform, multi-asset; heavier (C#/Python) | TBD |

Criteria: same-code backtest/live, license for SaaS, Python fit, MT5 adapter feasibility, performance,
community. Record in `docs/integrations/README.md`.

## 5. Approaches

1. Adopt one engine for backtest **and** live (e.g. NautilusTrader) behind our ports.
2. Research engine for backtest (vectorbt) + own lightweight live runner. Simpler start, risk of drift.
Decision after research.

## 6. Design sketch

- `strategies`: `Strategy`, `StrategyVersion`, parameters schema.
- `backtester`: `BacktestRun` (strategy version, symbol(s), period, costs model, results); worker
  process; ports `MarketDataSource`, `BacktestEngine`.
- `execution`: `Deployment` (mode paper|live, account, risk limits, state), `RiskCheck`, `KillSwitch`;
  ports `BrokerGateway`, `MarketDataFeed`, `JournalGateway`.
- MT5 live orders: `execution` → `mt5-bridge` command queue → EA polls/receives and executes →
  result back as deals (002 path).

## 7. Open questions

- First markets: FX/CFDs/gold on MT5 only, or also stocks/futures (IBKR)?
- Who writes strategies: only the owner (code) at first, or end users too (needs sandboxing)?
- Historical data source for backtests (broker history via EA, vendor, both)?

## 8. Done when

A sample strategy backtests, runs on paper, passes the gate and trades a demo MT5 account live with
risk limits enforced and the kill switch tested.
