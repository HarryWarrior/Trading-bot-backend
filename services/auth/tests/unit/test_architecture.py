"""Guards the hexagonal dependency rule: inner layers never import frameworks or drivers."""

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "auth_service"
INNER_LAYERS = ("domain", "application")
FORBIDDEN = ("fastapi", "starlette", "motor", "pymongo", "pydantic_settings")
IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)


def test_domain_and_application_have_no_framework_imports():
    offenders = []
    for layer in INNER_LAYERS:
        for source in (PACKAGE_ROOT / layer).rglob("*.py"):
            for module in IMPORT_PATTERN.findall(source.read_text(encoding="utf-8")):
                if module.split(".")[0] in FORBIDDEN:
                    offenders.append(f"{source.relative_to(PACKAGE_ROOT)} imports {module}")
    assert offenders == []
