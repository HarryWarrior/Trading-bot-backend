"""
Changelog / version guard for the Trading Bot backend.

Single version source: the root ``VERSION`` file (the version being prepared).

``--check-only`` (pre-push hook) passes when ``docs/CHANGELOG.md`` has either
  * a ``## [<VERSION>]`` section, or
  * a non-empty ``## [Unreleased]`` section;
otherwise it fails (changes were made without a changelog entry).

``--bump [patch|minor|major]`` (or ``--version X.Y.Z``) moves the ``[Unreleased]`` content into a
new ``## [X.Y.Z] - <date>`` section, leaves an empty ``[Unreleased]`` and writes ``VERSION``.
``--message`` first adds a bullet to ``[Unreleased]``.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

UNRELEASED = "## [Unreleased]"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read_version(root: Path) -> str:
    version_file = root / "VERSION"
    if not version_file.exists():
        raise SystemExit("VERSION file is missing (expected X.Y.Z in the repo root).")
    version = version_file.read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        raise SystemExit(f"VERSION must look like X.Y.Z, got {version!r}.")
    return version


def bump_semver(version: str, bump_type: str = "patch") -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def split_unreleased(content: str) -> tuple[str, str, str]:
    """Return (before, unreleased_body, after); body excludes the heading."""
    start = content.find(UNRELEASED)
    if start == -1:
        return content, "", ""
    body_start = start + len(UNRELEASED)
    nxt = re.search(r"^## \[", content[body_start:], re.MULTILINE)
    body_end = body_start + nxt.start() if nxt else len(content)
    return content[:start], content[body_start:body_end], content[body_end:]


def check(root: Path) -> tuple[bool, str]:
    version = read_version(root)
    changelog = root / "docs" / "CHANGELOG.md"
    if not changelog.exists():
        return False, "docs/CHANGELOG.md does not exist."
    content = changelog.read_text(encoding="utf-8")
    if re.search(rf"^## \[{re.escape(version)}\]", content, re.MULTILINE):
        return True, f"docs/CHANGELOG.md has a section for [{version}]."
    _, body, _ = split_unreleased(content)
    if body.strip():
        return True, f"docs/CHANGELOG.md has [Unreleased] entries (VERSION is {version})."
    return False, (
        f"docs/CHANGELOG.md has no [{version}] section and [Unreleased] is empty. "
        "Add an entry under [Unreleased] (or run with --bump)."
    )


def bump(root: Path, version: str | None, bump_type: str, message: str | None) -> str:
    current = read_version(root)
    target = version or bump_semver(current, bump_type)
    if not SEMVER.match(target):
        raise SystemExit(f"Version must look like X.Y.Z, got {target!r}.")
    changelog = root / "docs" / "CHANGELOG.md"
    content = changelog.read_text(encoding="utf-8")
    if UNRELEASED not in content:
        raise SystemExit("docs/CHANGELOG.md has no [Unreleased] section.")
    before, body, after = split_unreleased(content)
    if message:
        body = "\n\n- " + message + "\n" + body.lstrip("\n")
    if not body.strip():
        raise SystemExit("Nothing to release: [Unreleased] is empty (use --message).")
    release = f"## [{target}] - {datetime.date.today().isoformat()}\n{body.rstrip()}\n\n---\n\n"
    changelog.write_text(f"{before}{UNRELEASED}\n\n{release}{after.lstrip()}", encoding="utf-8")
    (root / "VERSION").write_text(f"{target}\n", encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Changelog / VERSION guard and release helper.")
    parser.add_argument("--check-only", action="store_true", help="verify the changelog rule")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], help="release Unreleased")
    parser.add_argument("--version", help="explicit release version X.Y.Z (implies release)")
    parser.add_argument("--message", help="bullet to add to [Unreleased] before releasing")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent

    if args.check_only or not (args.bump or args.version):
        ok, msg = check(root)
        print(("OK: " if ok else "FAIL: ") + msg)
        return 0 if ok else 1

    target = bump(root, args.version, args.bump or "patch", args.message)
    print(f"Released [{target}]; VERSION updated.")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
