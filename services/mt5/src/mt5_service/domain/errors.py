"""Domain errors. Each carries a stable machine-readable ``code`` and an HTTP status hint."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400


class TerminalNotAvailable(DomainError):
    """The MT5 terminal is not running, not logged in, or the MetaTrader5 package is missing."""

    code = "TERMINAL_NOT_AVAILABLE"
    http_status = 409

    def __init__(self, reason: str = "MetaTrader 5 terminal is not available") -> None:
        super().__init__(reason)
        self.reason = reason


class TerminalAccountMismatch(DomainError):
    code = "TERMINAL_ACCOUNT_MISMATCH"
    http_status = 409

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"The terminal is logged in to {actual}, not to the linked {expected}")
        self.expected = expected
        self.actual = actual


class AccountAlreadyLinked(DomainError):
    code = "ACCOUNT_ALREADY_LINKED"
    http_status = 409

    def __init__(self, account_ref: str) -> None:
        super().__init__(f"Account {account_ref} is already linked to another user")
        self.account_ref = account_ref


class AccountNotFound(DomainError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self, account_id: str) -> None:
        super().__init__("Linked account not found")
        self.account_id = account_id


class SymbolNotFound(DomainError):
    code = "SYMBOL_NOT_FOUND"
    http_status = 404

    def __init__(self, symbol: str) -> None:
        super().__init__(f"Symbol {symbol} not found in the terminal")
        self.symbol = symbol


class InvalidTimeframe(DomainError):
    code = "INVALID_TIMEFRAME"
    http_status = 422

    def __init__(self, timeframe: str) -> None:
        super().__init__(f"Unsupported timeframe {timeframe!r}")
        self.timeframe = timeframe


class CountOutOfRange(DomainError):
    code = "COUNT_OUT_OF_RANGE"
    http_status = 422

    def __init__(self, count: int, maximum: int) -> None:
        super().__init__(f"count must be between 1 and {maximum}, got {count}")
        self.count = count


class JournalUnavailable(DomainError):
    code = "JOURNAL_UNAVAILABLE"
    http_status = 503

    def __init__(self, reason: str = "Journal service is unavailable") -> None:
        super().__init__(reason)
        self.reason = reason
