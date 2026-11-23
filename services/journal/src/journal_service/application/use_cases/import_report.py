import hashlib

from journal_service.application.ports.clock import Clock
from journal_service.application.ports.ids import IdGenerator
from journal_service.application.ports.parsing import ReportParser
from journal_service.application.ports.repositories import (
    BalanceRepository,
    ImportRepository,
    TradeRepository,
)
from journal_service.application.use_cases._build import build_balance_event, build_trade
from journal_service.domain.errors import DuplicateImport
from journal_service.domain.report_import import ReportImport


class ImportReport:
    def __init__(
        self,
        parser: ReportParser,
        trades: TradeRepository,
        balances: BalanceRepository,
        imports: ImportRepository,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._parser = parser
        self._trades = trades
        self._balances = balances
        self._imports = imports
        self._clock = clock
        self._ids = ids

    async def execute(self, user_id: str, filename: str, content: bytes) -> ReportImport:
        sha256 = hashlib.sha256(content).hexdigest()
        previous = await self._imports.find_by_sha(user_id, sha256)
        if previous is not None:
            raise DuplicateImport(previous.id)

        parsed = self._parser.parse(filename, content)
        import_id = self._ids.new_id()
        account = parsed.account
        account_ref = f"{account.login}@{account.server}" if account else f"upload:{import_id}"

        trades = [
            build_trade(
                t,
                user_id=user_id,
                account_ref=account_ref,
                source="report",
                import_id=import_id,
                ids=self._ids,
            )
            for t in parsed.trades
        ]
        events = [
            build_balance_event(e, user_id=user_id, account_ref=account_ref, ids=self._ids)
            for e in parsed.balance_events
        ]
        created, updated = await self._trades.upsert_many(user_id, trades)
        balance_count = await self._balances.upsert_many(user_id, events)

        report_import = ReportImport(
            id=import_id,
            user_id=user_id,
            filename=filename,
            sha256=sha256,
            account_ref=account_ref,
            trades_created=created,
            trades_updated=updated,
            balance_events=balance_count,
            skipped_rows=list(parsed.skipped_rows),
            created_at=self._clock.now(),
        )
        await self._imports.add(report_import)
        return report_import
