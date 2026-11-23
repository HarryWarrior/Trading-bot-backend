"""Composition root: the only place that knows which adapter implements which port."""

from dataclasses import dataclass

from template_service.adapters.outbound.memory_item_repository import InMemoryItemRepository
from template_service.application.use_cases.create_item import CreateItem
from template_service.application.use_cases.list_items import ListItems
from template_service.settings import TemplateSettings


@dataclass(frozen=True)
class Container:
    settings: TemplateSettings
    create_item: CreateItem
    list_items: ListItems


def build_container(settings: TemplateSettings) -> Container:
    repository = InMemoryItemRepository()
    return Container(
        settings=settings,
        create_item=CreateItem(repository),
        list_items=ListItems(repository),
    )
