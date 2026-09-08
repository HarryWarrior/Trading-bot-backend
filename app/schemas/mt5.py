"""
Pydantic schemas for MetaTrader 5 account connection, deal synchronization, and OHLCV rates.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class MT5AccountCreate(BaseModel):
    """Schema for registering a new MetaTrader 5 trading account."""
    account_name: str = Field(..., description="Friendly label for the account (e.g. IC Markets Live)")
    login: int = Field(..., description="MT5 Account Login ID / Number")
    server: str = Field(..., description="Broker MT5 Server Name (e.g. ICMarkets-Live02)")
    password: str = Field(..., description="Investor (read-only) or master password")
    broker_name: Optional[str] = Field(None, description="Optional broker name")
    platform: str = Field("MT5", description="Platform type (MT4 or MT5)")


class MT5AccountResponse(BaseModel):
    """Public representation of a linked MetaTrader account."""
    id: str = Field(..., description="Unique MongoDB account ID")
    user_id: Optional[str] = Field(None, description="Owner user ID")
    account_name: str
    login: int
    server: str
    broker_name: Optional[str] = None
    platform: str = "MT5"
    is_connected: bool = False
    last_sync_at: Optional[datetime] = None
    balance: float = 0.0
    equity: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    created_at: datetime


class MT5SyncRequest(BaseModel):
    """Parameters for synchronizing deal history."""
    from_date: Optional[datetime] = Field(None, description="Start date for deal sync")
    to_date: Optional[datetime] = Field(None, description="End date for deal sync")


class MT5SyncResponse(BaseModel):
    """Result of a deal synchronization batch."""
    account_id: str
    synced_deals_count: int
    new_trades_count: int
    balance: float
    equity: float
    message: str


class RateCandle(BaseModel):
    """OHLCV Candlestick bar for financial charts."""
    time: int = Field(..., description="UNIX timestamp in seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class RatesRequest(BaseModel):
    """Query parameters for fetching historical rates."""
    symbol: str
    timeframe: str = Field("5m", description="Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1D")
    from_time: Optional[datetime] = None
    to_time: Optional[datetime] = None
    count: int = Field(200, description="Number of candles to retrieve (max 1000)")


class RatesResponse(BaseModel):
    """Candlestick series response."""
    symbol: str
    timeframe: str
    candles: List[RateCandle]
    count: int
