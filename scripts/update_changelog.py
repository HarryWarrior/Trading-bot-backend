"""
Automated Changelog Updater and Version Manager for Trading Bot Backend API.

This script updates docs/CHANGELOG.md with new version entries,
categories (Added, Changed, Fixed, Security), and ensures version synchronization across the repository.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path


def get_current_app_version(backend_root: Path) -> str:
    """Extract current version string from app/main.py."""
    main_file = backend_root / "app" / "main.py"
    if not main_file.exists():
        return "2.0.0"

    content = main_file.read_text(encoding="utf-8")
    match = re.search(r'version=["\']([0-9]+\.[0-9]+\.[0-9]+)["\']', content)
    return match.group(1) if match else "2.0.0"


def bump_semver(version: str, bump_type: str = "patch") -> str:
    """Bump semantic version (major, minor, or patch)."""
    parts = version.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def update_main_py_version(backend_root: Path, new_version: str):
    """Update version in app/main.py."""
    main_file = backend_root / "app" / "main.py"
    if not main_file.exists():
        return

    content = main_file.read_text(encoding="utf-8")
    updated_content = re.sub(
        r'version=["\']([0-9]+\.[0-9]+\.[0-9]+)["\']',
        f'version="{new_version}"',
        content,
    )
    main_file.write_text(updated_content, encoding="utf-8")
    print(f"✅ Updated version in app/main.py to {new_version}")


def format_changelog_entry(version: str, date_str: str, changes: dict[str, list[str]]) -> str:
    """Format a standard markdown changelog release block."""
    lines = [f"## [{version}] - {date_str}"]

    category_emojis = {
        "Added": "✨ Added",
        "Changed": "🔧 Changed",
        "Fixed": "🐛 Fixed",
        "Security": "🔒 Security",
        "Removed": "🗑️ Removed",
    }

    for cat, items in changes.items():
        if items:
            emoji_title = category_emojis.get(cat, f"📌 {cat}")
            lines.append(f"\n### {emoji_title}")
            for item in items:
                lines.append(f"- {item}")

    lines.append("\n---\n")
    return "\n".join(lines)


def prepend_to_changelog(file_path: Path, entry_content: str):
    """Prepend a new release entry right after the top header of a changelog file."""
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f"# Changelog\n\n{entry_content}\n", encoding="utf-8")
        print(f"✅ Created {file_path.name} with new version entry.")
        return

    content = file_path.read_text(encoding="utf-8")

    # Locate where to insert (after main # Changelog title)
    header_match = re.search(r"^(#\s+[^\n]+\n+)", content)
    if header_match:
        header = header_match.group(1)
        rest = content[len(header) :]
        new_content = f"{header}{entry_content}\n{rest}"
    else:
        new_content = f"# Changelog\n\n{entry_content}\n{content}"

    file_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Updated {file_path}")


def main():
    parser = argparse.ArgumentParser(description="Update docs/CHANGELOG.md and bump project version.")
    parser.add_argument("--version", type=str, help="Explicit version (e.g. 2.1.0)")
    parser.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        default="patch",
        help="Semantic version bump type (default: patch)",
    )
    parser.add_argument(
        "--added",
        nargs="*",
        default=[],
        help="List of newly added features",
    )
    parser.add_argument(
        "--changed",
        nargs="*",
        default=[],
        help="List of changed features",
    )
    parser.add_argument(
        "--fixed",
        nargs="*",
        default=[],
        help="List of bug fixes",
    )
    parser.add_argument(
        "--security",
        nargs="*",
        default=[],
        help="List of security improvements",
    )
    parser.add_argument(
        "--message",
        type=str,
        help="Quick single message to add under Added",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify if docs/CHANGELOG.md has an entry for current version",
    )

    args = parser.parse_args()
    backend_root = Path(__file__).resolve().parent.parent
    docs_changelog = backend_root / "docs" / "CHANGELOG.md"

    current_version = get_current_app_version(backend_root)

    # Check only mode (used by git hooks to ensure changelog is updated)
    if args.check_only:
        if not docs_changelog.exists():
            print("⚠️ docs/CHANGELOG.md does not exist.")
            sys.exit(1)

        content = docs_changelog.read_text(encoding="utf-8")
        if f"[{current_version}]" not in content:
            print(f"⚠️ docs/CHANGELOG.md is missing an entry for current version [{current_version}].")
            print("💡 Run 'python scripts/update_changelog.py --message \"...\"' to add it.")
            sys.exit(1)
        else:
            print(f"✅ docs/CHANGELOG.md is up to date with version [{current_version}].")
            sys.exit(0)

    # Determine target version
    if args.version:
        target_version = args.version
    else:
        target_version = bump_semver(current_version, args.bump)

    # Collect changes
    changes = {
        "Added": list(args.added),
        "Changed": list(args.changed),
        "Fixed": list(args.fixed),
        "Security": list(args.security),
    }

    if args.message:
        changes["Added"].append(args.message)

    # If no changes provided, provide default placeholder
    if not any(changes.values()):
        changes["Added"].append("Automated update and performance improvements")

    today_str = datetime.date.today().isoformat()
    entry = format_changelog_entry(target_version, today_str, changes)

    # Update app/main.py
    update_main_py_version(backend_root, target_version)

    # Update docs/CHANGELOG.md
    prepend_to_changelog(docs_changelog, entry)

    print(f"\n🎉 Successfully created release [{target_version}] in docs/CHANGELOG.md.")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

