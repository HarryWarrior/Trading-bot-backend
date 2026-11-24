from fastapi import APIRouter

# Routes are added in a later task; the prefix is fixed by the service layout.
router = APIRouter(prefix="/api/v1/mt5", tags=["mt5"])
