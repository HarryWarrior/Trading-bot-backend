"""Item entity: the sample aggregate of the template. Replace it with the real domain."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from template_service.domain.errors import InvalidItemName

MAX_NAME_LENGTH = 100


@dataclass(frozen=True)
class Item:
    id: str
    user_id: str
    name: str
    created_at: datetime

    @classmethod
    def create(cls, user_id: str, name: str) -> "Item":
        """Create a new item owned by ``user_id``.

        Raises:
            InvalidItemName: If the stripped name is empty or longer than 100 characters.
        """
        clean_name = name.strip()
        if not clean_name or len(clean_name) > MAX_NAME_LENGTH:
            raise InvalidItemName(f"Item name must be 1-{MAX_NAME_LENGTH} characters.")
        return cls(id=uuid4().hex, user_id=user_id, name=clean_name, created_at=datetime.now(UTC))
