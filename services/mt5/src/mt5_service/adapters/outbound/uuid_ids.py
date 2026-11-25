import uuid


class UuidIdGenerator:
    def new_id(self) -> str:
        return uuid.uuid4().hex
