"""Domain errors. Each carries a stable machine-readable ``code``."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"


class InvalidItemName(DomainError):
    code = "INVALID_ITEM_NAME"
