import pytest

from template_service.adapters.outbound.memory_item_repository import InMemoryItemRepository
from template_service.application.use_cases.create_item import CreateItem
from template_service.application.use_cases.list_items import ListItems
from trading_shared.envelope import PageParams

pytestmark = pytest.mark.asyncio


async def test_list_items_isolated_by_user():
    repository = InMemoryItemRepository()
    create = CreateItem(repository)
    await create.execute("user-a", "EURUSD")
    await create.execute("user-a", "GBPUSD")
    await create.execute("user-b", "XAUUSD")

    list_items = ListItems(repository)
    _, total_a = await list_items.execute("user-a", PageParams())
    _, total_b = await list_items.execute("user-b", PageParams())

    assert total_a == 2
    assert total_b == 1


async def test_list_items_newest_first():
    repository = InMemoryItemRepository()
    create = CreateItem(repository)
    await create.execute("user-a", "first")
    await create.execute("user-a", "second")

    items, _ = await ListItems(repository).execute("user-a", PageParams())

    assert [item.name for item in items] == ["second", "first"]
