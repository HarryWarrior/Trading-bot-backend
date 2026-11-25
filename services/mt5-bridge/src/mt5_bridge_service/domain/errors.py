"""Domain errors. Each carries a stable machine-readable ``code`` and an HTTP status hint."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400


class InvalidTokenName(DomainError):
    code = "INVALID_TOKEN_NAME"
    http_status = 400


class TokenNotFound(DomainError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self, token_id: str) -> None:
        super().__init__("Ingest token not found")
        self.token_id = token_id


class InvalidHeartbeat(DomainError):
    code = "INVALID_HEARTBEAT"
    http_status = 400


class InvalidIngestToken(DomainError):
    """Unknown, revoked or wrongly scoped ingest token. Never carries the token itself."""

    code = "UNAUTHENTICATED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("Invalid or revoked ingest token")


class InvalidDealBatch(DomainError):
    code = "INVALID_DEAL_BATCH"
    http_status = 422


class JournalUnavailable(DomainError):
    """Journal is down, timed out or refused our credentials: the EA keeps the batch and retries."""

    code = "JOURNAL_UNAVAILABLE"
    http_status = 503

    def __init__(self, reason: str = "Journal service is unavailable") -> None:
        super().__init__(reason)


class JournalRejected(DomainError):
    """Journal refused the batch itself (4xx): resending the same batch can never succeed."""

    code = "JOURNAL_REJECTED"
    http_status = 422

    def __init__(self, reason: str = "Journal rejected the deals", details: object = None) -> None:
        super().__init__(reason)
        self.details = details
