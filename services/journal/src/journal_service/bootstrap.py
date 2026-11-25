"""Composition root: the only place that knows which adapter implements which port."""

from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorClient

from journal_service.adapters.outbound.mongo_repositories import (
    MongoBalanceRepository,
    MongoImportRepository,
    MongoTradeRepository,
)
from journal_service.adapters.outbound.parsers.dispatcher import DispatchingReportParser
from journal_service.adapters.outbound.parsers.flat_csv import FlatCsvParser
from journal_service.adapters.outbound.parsers.mt5_report import Mt5ReportParser
from journal_service.adapters.outbound.system_clock import SystemClock
from journal_service.adapters.outbound.uuid_ids import UuidIdGenerator
from journal_service.application.use_cases.get_dataset import GetDataset
from journal_service.application.use_cases.get_trade import GetTrade
from journal_service.application.use_cases.import_report import ImportReport
from journal_service.application.use_cases.ingest_mt5_history import IngestMt5History
from journal_service.application.use_cases.list_accounts import ListAccounts
from journal_service.application.use_cases.list_imports import ListImports
from journal_service.application.use_cases.list_trades import ListTrades
from journal_service.settings import JournalSettings
from trading_shared.mongo import create_mongo_client


@dataclass(frozen=True)
class Container:
    settings: JournalSettings
    mongo_client: AsyncIOMotorClient
    repositories: tuple
    import_report: ImportReport
    ingest_mt5: IngestMt5History
    list_imports: ListImports
    list_trades: ListTrades
    get_trade: GetTrade
    list_accounts: ListAccounts
    get_dataset: GetDataset

    async def create_indexes(self) -> None:
        for repository in self.repositories:
            await repository.create_indexes()

    def close(self) -> None:
        self.mongo_client.close()


def build_container(settings: JournalSettings) -> Container:
    client = create_mongo_client(settings.mongodb_url)
    db = client[settings.database_name]
    trades = MongoTradeRepository(db)
    balances = MongoBalanceRepository(db)
    imports = MongoImportRepository(db)
    parser = DispatchingReportParser([Mt5ReportParser(), FlatCsvParser()])
    clock = SystemClock()
    ids = UuidIdGenerator()
    return Container(
        settings=settings,
        mongo_client=client,
        repositories=(trades, balances, imports),
        import_report=ImportReport(parser, trades, balances, imports, clock, ids),
        ingest_mt5=IngestMt5History(trades, balances, ids),
        list_imports=ListImports(imports),
        list_trades=ListTrades(trades),
        get_trade=GetTrade(trades),
        list_accounts=ListAccounts(trades),
        get_dataset=GetDataset(trades, balances),
    )
