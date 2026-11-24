"""Live checks against the real MetaTrader 5 terminal. Run with a logged-in terminal open:

    pytest -m live services/mt5/tests/live

Deselected by default. Each test skips itself when the terminal is not available.
"""

import pytest

from mt5_service.adapters.outbound.mt5_terminal import MetaTrader5TerminalAdapter
from mt5_service.domain.errors import TerminalNotAvailable

pytestmark = pytest.mark.live


@pytest.fixture
async def terminal():
    adapter = MetaTrader5TerminalAdapter()
    try:
        await adapter.current_account()
    except TerminalNotAvailable as exc:
        pytest.skip(f"MetaTrader 5 terminal not available: {exc}")
    yield adapter
    await adapter.close()


async def test_live_account(terminal):
    account = await terminal.current_account()
    assert account.login > 0 and account.server
    assert account.trade_mode in ("demo", "contest", "real")


async def test_live_history_deals_are_naive_server_time(terminal):
    deals = await terminal.history_deals()
    assert all(d.time_server.tzinfo is None for d in deals)


async def test_live_rates_for_a_market_watch_symbol(terminal):
    import MetaTrader5 as mt5

    visible = [s.name for s in (mt5.symbols_get() or ()) if s.visible]
    if not visible:
        pytest.skip("no symbols in Market Watch")
    candles = await terminal.rates(visible[0], "M1", 5)
    assert candles and candles[0].time.tzinfo is None
