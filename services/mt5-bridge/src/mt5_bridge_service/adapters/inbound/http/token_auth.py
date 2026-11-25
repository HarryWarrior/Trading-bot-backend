"""``Authorization: Bearer <ingest token>`` for the EA-facing endpoints.

The plaintext is hashed and looked up; it is never logged, stored or echoed.
"""

from fastapi import Header, Request

from mt5_bridge_service.domain.token import IngestToken
from trading_shared.errors import AppError


async def ingest_token_owner(
    request: Request, authorization: str | None = Header(default=None)
) -> IngestToken:
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise AppError("UNAUTHENTICATED", "An ingest token is required", 401)
    container = request.app.state.container
    return await container.authenticate_token.execute(value.strip())
