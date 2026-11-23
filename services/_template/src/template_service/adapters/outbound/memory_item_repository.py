"""In-memory ItemRepository. Swap for a Mongo adapter when the service needs persistence."""

from template_service.domain.item import Item


class InMemoryItemRepository:
    def __init__(self) -> None:
        self._items: list[Item] = []

    async def add(self, item: Item) -> None:
        self._items.append(item)

    async def list_by_user(self, user_id: str, page: int, page_size: int) -> tuple[list[Item], int]:
        owned = [item for item in reversed(self._items) if item.user_id == user_id]
        start = (page - 1) * page_size
        return owned[start : start + page_size], len(owned)
