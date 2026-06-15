# mount-image-udisks — AGENTS.md

## Project

Disk image mounting via udisksctl (Linux).

- **Package**: `mount-image-udisks` (PyPI), `mount_image_udisks` (import)
- **Repo**: `https://github.com/MBanucu/mount-image-udisks`
- **Python**: `>=3.10`
- **License**: GPL-3.0-only

## Commands

```bash
# Install editable, run tests
pip install -e .
python -m unittest discover -s tests -v

# Coverage (NixOS)
nix-shell -p "python313.withPackages(ps: [ ps.coverage ])" --run "
PYTHONPATH=. python -m coverage run --source=mount_image_udisks -m unittest discover -s tests -v
python -m coverage report --show-missing
"

# Coverage (pip)
pip install coverage
python -m coverage run -m unittest discover -s tests -v
python -m coverage report --fail-under=70 --skip-covered
```

## Codecov API

```bash
# File-level report (absolute)
curl -s "https://api.codecov.io/api/v2/gh/MBanucu/repos/mount-image-udisks/file_report/mount_image_udisks/__init__.py?branch=main"

# Repo-level totals
curl -s "https://api.codecov.io/api/v2/gh/MBanucu/repos/mount-image-udisks/totals?branch=main"

# Recent commits with coverage
curl -s "https://api.codecov.io/api/v2/gh/MBanucu/repos/mount-image-udisks/commits?branch=main"
```

Response fields:
- `totals.lines` — trackable lines; `totals.hits` — covered; `totals.misses` — uncovered
- `line_coverage` — array of `[line_number, hit_count]` entries; `hit_count > 0` means covered

## Module structure

```
mount_image_udisks/
  __init__.py    — public API + parse helpers
tests/
  test_mount_image_udisks.py
```
