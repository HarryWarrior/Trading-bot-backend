from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mt5_bridge_service.domain.account import (
    HEARTBEAT_TIMEOUT,
    AccountStatus,
    BrokerAccount,
    Heartbeat,
    account_ref,
)
from mt5_bridge_service.domain.errors import InvalidHeartbeat

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _account(last_heartbeat: datetime | None) -> BrokerAccount:
    return BrokerAccount(
        user_id="u1",
        account_ref="123@Broker-Demo",
        login=123,
        server="Broker-Demo",
        balance=Decimal("1000"),
        equity=Decimal("1000"),
        last_heartbeat=last_heartbeat,
        last_deal_at=None,
    )


def test_status_connected_within_5_minutes_else_disconnected():
    assert HEARTBEAT_TIMEOUT == timedelta(minutes=5)
    assert _account(NOW).status(NOW) == AccountStatus.CONNECTED
    assert _account(NOW - timedelta(minutes=5)).status(NOW) == "connected"
    assert _account(NOW - timedelta(minutes=5, seconds=1)).status(NOW) == "disconnected"
    assert _account(None).status(NOW) == AccountStatus.DISCONNECTED


def test_account_ref_is_login_at_server():
    assert account_ref(123, "Broker-Demo") == "123@Broker-Demo"


def test_from_heartbeat_builds_account():
    hb = Heartbeat(
        login=123,
        server=" Broker-Demo ",
        balance=Decimal("10"),
        equity=Decimal("9"),
        terminal_build=4410,
    )

    account = BrokerAccount.from_heartbeat("u1", hb, NOW)

    assert account.account_ref == "123@Broker-Demo"
    assert account.server == "Broker-Demo"
    assert account.last_heartbeat == NOW
    assert account.terminal_build == 4410
    assert account.last_deal_at is None


@pytest.mark.parametrize(("login", "server"), [(0, "Srv"), (-1, "Srv"), (1, "  ")])
def test_from_heartbeat_rejects_invalid_identity(login, server):
    hb = Heartbeat(login=login, server=server, balance=Decimal(0), equity=Decimal(0))
    with pytest.raises(InvalidHeartbeat):
        BrokerAccount.from_heartbeat("u1", hb, NOW)


def test_naive_heartbeat_time_is_rejected():
    hb = Heartbeat(login=1, server="Srv", balance=Decimal(0), equity=Decimal(0))
    with pytest.raises(ValueError):
        BrokerAccount.from_heartbeat("u1", hb, datetime(2026, 1, 1))
