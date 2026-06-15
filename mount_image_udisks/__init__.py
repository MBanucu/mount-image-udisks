"""Disk image mounting via udisksctl (Linux, no sudo needed for active sessions).

Uses ``udisksctl loop-setup`` to create loop devices and ``udisksctl mount``
to mount filesystems via UDisks2.  PolKit grants active local sessions
permission without a password on most desktop distributions.

Key advantages over the sudo strategy:
  - No root password required (uses polkit authorisation)
  - Mount point managed by udisks2 (under /run/media/$USER/)
  - Automatic filesystem type detection when fstype is not specified
"""

import re
import subprocess

_DEV_RE = re.compile(r'as\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)
_MOUNT_RE = re.compile(r'at\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)
_ALREADY_MOUNTED_RE = re.compile(
    r"is already mounted at [`']([^`']+)")


def mount_image(image_path: str, fstype: str | None = None,
                options: list[str] | None = None) -> tuple[str, str]:
    """Attach *image_path* via udisksctl and mount it.

    Returns ``(device, mount_point)``.
    Raises ``RuntimeError`` on failure.
    """
    loop_dev = _loop_setup(image_path)
    try:
        mount_point = _mount(loop_dev, fstype, options)
    except RuntimeError as e:
        already = _parse_already_mounted(str(e))
        if already:
            _loop_delete(loop_dev)
            # DE auto-mounted a previous loop device — find it
            r = subprocess.run(
                ['findmnt', '-n', '-o', 'SOURCE', already],
                capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip(), already
            raise RuntimeError(
                f'device already mounted at {already} but could not '
                f'find backing device') from e
        _loop_delete(loop_dev)
        raise
    return loop_dev, mount_point


def umount_image(device: str, mount_point: str | None = None):
    """Unmount and detach a disk image."""
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl unmount failed: {r.stderr.strip()}")

    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)


def attach_image(image_path: str) -> str:
    """Attach *image_path* as a block device without mounting.

    Returns the device path (e.g. ``/dev/loop0``).
    Raises ``RuntimeError`` on failure.
    """
    return _loop_setup(image_path)


def detach_image(device: str):
    """Detach a block device."""
    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)


def umount_inner(device: str):
    """Unmount without detach. Used by the orchestrator."""
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl unmount failed: {r.stderr.strip()}")


def detach_inner(device: str):
    """Detach without unmount. Used by the orchestrator."""
    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)


# ── internal helpers ────────────────────────────────────────────────

def _loop_setup(image_path: str, read_only: bool = False) -> str:
    cmd = ['udisksctl', 'loop-setup', '-f', str(image_path),
           '--no-user-interaction']
    if read_only:
        cmd.append('--read-only')

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl loop-setup failed: {r.stderr.strip()}")

    dev = _parse_dev(r.stdout)
    if not dev:
        raise RuntimeError(
            f"udisksctl loop-setup: could not parse device from: {r.stdout.strip()}")
    return dev


def _mount(loop_dev: str, fstype: str | None, options: list[str] | None) -> str:
    cmd = ['udisksctl', 'mount', '-b', loop_dev, '--no-user-interaction']
    if fstype:
        cmd.extend(['-t', fstype])
    if options:
        cmd.extend(['-o', ','.join(options)])

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl mount failed: {r.stderr.strip()}")

    mp = _parse_mount(r.stdout)
    if not mp:
        raise RuntimeError(
            f"udisksctl mount: could not parse mount point from: {r.stdout.strip()}")
    return mp


def _loop_delete(loop_dev: str):
    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', loop_dev, '--no-user-interaction'],
        capture_output=True)


def _parse_dev(stdout: str) -> str | None:
    m = _DEV_RE.search(stdout)
    if m:
        return m.group(1)
    for line in stdout.splitlines():
        if ' as ' in line:
            parts = line.strip().split()
            if parts and parts[-1].rstrip('.').startswith('/dev/'):
                return parts[-1].rstrip('.')
    return None


def _parse_mount(stdout: str) -> str | None:
    m = _MOUNT_RE.search(stdout)
    if m:
        return m.group(1)
    for line in stdout.splitlines():
        if 'Mounted' in line and 'at' in line:
            idx = line.find(' at ')
            if idx != -1:
                return line[idx + 4:].rstrip('.')
    return None


def _parse_already_mounted(error_msg: str) -> str | None:
    m = _ALREADY_MOUNTED_RE.search(error_msg)
    if m:
        return m.group(1)
    return None
