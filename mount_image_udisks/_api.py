"""Public API for mount-image-udisks."""

import subprocess

from mount_image_udisks._helpers import loop_setup, mount_device, loop_delete
from mount_image_udisks._monitor import detach_loop
from mount_image_udisks._strategy import StepFn, UNMOUNT_RETRY_THEN_LAZY


def mount_image(image_path: str, fstype: str | None = None,
                options: list[str] | None = None) -> tuple[str, str]:
    """Attach *image_path* via udisksctl and mount it.

    Returns ``(device, mount_point)``.
    Raises ``RuntimeError`` on failure.
    """
    loop_dev = loop_setup(image_path)

    try:
        mount_point = mount_device(loop_dev, fstype, options)
    except RuntimeError as e:
        if 'AlreadyMounted' in str(e):
            r = subprocess.run(
                ['findmnt', '-n', '-o', 'TARGET,SOURCE', '--source', loop_dev],
                capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                target, source = r.stdout.strip().split(None, 1)
                loop_delete(loop_dev)
                return source, target
        loop_delete(loop_dev)
        raise
    return loop_dev, mount_point


def umount_image(device: str, mount_point: str | None = None,
                 strategy: StepFn = UNMOUNT_RETRY_THEN_LAZY):
    """Unmount and detach a disk image.

    *strategy* is a callable ``(device, mount_point) -> (ok, err)``.
    Use :func:`compose` and :func:`retry` to build custom strategies,
    or pick from the pre-built ones:

    - ``UNMOUNT_FAIL_FAST`` — normal unmount, raise on failure
    - ``UNMOUNT_RETRY`` — normal unmount, retry 3x with 0.5 s delay
    - ``UNMOUNT_FORCE`` — normal, then ``--force``
    - ``UNMOUNT_LAZY`` — normal, then ``umount -l`` (needs *mount_point*)
    - ``UNMOUNT_FORCE_THEN_LAZY`` — normal -> force -> lazy
    - ``UNMOUNT_RETRY_THEN_LAZY`` (**default**) — retry normal 3x -> lazy

    A custom strategy::

        strategy = compose(retry(_unmount_normal, attempts=5),
                           _unmount_force,
                           _unmount_lazy)
    """
    ok, err = strategy(device, mount_point)
    if not ok:
        raise RuntimeError(f"udisksctl unmount failed: {err.strip()}")

    detach_loop(device)


def attach_image(image_path: str) -> str:
    """Attach *image_path* as a block device without mounting.

    Returns the device path (e.g. ``/dev/loop0``).
    Raises ``RuntimeError`` on failure.
    """
    return loop_setup(image_path)


def detach_image(device: str):
    """Detach a block device."""
    detach_loop(device)


def umount_inner(device: str):
    """Unmount without detach. Used by the mount-image orchestrator."""
    r = subprocess.run(
        ['udisksctl', 'unmount', '-b', device, '--no-user-interaction'],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"udisksctl unmount failed: {r.stderr.strip()}")


def detach_inner(device: str):
    """Detach without unmount. Used by the mount-image orchestrator."""
    detach_loop(device)
