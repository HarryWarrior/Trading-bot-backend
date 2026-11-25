from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.domain.errors import InvalidIngestToken
from mt5_bridge_service.domain.token import INGEST_MT5_SCOPE, IngestToken, hash_token


class AuthenticateIngestToken:
    def __init__(self, tokens: TokenRepository, clock: Clock) -> None:
        self._tokens = tokens
        self._clock = clock

    async def execute(self, plaintext: str) -> IngestToken:
        """Resolve the owner of an EA request and record the use (``last_used_at``).

        Raises:
            InvalidIngestToken: If the token is blank, unknown, revoked or not ``ingest:mt5``.
        """
        if not plaintext.strip():
            raise InvalidIngestToken()
        token = await self._tokens.find_active_by_hash(hash_token(plaintext.strip()))
        if token is None or token.scope != INGEST_MT5_SCOPE:
            raise InvalidIngestToken()
        await self._tokens.touch_last_used(token.user_id, token.id, self._clock.now())
        return token
