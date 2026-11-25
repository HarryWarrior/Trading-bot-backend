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
