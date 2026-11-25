"""Random uuid4-hex id generator for the IdGenerator port."""

import uuid


class UuidIdGenerator:
    def new_id(self) -> str:
        return uuid.uuid4().hex
