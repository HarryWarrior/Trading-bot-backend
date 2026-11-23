from template_service.application.ports.item_repository import ItemRepository
from template_service.domain.item import Item


class CreateItem:
    def __init__(self, repository: ItemRepository):
        self._repository = repository

    async def execute(self, user_id: str, name: str) -> Item:
        item = Item.create(user_id, name)
        await self._repository.add(item)
        return item
