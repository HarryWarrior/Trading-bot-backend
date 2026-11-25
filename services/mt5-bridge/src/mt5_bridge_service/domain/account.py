"""Broker accounts seen through the EA heartbeat. There is deliberately no password field."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from mt5_bridge_service.domain.errors import InvalidHeartbeat

# The EA beats every 60 s; five missed beats mean the terminal (or the EA) is gone.
HEARTBEAT_TIMEOUT = timedelta(minutes=5)


class AccountStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


def account_ref(login: int, server: str) -> str:
    """Identity of an MT5 account, identical to the one journal and the mt5 service use."""
    return f"{login}@{server}"


@dataclass(frozen=True)
class Heartbeat:
    """What the EA reports every minute."""

    login: int
    server: str
    balance: Decimal
    equity: Decimal
    terminal_build: int | None = None


@dataclass(frozen=True)
class BrokerAccount:
    user_id: str
    account_ref: str
    login: int
    server: str
    balance: Decimal
    equity: Decimal
    last_heartbeat: datetime | None
    last_deal_at: datetime | None
    terminal_build: int | None = None

    def __post_init__(self) -> None:
        for name in ("last_heartbeat", "last_deal_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")

    def status(self, now: datetime) -> AccountStatus:
        if self.last_heartbeat is not None and now - self.last_heartbeat <= HEARTBEAT_TIMEOUT:
            return AccountStatus.CONNECTED
        return AccountStatus.DISCONNECTED

    @classmethod
    def from_heartbeat(cls, user_id: str, heartbeat: Heartbeat, at: datetime) -> "BrokerAccount":
        """Build the account state a heartbeat received at ``at`` describes.

        Raises:
            InvalidHeartbeat: If the login is not positive or the server is blank.
        """
        server = heartbeat.server.strip()
        if heartbeat.login <= 0 or not server:
            raise InvalidHeartbeat("Heartbeat needs a positive login and a server name.")
        return cls(
            user_id=user_id,
            account_ref=account_ref(heartbeat.login, server),
            login=heartbeat.login,
            server=server,
            balance=heartbeat.balance,
            equity=heartbeat.equity,
            last_heartbeat=at,
            last_deal_at=None,
            terminal_build=heartbeat.terminal_build,
        )
