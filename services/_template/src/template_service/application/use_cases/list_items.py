from template_service.application.ports.item_repository import ItemRepository
from template_service.domain.item import Item
from trading_shared.envelope import PageParams


class ListItems:
    def __init__(self, repository: ItemRepository):
        self._repository = repository

    async def execute(self, user_id: str, params: PageParams) -> tuple[list[Item], int]:
        return await self._repository.list_by_user(user_id, params.page, params.page_size)
