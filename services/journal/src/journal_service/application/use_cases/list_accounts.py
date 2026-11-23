from journal_service.application.ports.repositories import AccountSummary, TradeRepository


class ListAccounts:
    def __init__(self, trades: TradeRepository) -> None:
        self._trades = trades

    async def execute(self, user_id: str) -> list[AccountSummary]:
        return await self._trades.accounts(user_id)
