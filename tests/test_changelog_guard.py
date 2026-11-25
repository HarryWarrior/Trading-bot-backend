import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "update_changelog.py"
spec = importlib.util.spec_from_file_location("update_changelog", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def make_root(tmp_path: Path, changelog: str, version: str = "3.0.0") -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (tmp_path / "docs" / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_real_repo_passes():
    ok, _ = guard.check(SCRIPT.parent.parent)
    assert ok


def test_fails_with_empty_unreleased_and_no_version_section(tmp_path):
    root = make_root(tmp_path, "# Changelog\n\n## [Unreleased]\n\n## [2.0.4] - 2026-09-08\n- x\n")
    ok, msg = guard.check(root)
    assert not ok and "3.0.0" in msg


def test_passes_with_unreleased_entries(tmp_path):
    root = make_root(tmp_path, "# Changelog\n\n## [Unreleased]\n- change\n\n## [2.0.4] - d\n- x\n")
    assert guard.check(root)[0]


def test_passes_with_version_section(tmp_path):
    root = make_root(tmp_path, "# Changelog\n\n## [Unreleased]\n\n## [3.0.0] - d\n- x\n")
    assert guard.check(root)[0]


def test_missing_version_file_exits(tmp_path):
    root = make_root(tmp_path, "# Changelog\n")
    (root / "VERSION").unlink()
    with pytest.raises(SystemExit):
        guard.check(root)


def test_bump_moves_unreleased_and_writes_version(tmp_path):
    root = make_root(tmp_path, "# Changelog\n\n## [Unreleased]\n- change\n\n## [2.0.4] - d\n- x\n")
    assert guard.bump(root, None, "minor", None) == "3.1.0"
    text = (root / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [3.1.0] -" in text and "- change" in text
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "3.1.0"
    assert guard.check(root)[0]
