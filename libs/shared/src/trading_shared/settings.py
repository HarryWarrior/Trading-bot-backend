"""Base settings every service extends."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    version: str = "0.1.0"
    environment: Literal["local", "test", "prod"] = "local"
    log_level: str = "INFO"
