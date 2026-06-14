"""Disk image mounting via udisksctl (Linux)."""

import subprocess
import time


def mount_image(image_path: str, fstype: str = 'exfat',
                options: list[str] | None = None) -> tuple[str, str]:
    """Attach *image_path* via udisksctl and mount it.

    Returns ``(device, mount_point)``.
    Raises ``RuntimeError`` on failure.
    """
    r = subprocess.run(
        ['udisksctl', 'loop-setup', '-f', str(image_path),
         '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl loop-setup failed: {r.stderr}")

    loop_dev = _parse_dev(r.stdout)
    if not loop_dev:
        raise RuntimeError(
            f"udisksctl loop-setup: could not parse device from: {r.stdout}")

    r = subprocess.run(
        ['udisksctl', 'mount', '-b', loop_dev, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(
            ['udisksctl', 'loop-delete', '-b', loop_dev,
             '--no-user-interaction'],
            capture_output=True)
        raise RuntimeError(f"udisksctl mount failed: {r.stderr}")

    mount_point = _parse_mount(r.stdout)
    if not mount_point:
        raise RuntimeError(
            f"udisksctl mount: could not parse mount point from: {r.stdout}")

    return loop_dev, mount_point


def umount_image(device: str, mount_point: str | None = None):
    """Unmount and detach a disk image."""
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl unmount failed: {r.stderr.strip()}")
    time.sleep(0.3)

    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)


def attach_image(image_path: str) -> str:
    """Attach *image_path* as a block device without mounting.

    Returns the device path (e.g. ``/dev/loop0``).
    Raises ``RuntimeError`` on failure.
    """
    r = subprocess.run(
        ['udisksctl', 'loop-setup', '-f', str(image_path),
         '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl loop-setup failed: {r.stderr}")
    loop_dev = _parse_dev(r.stdout)
    if not loop_dev:
        raise RuntimeError(
            f"udisksctl loop-setup: could not parse device from: {r.stdout}")
    return loop_dev


def detach_image(device: str):
    """Detach a block device."""
    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)


def _parse_dev(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if ' as ' in line:
            parts = line.strip().split()
            if parts and parts[-1].rstrip('.').startswith('/dev/'):
                return parts[-1].rstrip('.')
    return None


def _parse_mount(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if 'Mounted' in line and 'at' in line:
            idx = line.find(' at ')
            if idx != -1:
                return line[idx + 4:].rstrip('.')
    return None


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
