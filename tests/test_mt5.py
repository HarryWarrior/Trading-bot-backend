"""
Unit tests for MetaTrader 5 service, encryption, deal simulation, and rate feeds.
"""

import pytest
from app.services.mt5_service import MT5Service, _encrypt_password, _decrypt_password
from app.schemas.mt5 import RatesResponse, RateCandle


def test_encryption_decryption_cycle():
    """Verify AES/XOR password encryption is bidirectional and lossless."""
    original_pass = "MySecretInvestorPass123!"
    encrypted = _encrypt_password(original_pass)
    assert encrypted != original_pass
    assert len(encrypted) > 0

    decrypted = _decrypt_password(encrypted)
    assert decrypted == original_pass


def test_rates_candlestick_generation():
    """Verify OHLCV candlestick time series adheres to market rules."""
    rates = MT5Service.get_historical_rates(symbol="EURUSD", timeframe="5m", count=50)

    assert isinstance(rates, RatesResponse)
    assert rates.symbol == "EURUSD"
    assert rates.timeframe == "5m"
    assert len(rates.candles) == 50

    for candle in rates.candles:
        assert isinstance(candle, RateCandle)
        assert candle.high >= candle.open
        assert candle.high >= candle.close
        assert candle.low <= candle.open
        assert candle.low <= candle.close
        assert candle.volume >= 0
        assert candle.time > 0


def test_mt5_account_response_schema_active_field():
    """Verify MT5AccountResponse supports is_active state flag."""
    from datetime import datetime
    from app.schemas.mt5 import MT5AccountResponse

    account = MT5AccountResponse(
        id="65f2a1b9c8d7e6f5a4b3c2d1",
        account_name="IC Markets Demo",
        login=12345678,
        server="ICMarkets-Demo01",
        platform="MT5",
        is_connected=True,
        is_active=True,
        balance=10000.0,
        equity=10000.0,
        currency="USD",
        leverage=100,
        created_at=datetime.utcnow(),
    )
    assert account.is_active is True
    assert account.login == 12345678


@pytest.mark.asyncio
async def test_broker_connection_validation_failure():
    """Verify that invalid credentials or unreachable servers are rejected with ValueError."""
    with pytest.raises(ValueError, match="Invalid MT5 Login ID"):
        await MT5Service._test_broker_connection(login=0, password="validpass123", server="ICMarkets-Live")

    with pytest.raises(ValueError, match="Invalid Password"):
        await MT5Service._test_broker_connection(login=12345, password="12", server="ICMarkets-Live")

    with pytest.raises(ValueError, match="Invalid Server"):
        await MT5Service._test_broker_connection(login=12345, password="validpass123", server=" ")

    with pytest.raises(ValueError, match="Authentication failed on server"):
        await MT5Service._test_broker_connection(login=12345, password="wrong_password", server="ICMarkets-Live")


@pytest.mark.asyncio
async def test_broker_connection_success():
    """Verify valid credentials return authenticated status and telemetry."""
    is_connected, balance, equity, currency, leverage = await MT5Service._test_broker_connection(
        login=50124890,
        password="ValidInvestorPassword123!",
        server="ICMarketsSC-Live02",
    )
    assert is_connected is True
    assert balance > 0
    assert equity > 0
    assert currency == "USD"
    assert leverage == 100


