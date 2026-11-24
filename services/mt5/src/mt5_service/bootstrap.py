"""Composition root: the only place that knows which adapter implements which port.

The default terminal is the MetaTrader5 adapter, whose package is imported lazily: building the
container never contacts the terminal. Tests inject fakes for the terminal, journal and accounts.
"""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient

from mt5_service.adapters.outbound.journal_gateway import JournalHttpGateway
from mt5_service.adapters.outbound.mongo_accounts import MongoLinkedAccountRepository
from mt5_service.adapters.outbound.mt5_terminal import MetaTrader5TerminalAdapter
from mt5_service.adapters.outbound.system_clock import SystemClock
from mt5_service.adapters.outbound.uuid_ids import UuidIdGenerator
from mt5_service.application.ports.clock import Clock
from mt5_service.application.ports.journal import JournalGateway
from mt5_service.application.ports.repositories import LinkedAccountRepository
from mt5_service.application.ports.terminal import BrokerTerminal
from mt5_service.application.use_cases.get_rates import GetRates
from mt5_service.application.use_cases.get_status import GetStatus
from mt5_service.application.use_cases.link_account import LinkAccount
from mt5_service.application.use_cases.list_accounts import ListAccounts
from mt5_service.application.use_cases.sync_account import SyncAccount
from mt5_service.application.use_cases.unlink_account import UnlinkAccount
from mt5_service.settings import Mt5Settings
from trading_shared.mongo import create_mongo_client


@dataclass(frozen=True)
class Container:
    settings: Mt5Settings
    mongo_client: AsyncIOMotorClient | None
    accounts: LinkedAccountRepository
    link_account: LinkAccount
    list_accounts: ListAccounts
    get_status: GetStatus
    sync_account: SyncAccount
    unlink_account: UnlinkAccount
    get_rates: GetRates

    async def create_indexes(self) -> None:
        create = getattr(self.accounts, "create_indexes", None)
        if create is not None:
            await create()

    def close(self) -> None:
        if self.mongo_client is not None:
            self.mongo_client.close()


def build_container(
    settings: Mt5Settings,
    terminal: BrokerTerminal | None = None,
    journal: JournalGateway | None = None,
    accounts: LinkedAccountRepository | None = None,
    clock: Clock | None = None,
) -> Container:
    client = None
    if accounts is None:
        client = create_mongo_client(settings.mongodb_url)
        accounts = MongoLinkedAccountRepository(client[settings.database_name])
    terminal = terminal or MetaTrader5TerminalAdapter()
    journal = journal or JournalHttpGateway(
        settings.journal_url, settings.ingest_service_key.get_secret_value()
    )
    clock = clock or SystemClock()
    offset = settings.server_utc_offset_minutes
    return Container(
        settings=settings,
        mongo_client=client,
        accounts=accounts,
        link_account=LinkAccount(terminal, accounts, clock, UuidIdGenerator()),
        list_accounts=ListAccounts(accounts),
        get_status=GetStatus(terminal, accounts, clock),
        sync_account=SyncAccount(terminal, journal, accounts, clock, offset),
        unlink_account=UnlinkAccount(accounts),
        get_rates=GetRates(terminal, clock, offset),
    )
