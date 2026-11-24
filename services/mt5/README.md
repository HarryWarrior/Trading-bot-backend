# mt5 service

Links the account of the MetaTrader 5 terminal running on this machine, syncs its CLOSED trades
and balance events to the `journal` service, and serves real candles. Prefix `/api/v1/mt5`.

Nothing is simulated and no broker password is ever accepted or stored: the account is whatever the
running terminal reports (`login@server`). When the terminal is not running, not logged in or on
another account the API answers with an error code (`TERMINAL_NOT_AVAILABLE`,
`TERMINAL_ACCOUNT_MISMATCH`).

Status: domain and use cases are built (task 1); the MT5 adapter, journal client, storage and HTTP
routes follow in later tasks.

## Rules implemented in the domain

- Deal times are broker server time. `offset = round_to_30min(latest_tick_server - utc_now)`;
  stored/returned times are tz-aware UTC.
- Deals are grouped by `position_id`. Side = side of the IN deal, volume = sum of IN volumes, close
  price = volume-weighted exit price, close time = last exit, profit/commission/swap/fee summed
  (fee is folded into commission because journal has no fee field). Only fully closed positions
  become trades; open ones are counted.
- Positions containing an INOUT (reversal) deal are NOT supported yet: they are skipped and reported
  in `skipped_positions` with a reason, never guessed.
- Balance-type deals: BALANCE -> deposit/withdrawal by sign, CREDIT -> credit, every other non-trade
  type -> adjustment (profit + commission + swap + fee). BUY_CANCELED / SELL_CANCELED are ignored.

## Run and test

```bash
pip install -e libs/shared -e "services/mt5[dev]"
pytest services/mt5/tests -q -W error
```
