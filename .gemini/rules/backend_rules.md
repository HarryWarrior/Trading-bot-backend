# Backend Rules for Gemini / AI Assistant

- Apply Pagination & Search contract to all list endpoints (`page`, `page_size`, `sort_by`, `sort_dir`, `q`).
- Round all P&L floats to 2 decimal places and price values to asset standards.
- Compute SHA-256 for uploaded files to guarantee idempotency.
- Code, docstrings, error messages, and logs strictly in English.
- No trivial comments; only document complex algorithms.
- Run `python scripts/update_changelog.py` when introducing changes to sync CHANGELOG and bump version.
- Enforce Ruff checks before pushing.
