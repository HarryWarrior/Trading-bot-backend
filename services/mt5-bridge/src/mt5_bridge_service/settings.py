from pydantic import AliasChoices, Field, SecretStr, field_validator

from trading_shared.settings import BaseServiceSettings

MIN_JWT_SECRET_LENGTH = 32
MIN_SERVICE_KEY_LENGTH = 32


class BridgeSettings(BaseServiceSettings):
    service_name: str = "mt5-bridge"
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        validation_alias=AliasChoices("MONGO_URL", "MONGODB_URL", "mongodb_url"),
    )
    database_name: str = Field(
        default="bridge_db",
        validation_alias=AliasChoices("MONGO_DB", "DATABASE_NAME", "database_name"),
    )
    # Same secret as auth: this service only verifies user tokens, it never issues them.
    jwt_secret_key: SecretStr
    # Same value as the journal service: authorizes the bridge on POST /ingest/deals.
    ingest_service_key: SecretStr
    journal_url: str = "http://localhost:8002"
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
