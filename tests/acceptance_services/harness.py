"""Cross-service acceptance harness: the four REAL apps in one event loop, no ports, no MetaTrader.

auth, journal, analytics and mt5 are the production ``create_app`` factories. They are wired to each
other through ``httpx.ASGITransport`` (journal is the only one the others call), run on throwaway
MongoDB databases, and mt5 gets a ``FakeTerminal`` (defined in the mt5 test helpers) instead of the
MetaTrader5 package, so no real terminal is ever contacted. A test skips only when MongoDB is not
reachable.

Lifespans are entered with ``router.lifespan_context`` so every app (and Motor) shares one loop.
"""

from __future__ import annotations

import sys
import uuid
import warnings
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "mt5" / "tests"))  # FakeTerminal and builders

# starlette 0.27 imports the legacy `multipart` alias, which python-multipart >= 0.0.13 flags.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import multipart  # noqa: F401

from mt5_fakes import FakeTerminal, FixedClock, terminal_account  # noqa: E402

from analytics_service.adapters.outbound.journal_client import JournalHttpTradeSource  # noqa: E402
from analytics_service.main import create_app as create_analytics_app  # noqa: E402
from analytics_service.settings import AnalyticsSettings  # noqa: E402
from auth_service.application.use_cases.promote_to_admin import PromoteToAdmin  # noqa: E402
from auth_service.main import create_app as create_auth_app  # noqa: E402
from auth_service.settings import AuthSettings  # noqa: E402
from journal_service.main import create_app as create_journal_app  # noqa: E402
from journal_service.settings import JournalSettings  # noqa: E402
from mt5_service.adapters.outbound.journal_gateway import JournalHttpGateway  # noqa: E402
from mt5_service.main import create_app as create_mt5_app  # noqa: E402
from mt5_service.settings import Mt5Settings  # noqa: E402

MONGO_URL = "mongodb://localhost:27017"
SECRET = "acceptance-secret-key-with-enough-length-0123456789"
SERVICE_KEY = "acceptance-ingest-service-key-with-enough-length-0123456789"
PASSWORD = "AcceptancePass123!"
SAMPLE = ROOT / "data" / "samples" / "sample_trades.csv"

AUTH = "/api/v1/auth"
JOURNAL = "/api/v1/journal"
ANALYTICS = "/api/v1/analytics"
MT5 = "/api/v1/mt5"


class RecordingEmailSender:
    """Captures what would be emailed: the only place a verification code is ever visible."""

    def __init__(self) -> None:
        self.verifications: list[tuple[str, str]] = []
        self.resets: list[tuple[str, str]] = []

    async def send_verification(self, email: str, code: str) -> None:
        self.verifications.append((email, code))

    async def send_password_reset(self, email: str, token: str) -> None:
        self.resets.append((email, token))

    def last_code(self, email: str) -> str:
        return next(code for address, code in reversed(self.verifications) if address == email)


@dataclass
class Session:
    email: str
    access_token: str
    refresh_token: str
    user_id: str
    role: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@dataclass
class Stack:
    auth: httpx.AsyncClient
    journal: httpx.AsyncClient
    analytics: httpx.AsyncClient
    mt5: httpx.AsyncClient
    sender: RecordingEmailSender
    terminal: FakeTerminal
    mongo: MongoClient
    databases: dict[str, str]
    auth_app: object
    _counter: list[int] = field(default_factory=lambda: [0])

    def new_email(self) -> str:
        self._counter[0] += 1
        return f"user{self._counter[0]}-{uuid.uuid4().hex[:6]}@acceptance-tests.com"

    async def sign_up(self, email: str | None = None) -> str:
        email = email or self.new_email()
        response = await self.auth.post(
            f"{AUTH}/sign-up", json={"email": email, "password": PASSWORD, "name": "Acceptance"}
        )
        assert response.status_code == 201, response.text
        return email

    async def sign_in(self, email: str) -> Session:
        response = await self.auth.post(
            f"{AUTH}/sign-in", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        return Session(
            email=email,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            user_id=data["user"]["id"],
            role=data["user"]["role"],
        )

    async def register(self, *, admin: bool = False) -> Session:
        """Sign up, verify with the emailed code, optionally promote to admin, sign in."""
        email = await self.sign_up()
        verified = await self.auth.post(
            f"{AUTH}/verify-email", json={"email": email, "code": self.sender.last_code(email)}
        )
        assert verified.status_code == 200, verified.text
        if admin:
            users = self.auth_app.state.container.repositories[0]
            await PromoteToAdmin(users).execute(email)
        return await self.sign_in(email)

    async def upload(self, session: Session, name: str, content: bytes) -> httpx.Response:
        return await self.journal.post(
            f"{JOURNAL}/imports",
            files={"file": (name, content, "text/csv")},
            headers=session.headers,
        )

    async def summary(self, session: Session) -> dict:
        response = await self.analytics.get(f"{ANALYTICS}/summary", headers=session.headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]["summary"]


@pytest.fixture
def databases():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    suffix = uuid.uuid4().hex
    names = {kind: f"test_acceptance_{kind}_{suffix}" for kind in ("auth", "journal", "mt5")}
    try:
        yield names, client
    finally:
        for name in names.values():
            client.drop_database(name)
        client.close()


@pytest.fixture
async def stack(databases) -> AsyncIterator[Stack]:
    names, mongo = databases
    sender = RecordingEmailSender()
    terminal = FakeTerminal(terminal_account())

    auth_app = create_auth_app(
        AuthSettings(
            _env_file=None,
            environment="test",
            mongodb_url=MONGO_URL,
            database_name=names["auth"],
            jwt_secret_key=SECRET,
        ),
        email_sender=sender,
    )
    journal_app = create_journal_app(
        JournalSettings(
            _env_file=None,
            environment="test",
            mongodb_url=MONGO_URL,
            database_name=names["journal"],
            jwt_secret_key=SECRET,
            ingest_service_key=SERVICE_KEY,
        )
    )
    journal_transport = httpx.ASGITransport(app=journal_app)
    analytics_app = create_analytics_app(
        AnalyticsSettings(_env_file=None, environment="test", jwt_secret_key=SECRET),
        trade_source=JournalHttpTradeSource("http://journal.test", transport=journal_transport),
    )
    mt5_app = create_mt5_app(
        Mt5Settings(
            _env_file=None,
            environment="test",
            mongodb_url=MONGO_URL,
            database_name=names["mt5"],
            jwt_secret_key=SECRET,
            ingest_service_key=SERVICE_KEY,
        ),
        terminal=terminal,
        clock=FixedClock(),  # matches the FakeTerminal tick (+3h broker offset)
        journal=JournalHttpGateway("http://journal.test", SERVICE_KEY, transport=journal_transport),
    )

    async with AsyncExitStack() as exit_stack:
        for app in (auth_app, journal_app, mt5_app):
            await exit_stack.enter_async_context(app.router.lifespan_context(app))

        def client(app, name: str) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=f"http://{name}.test"
            )

        clients = {
            "auth": client(auth_app, "auth"),
            "journal": client(journal_app, "journal"),
            "analytics": client(analytics_app, "analytics"),
            "mt5": client(mt5_app, "mt5"),
        }
        for opened in clients.values():
            await exit_stack.enter_async_context(opened)
        yield Stack(
            **clients,
            sender=sender,
            terminal=terminal,
            mongo=mongo,
            databases=names,
            auth_app=auth_app,
        )
