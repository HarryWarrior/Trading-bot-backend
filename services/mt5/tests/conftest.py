from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from mt5_fakes import (  # noqa: E402
    FakeJournalGateway,
    FakeTerminal,
    FixedClock,
    InMemoryLinkedAccountRepository,
    SequentialIds,
    terminal_account,
)


@pytest.fixture
def terminal() -> FakeTerminal:
    return FakeTerminal(terminal_account())


@pytest.fixture
def journal() -> FakeJournalGateway:
    return FakeJournalGateway()


@pytest.fixture
def repo() -> InMemoryLinkedAccountRepository:
    return InMemoryLinkedAccountRepository()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()
