# mount-image-udisks — AGENTS.md

## Project

Disk image mounting via udisksctl (Linux).

- **Package**: `mount-image-udisks` (PyPI), `mount_image_udisks` (import)
- **Repo**: `https://github.com/MBanucu/mount-image-udisks`
- **Python**: `>=3.10`
- **License**: GPL-3.0-only

## Commands

```bash
pip install -e .
python -m unittest discover -s tests -v
pip install coverage
python -m coverage run -m unittest discover -s tests -v
python -m coverage report --fail-under=70 --skip-covered

# or via Nix dev shell:
nix develop -c python -m unittest discover -s tests -v
```

## Module structure

```
mount_image_udisks/
  __init__.py    — public API + parse helpers
tests/
  test_mount_image_udisks.py
```
