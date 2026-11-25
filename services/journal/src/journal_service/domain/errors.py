"""Domain errors. Each carries a stable machine-readable ``code`` and an HTTP status hint."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400


class DuplicateImport(DomainError):
    code = "DUPLICATE_IMPORT"
    http_status = 409

    def __init__(self, import_id: str) -> None:
        super().__init__(f"This file was already imported (import {import_id})")
        self.import_id = import_id


class TradeNotFound(DomainError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self, trade_id: str) -> None:
        super().__init__("Trade not found")
        self.trade_id = trade_id


class UnreadableReport(DomainError):
    code = "UNREADABLE_REPORT"
    http_status = 400

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
