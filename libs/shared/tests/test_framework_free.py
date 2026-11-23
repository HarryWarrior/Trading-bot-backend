"""envelope.py is imported by application layers, so it must stay framework-free."""

import re
from pathlib import Path

ENVELOPE = Path(__file__).resolve().parents[1] / "src" / "trading_shared" / "envelope.py"


def test_envelope_has_no_framework_imports():
    modules = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", ENVELOPE.read_text(), re.MULTILINE)
    assert [m for m in modules if m.split(".")[0] in ("fastapi", "starlette")] == []
