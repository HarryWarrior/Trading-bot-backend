import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_only_samples_are_tracked_under_data():
    out = subprocess.run(
        ["git", "ls-files", "data"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    lines = [line for line in out.splitlines() if line.strip()]
    offenders = [line for line in lines if not line.startswith("data/samples/")]
    assert offenders == []
