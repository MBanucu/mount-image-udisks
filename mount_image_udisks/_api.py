"""Public API for mount-image-udisks."""

import subprocess

from mount_image_udisks._helpers import loop_setup, mount_device, loop_delete


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


def attach_image(image_path: str) -> str:
    """Attach *image_path* as a block device without mounting.

    Returns the device path (e.g. ``/dev/loop0``).
    Raises ``RuntimeError`` on failure.
    """
    return loop_setup(image_path)
