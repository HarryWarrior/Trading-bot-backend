from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.domain.errors import TokenNotFound
from mt5_bridge_service.domain.token import IngestToken


class RevokeIngestToken:
    def __init__(self, tokens: TokenRepository, clock: Clock) -> None:
        self._tokens = tokens
        self._clock = clock

    async def execute(self, user_id: str, token_id: str) -> IngestToken:
        """Revoke one of the user's tokens (idempotent).

        Raises:
            TokenNotFound: If the token does not exist or belongs to another user.
        """
        token = await self._tokens.get(user_id, token_id)
        if token is None:
            raise TokenNotFound(token_id)
        if token.is_active:
            await self._tokens.mark_revoked(user_id, token_id, self._clock.now())
            token = await self._tokens.get(user_id, token_id)
            if token is None:
                raise TokenNotFound(token_id)
        return token
