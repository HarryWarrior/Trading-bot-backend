"""
API Router for MetaTrader 5 account connection, deal synchronization, and OHLCV rates.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.mt5 import (
    MT5AccountCreate,
    MT5AccountResponse,
    MT5SyncResponse,
    RatesResponse,
)
from app.services.mt5_service import MT5Service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/accounts", response_model=MT5AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_mt5_account(account_data: MT5AccountCreate):
    """
    Link a new MetaTrader 5 trading account with encrypted credentials.
    """
    try:
        account = await MT5Service.create_account(account_data)
        logger.info(f"Linked MT5 account {account.login} on {account.server}")
        return account
    except Exception as e:
        logger.error(f"Failed to link MT5 account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to MetaTrader account: {str(e)}",
        )


@router.get("/accounts", response_model=List[MT5AccountResponse])
async def list_mt5_accounts():
    """
    List all registered MetaTrader accounts.
    """
    try:
        return await MT5Service.list_accounts()
    except Exception as e:
        logger.error(f"Error listing MT5 accounts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving MetaTrader accounts",
        )


@router.post("/accounts/{account_id}/sync", response_model=MT5SyncResponse)
async def sync_mt5_account(account_id: str):
    """
    Trigger manual deal synchronization from the broker server.
    """
    try:
        sync_result = await MT5Service.sync_account_deals(account_id)
        logger.info(f"Synced {sync_result.synced_deals_count} deals for account {account_id}")
        return sync_result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error syncing account {account_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synchronization failed: {str(e)}",
        )


@router.post("/accounts/{account_id}/activate", response_model=MT5AccountResponse)
async def activate_mt5_account(account_id: str):
    """
    Switch active MetaTrader account for dashboard and analytics ingestion.
    """
    try:
        account = await MT5Service.set_active_account(account_id)
        logger.info(f"Activated MT5 account {account.login} ({account.id})")
        return account
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error activating MT5 account {account_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate account: {str(e)}",
        )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_200_OK)
async def delete_mt5_account(account_id: str):
    """
    Unlink and delete a registered MetaTrader account.
    """
    try:
        await MT5Service.delete_account(account_id)
        logger.info(f"Deleted MT5 account {account_id}")
        return {"success": True, "message": f"Account {account_id} successfully removed"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting MT5 account {account_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}",
        )


@router.get("/accounts/{account_id}/status")
async def get_account_status(account_id: str):
    """
    Check live connectivity and account summary with the broker.
    """
    account = await MT5Service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )

    return {
        "success": True,
        "account_id": account_id,
        "server": account.get("server"),
        "login": account.get("login"),
        "is_connected": account.get("is_connected", True),
        "is_active": account.get("is_active", False),
        "balance": account.get("balance", 10000.0),
        "equity": account.get("equity", 10000.0),
        "last_sync_at": account.get("last_sync_at"),
    }


@router.get("/rates", response_model=RatesResponse)
async def get_rates(
    symbol: str = Query(..., description="Currency pair or asset symbol (e.g. EURUSD, GBPUSD, XAUUSD)"),
    timeframe: str = Query("5m", description="Candle timeframe (1m, 5m, 15m, 1h, 4h, 1D)"),
    count: int = Query(200, ge=10, le=1000, description="Number of candlestick bars to return"),
):
    """
    Get historical OHLCV candlestick time-series for candlestick chart rendering.
    """
    try:
        return MT5Service.get_historical_rates(symbol=symbol, timeframe=timeframe, count=count)
    except Exception as e:
        logger.error(f"Error fetching rates for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch rates: {str(e)}",
        )
