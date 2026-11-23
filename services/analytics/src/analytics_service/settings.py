from trading_shared.settings import BaseServiceSettings


class AnalyticsSettings(BaseServiceSettings):
    service_name: str = "analytics"
    journal_url: str = "http://localhost:8002"
