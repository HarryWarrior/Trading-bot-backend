"""HTTP routes of the bridge. Token, account and EA ingest endpoints arrive with spec 002 Task 4."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/mt5-bridge", tags=["mt5-bridge"])
