from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.domain.token import IngestToken


class ListIngestTokens:
    def __init__(self, tokens: TokenRepository) -> None:
        self._tokens = tokens

    async def execute(self, user_id: str) -> list[IngestToken]:
        """The user's tokens, newest first (hashes only, never plaintext)."""
        return await self._tokens.list_for_user(user_id)
