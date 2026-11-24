from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, SecretStr, field_validator

from trading_shared.settings import BaseServiceSettings

MIN_JWT_SECRET_LENGTH = 32
MIN_SERVICE_KEY_LENGTH = 32
MIN_UTC_OFFSET_MINUTES = -720
MAX_UTC_OFFSET_MINUTES = 840


class Mt5Settings(BaseServiceSettings):
    service_name: str = "mt5"
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "mt5_db"
    # Same secret as auth: this service only verifies tokens, it never issues them.
    jwt_secret_key: SecretStr
    journal_url: str = "http://localhost:8002"
    # Same value as the journal service: authorizes POST /ingest/mt5.
    ingest_service_key: SecretStr
    # Broker server offset from UTC in minutes (e.g. 180 for GMT+3). None = detect from the
    # latest tick; set it when the market is closed or ticks are stale.
    server_utc_offset_minutes: int | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_SERVER_UTC_OFFSET_MINUTES", "server_utc_offset_minutes"),
    )
    # IANA zone of the broker server clock (e.g. Europe/Athens for EET brokers such as FTMO).
    # Recommended: DST aware and independent of fresh ticks. Wins over the fixed offset above.
    server_timezone: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_SERVER_TIMEZONE", "server_timezone"),
    )
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters long"
            )
        return value

    @field_validator("ingest_service_key")
    @classmethod
    def _validate_service_key_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SERVICE_KEY_LENGTH:
            raise ValueError(
                f"INGEST_SERVICE_KEY must be at least {MIN_SERVICE_KEY_LENGTH} characters long"
            )
        return value

    @field_validator("server_utc_offset_minutes")
    @classmethod
    def _validate_offset(cls, value: int | None) -> int | None:
        if value is not None and not MIN_UTC_OFFSET_MINUTES <= value <= MAX_UTC_OFFSET_MINUTES:
            raise ValueError(
                "SERVER_UTC_OFFSET_MINUTES must be between "
                f"{MIN_UTC_OFFSET_MINUTES} and {MAX_UTC_OFFSET_MINUTES}"
            )
        return value

    @field_validator("server_timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            ZoneInfo(value.strip())
        except (KeyError, ValueError, OSError):
            raise ValueError(
                "MT5_SERVER_TIMEZONE must be an IANA time zone, e.g. Europe/Athens"
            ) from None
        return value.strip()
