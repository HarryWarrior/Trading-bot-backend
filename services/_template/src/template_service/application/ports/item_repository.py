"""Outbound port: persistence of items. Adapters implement this Protocol."""

from typing import Protocol

from template_service.domain.item import Item


class ItemRepository(Protocol):
    async def add(self, item: Item) -> None: ...

    async def list_by_user(self, user_id: str, page: int, page_size: int) -> tuple[list[Item], int]:
        """Return one page of the user's items, newest first, and the user's total count."""
        ...
