from typing import Self

from pydantic import SecretStr, field_validator, model_validator

from trading_shared.settings import BaseServiceSettings

MIN_JWT_SECRET_LENGTH = 32


class AuthSettings(BaseServiceSettings):
    service_name: str = "auth"
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "auth_db"
    jwt_secret_key: SecretStr
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters long"
            )
        return value

    @model_validator(mode="after")
    def _validate_smtp(self) -> Self:
        if self.environment == "prod" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required when ENVIRONMENT=prod")
        if self.smtp_host:
            if not self.smtp_from_email:
                raise ValueError("SMTP_FROM_EMAIL is required when SMTP_HOST is set")
            if bool(self.smtp_user) != bool(self.smtp_password):
                raise ValueError("SMTP_USER and SMTP_PASSWORD must be set together")
        return self
