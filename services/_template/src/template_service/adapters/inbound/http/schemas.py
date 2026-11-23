from datetime import datetime

from pydantic import BaseModel

from template_service.domain.item import Item


class CreateItemRequest(BaseModel):
    name: str


class ItemOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, item: Item) -> "ItemOut":
        return cls(id=item.id, name=item.name, created_at=item.created_at)
