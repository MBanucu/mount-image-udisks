"""Internal helper functions — subprocess calls and parsing."""

import re
import subprocess

_DEV_RE = re.compile(r'as\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)
_MOUNT_RE = re.compile(r'at\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)


def loop_setup(image_path: str) -> str:
    cmd = ['udisksctl', 'loop-setup', '-f', str(image_path),
           '--no-user-interaction']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl loop-setup failed: {r.stderr.strip()}")
    dev = parse_dev(r.stdout)
    if not dev:
        raise RuntimeError(
            f"udisksctl loop-setup: could not parse device from: {r.stdout.strip()}")
    return dev


def mount_device(loop_dev: str, fstype: str | None,
                 options: list[str] | None) -> str:
    cmd = ['udisksctl', 'mount', '-b', loop_dev, '--no-user-interaction']
    if fstype:
        cmd.extend(['-t', fstype])
    if options:
        cmd.extend(['-o', ','.join(options)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl mount failed: {r.stderr.strip()}")
    mp = parse_mount(r.stdout)
    if not mp:
        raise RuntimeError(
            f"udisksctl mount: could not parse mount point from: {r.stdout.strip()}")
    return mp


def loop_delete(loop_dev: str):
    return subprocess.run(
        ['udisksctl', 'loop-delete', '-b', loop_dev, '--no-user-interaction'],
        capture_output=True)


def power_off(device: str):
    return subprocess.run(
        ['udisksctl', 'power-off', '-b', device, '--no-user-interaction'],
        capture_output=True)


def parse_dev(stdout: str) -> str | None:
    m = _DEV_RE.search(stdout)
    if m:
        return m.group(1)
    return None


def parse_mount(stdout: str) -> str | None:
    m = _MOUNT_RE.search(stdout)
    if m:
        return m.group(1)
    for line in stdout.splitlines():
        if 'Mounted' in line and 'at' in line:
            idx = line.find(' at ')
            if idx != -1:
                return line[idx + 4:].rstrip('.')
    return None
