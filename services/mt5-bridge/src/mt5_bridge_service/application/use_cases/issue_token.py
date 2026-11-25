from mt5_bridge_service.application.ports.clock import Clock
from mt5_bridge_service.application.ports.ids import IdGenerator
from mt5_bridge_service.application.ports.tokens import TokenRepository
from mt5_bridge_service.domain.token import IngestToken


class IssueIngestToken:
    def __init__(self, tokens: TokenRepository, clock: Clock, ids: IdGenerator) -> None:
        self._tokens = tokens
        self._clock = clock
        self._ids = ids

    async def execute(self, user_id: str, name: str) -> tuple[IngestToken, str]:
        """Issue a token for ``user_id``.

        Returns:
            The stored token (hash only) and its plaintext. This is the only place the plaintext
            exists: show it to the user once and never store or log it.

        Raises:
            InvalidTokenName: If the name is blank or too long.
        """
        token, plaintext = IngestToken.issue(self._ids.new_id(), user_id, name, self._clock.now())
        await self._tokens.add(token)
        return token, plaintext
