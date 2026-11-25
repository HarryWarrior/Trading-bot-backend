"""Composition root: the only place that knows which adapter implements which port."""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient

from mt5_bridge_service.adapters.outbound.journal_gateway import JournalHttpGateway
from mt5_bridge_service.adapters.outbound.mongo_accounts import MongoAccountRepository
from mt5_bridge_service.adapters.outbound.mongo_tokens import MongoTokenRepository
from mt5_bridge_service.adapters.outbound.system_clock import SystemClock
from mt5_bridge_service.adapters.outbound.uuid_ids import UuidIdGenerator
from mt5_bridge_service.application.ports.accounts import AccountRepository
from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.application.ports.journal import JournalGateway
from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.application.use_cases.authenticate_token import AuthenticateIngestToken
from mt5_bridge_service.application.use_cases.ingest_deals import IngestDeals
from mt5_bridge_service.application.use_cases.issue_token import IssueIngestToken
from mt5_bridge_service.application.use_cases.list_accounts import ListAccounts
from mt5_bridge_service.application.use_cases.list_tokens import ListIngestTokens
from mt5_bridge_service.application.use_cases.record_heartbeat import RecordHeartbeat
from mt5_bridge_service.application.use_cases.revoke_token import RevokeIngestToken
from mt5_bridge_service.settings import BridgeSettings
from trading_shared.mongo import create_mongo_client


@dataclass(frozen=True)
class Container:
    settings: BridgeSettings
    mongo_client: AsyncIOMotorClient | None
    tokens: TokenRepository
    accounts: AccountRepository
    issue_token: IssueIngestToken
    revoke_token: RevokeIngestToken
    list_tokens: ListIngestTokens
    authenticate_token: AuthenticateIngestToken
    record_heartbeat: RecordHeartbeat
    list_accounts: ListAccounts
    ingest_deals: IngestDeals

    async def create_indexes(self) -> None:
        # In-memory test doubles have no indexes to build.
        for repository in (self.tokens, self.accounts):
            create = getattr(repository, "create_indexes", None)
            if create is not None:
                await create()

    def close(self) -> None:
        if self.mongo_client is not None:
            self.mongo_client.close()


def build_container(
    settings: BridgeSettings,
    journal: JournalGateway | None = None,
    tokens: TokenRepository | None = None,
    accounts: AccountRepository | None = None,
    clock: Clock | None = None,
) -> Container:
    client = None
    if tokens is None or accounts is None:
        client = create_mongo_client(settings.mongodb_url)
        db = client[settings.database_name]
        tokens = tokens or MongoTokenRepository(db)
        accounts = accounts or MongoAccountRepository(db)
    journal = journal or JournalHttpGateway(
        settings.journal_url,
        settings.ingest_service_key.get_secret_value(),
        timeout=settings.journal_timeout_seconds,
    )
    clock = clock or SystemClock()
    ids = UuidIdGenerator()
    return Container(
        settings=settings,
        mongo_client=client,
        tokens=tokens,
        accounts=accounts,
        issue_token=IssueIngestToken(tokens, clock, ids),
        revoke_token=RevokeIngestToken(tokens, clock),
        list_tokens=ListIngestTokens(tokens),
        authenticate_token=AuthenticateIngestToken(tokens, clock),
        record_heartbeat=RecordHeartbeat(accounts, clock),
        list_accounts=ListAccounts(accounts, clock),
        ingest_deals=IngestDeals(journal, accounts),
    )
