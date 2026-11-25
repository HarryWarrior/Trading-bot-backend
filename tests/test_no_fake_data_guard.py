"""Guard: production code under services/ and libs/ never fabricates market data or balances.

Real data only: unavailable data is an explicit error or an empty result, never a random series or a
hard-coded demo balance. Test code (tests/ folders, test_*.py, conftest.py) is excluded.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "random module": re.compile(r"^\s*(import random\b|from random import)|\brandom\.\w+\(", re.M),
    "numpy random": re.compile(r"\bnp\.random\b|\bnumpy\.random\b"),
    "JS Math.random": re.compile(r"Math\.random"),
    "hard-coded demo balance": re.compile(r"(?<![\w.])(10000|25000)(\.0+)?(?![\w.])"),
}


def production_files() -> list[Path]:
    files = []
    for base in (ROOT / "services", ROOT / "libs"):
        for path in base.rglob("*.py"):
            parts = set(path.relative_to(ROOT).parts)
            if parts & {"tests", ".venv", "node_modules", "__pycache__", "scripts"}:
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            files.append(path)
    return files


def test_there_is_production_code_to_scan():
    assert len(production_files()) > 50


def test_no_random_data_or_hard_coded_balances_in_production_code():
    offenders = []
    for path in production_files():
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN.items():
            if pattern.search(text):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {label}")
    assert offenders == []
