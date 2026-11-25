from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

# starlette 0.27 imports the legacy `multipart` alias, which python-multipart >= 0.0.13 flags.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    import multipart  # noqa: F401

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
