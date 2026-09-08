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
