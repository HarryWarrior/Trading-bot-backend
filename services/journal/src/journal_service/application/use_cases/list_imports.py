from journal_service.application.ports.repositories import ImportRepository
from journal_service.domain.report_import import ReportImport
from trading_shared.envelope import PageParams


class ListImports:
    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    async def execute(self, user_id: str, params: PageParams) -> tuple[list[ReportImport], int]:
        return await self._imports.list(user_id, params.page, params.page_size)
