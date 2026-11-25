"""Composition root: the only place that knows which adapter implements which port."""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient

from mt5_bridge_service.adapters.outbound.mongo_accounts import MongoAccountRepository
from mt5_bridge_service.adapters.outbound.mongo_tokens import MongoTokenRepository
from mt5_bridge_service.adapters.outbound.system_clock import SystemClock
from mt5_bridge_service.adapters.outbound.uuid_ids import UuidIdGenerator
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
    mongo_client: AsyncIOMotorClient
    tokens: MongoTokenRepository
    accounts: MongoAccountRepository
    issue_token: IssueIngestToken
    revoke_token: RevokeIngestToken
    list_tokens: ListIngestTokens
    record_heartbeat: RecordHeartbeat
    list_accounts: ListAccounts

    async def create_indexes(self) -> None:
        await self.tokens.create_indexes()
        await self.accounts.create_indexes()

    def close(self) -> None:
        self.mongo_client.close()


def build_container(settings: BridgeSettings) -> Container:
    client = create_mongo_client(settings.mongodb_url)
    db = client[settings.database_name]
    tokens = MongoTokenRepository(db)
    accounts = MongoAccountRepository(db)
    clock = SystemClock()
    ids = UuidIdGenerator()
    return Container(
        settings=settings,
        mongo_client=client,
        tokens=tokens,
        accounts=accounts,
        issue_token=IssueIngestToken(tokens, clock, ids),
        revoke_token=RevokeIngestToken(tokens, clock),
        list_tokens=ListIngestTokens(tokens),
        record_heartbeat=RecordHeartbeat(accounts, clock),
        list_accounts=ListAccounts(accounts, clock),
    )
