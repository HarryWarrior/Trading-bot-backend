from pydantic import SecretStr, field_validator

from trading_shared.settings import BaseServiceSettings

MIN_JWT_SECRET_LENGTH = 32
MIN_SERVICE_KEY_LENGTH = 32


class JournalSettings(BaseServiceSettings):
    service_name: str = "journal"
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "journal_db"
    jwt_secret_key: SecretStr
    ingest_service_key: SecretStr
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_mb: int = 10

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
