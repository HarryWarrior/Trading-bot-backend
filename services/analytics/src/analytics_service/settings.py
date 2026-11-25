from pydantic import SecretStr, field_validator

from trading_shared.settings import BaseServiceSettings

MIN_JWT_SECRET_LENGTH = 32


class AnalyticsSettings(BaseServiceSettings):
    service_name: str = "analytics"
    # Same secret as auth: analytics only verifies tokens, it never issues them.
    jwt_secret_key: SecretStr
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
