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
import threading
import time
from typing import Callable

_DEV_RE = re.compile(r'as\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)
_MOUNT_RE = re.compile(r'at\s+(/[^\s]+?)\.?\s*$', re.MULTILINE)


def mount_image(image_path: str, fstype: str | None = None,
                options: list[str] | None = None) -> tuple[str, str]:
    """Attach *image_path* via udisksctl and mount it.

    Returns ``(device, mount_point)``.
    Raises ``RuntimeError`` on failure.
    """
    loop_dev = _loop_setup(image_path)

    # Try to mount ourselves.  If a DE auto-mounter (udisks2, gvfs, etc.)
    # already mounted the device, udisksctl mount fails with AlreadyMounted.
    # We handle this by error instead of probing upfront (blkid + findmnt)
    # because the probing approach has a race: the auto-mounter can finish
    # between our check and our mount call, producing the same error anyway.
    try:
        mount_point = _mount(loop_dev, fstype, options)
    except RuntimeError as e:
        if 'AlreadyMounted' in str(e):
            r = subprocess.run(
                ['findmnt', '-n', '-o', 'TARGET,SOURCE', '--source', loop_dev],
                capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                target, source = r.stdout.strip().split(None, 1)
                _loop_delete(loop_dev)
                return source, target
        _loop_delete(loop_dev)
        raise
    return loop_dev, mount_point


# ── unmount strategy API ─────────────────────────────────────────────

StepFn = Callable[[str, str | None], tuple[bool, str]]


def _unmount_normal(device: str, _mount_point: str | None) -> tuple[bool, str]:
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def _unmount_force(device: str, _mount_point: str | None) -> tuple[bool, str]:
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device,
         '--force', '--no-user-interaction'],
        capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def _unmount_lazy(_device: str, mount_point: str | None) -> tuple[bool, str]:
    if mount_point:
        subprocess.run(['umount', '-l', mount_point], capture_output=True)
        return True, ''
    return False, 'no mount point for lazy unmount'


def compose(*steps: StepFn) -> StepFn:
    """Chain unmount strategies: each runs only if the previous failed."""
    def _run(device: str, mount_point: str | None = None) -> tuple[bool, str]:
        last_err = ''
        for step in steps:
            ok, err = step(device, mount_point)
            if ok:
                return True, ''
            last_err = err
        return False, last_err
    return _run


def retry(step: StepFn, attempts: int = 3, delay: float = 0.5) -> StepFn:
    """Retry a strategy *attempts* times with *delay* seconds between."""
    def _run(device: str, mount_point: str | None = None) -> tuple[bool, str]:
        last_err = ''
        for _ in range(attempts):
            ok, err = step(device, mount_point)
            if ok:
                return True, ''
            last_err = err
            time.sleep(delay)
        return False, last_err
    return _run


# Pre-built strategies
UNMOUNT_FAIL_FAST:          StepFn = compose(_unmount_normal)
UNMOUNT_RETRY:              StepFn = compose(retry(_unmount_normal))
UNMOUNT_FORCE:              StepFn = compose(_unmount_normal, _unmount_force)
UNMOUNT_LAZY:               StepFn = compose(_unmount_normal, _unmount_lazy)
UNMOUNT_FORCE_THEN_LAZY:    StepFn = compose(_unmount_normal, _unmount_force,
                                              _unmount_lazy)
UNMOUNT_RETRY_THEN_LAZY:    StepFn = compose(retry(_unmount_normal),
                                              _unmount_lazy)


def umount_image(device: str, mount_point: str | None = None,
                 strategy: StepFn = UNMOUNT_RETRY_THEN_LAZY):
    """Unmount and detach a disk image.

    *strategy* is a callable ``(device, mount_point) -> (ok, err)``.
    Use :func:`compose` and :func:`retry` to build custom strategies,
    or pick from the pre-built ones:

    - ``UNMOUNT_FAIL_FAST`` — normal unmount, raise on failure
    - ``UNMOUNT_RETRY`` — normal unmount, retry 3× with 0.5 s delay
    - ``UNMOUNT_FORCE`` — normal, then ``--force``
    - ``UNMOUNT_LAZY`` — normal, then ``umount -l`` (needs *mount_point*)
    - ``UNMOUNT_FORCE_THEN_LAZY`` — normal → force → lazy
    - ``UNMOUNT_RETRY_THEN_LAZY`` (**default**) — retry normal 3× → lazy

    A custom strategy::

        strategy = compose(retry(_unmount_normal, attempts=5),
                           _unmount_force,
                           _unmount_lazy)
    """
    ok, err = strategy(device, mount_point)
    if not ok:
        raise RuntimeError(f"udisksctl unmount failed: {err.strip()}")

    _detach_loop(device)


def attach_image(image_path: str) -> str:
    """Attach *image_path* as a block device without mounting.

    Returns the device path (e.g. ``/dev/loop0``).
    Raises ``RuntimeError`` on failure.
    """
    return _loop_setup(image_path)


def detach_image(device: str):
    """Detach a block device."""
    _detach_loop(device)


def umount_inner(device: str):
    """Unmount without detach. Used by the mount-image orchestrator."""
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl unmount failed: {r.stderr.strip()}")


def detach_inner(device: str):
    """Detach without unmount. Used by the mount-image orchestrator."""
    _detach_loop(device)


# ── internal helpers ────────────────────────────────────────────────

def _loop_setup(image_path: str) -> str:
    cmd = ['udisksctl', 'loop-setup', '-f', str(image_path),
           '--no-user-interaction']

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


def _detach_loop(device: str):
    """Detach a loop device, retrying in the background if blocked.

    Tries one inline delete first.  If the backing file is still
    attached (e.g. a DE auto-mounter re-mounted), spawns a daemon
    thread that retries indefinitely with normal unmount between
    attempts.
    """
    subprocess.run(
        ['udisksctl', 'loop-delete', '-b', device, '--no-user-interaction'],
        capture_output=True)
    if _loop_size(device) == 0:
        return

    def _retry():
        while _loop_size(device) != 0:
            subprocess.run(
                ['udisksctl', 'loop-delete', '-b', device,
                 '--no-user-interaction'],
                capture_output=True)
            if _loop_size(device) == 0:
                return
            subprocess.run(
                ['udisksctl', 'unmount', '-b', device,
                 '--no-user-interaction'],
                capture_output=True)
            time.sleep(0.1)

    threading.Thread(target=_retry, daemon=True).start()


def _loop_size(device: str) -> int:
    """Return the backing-file size of a loop device, or 0 if detached."""
    name = device.split('/')[-1]
    try:
        with open(f'/sys/block/{name}/size') as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def _parse_dev(stdout: str) -> str | None:
    m = _DEV_RE.search(stdout)
    if m:
        return m.group(1)
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
