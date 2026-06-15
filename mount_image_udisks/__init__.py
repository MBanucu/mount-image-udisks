"""Disk image mounting via udisksctl (Linux, no sudo needed for active sessions).

Uses ``udisksctl loop-setup`` to create loop devices and ``udisksctl mount``
to mount filesystems via UDisks2.  PolKit grants active local sessions
permission without a password on most desktop distributions.

Key advantages over the sudo strategy:
  - No root password required (uses polkit authorisation)
  - Mount point managed by udisks2 (under /run/media/$USER/)
  - Automatic filesystem type detection when fstype is not specified
"""

from mount_image_udisks._api import (
    attach_image,
    detach_image,
    detach_inner,
    mount_image,
    umount_image,
    umount_inner,
)
from mount_image_udisks._strategy import (
    StepFn,
    UNMOUNT_FAIL_FAST,
    UNMOUNT_FORCE,
    UNMOUNT_FORCE_THEN_LAZY,
    UNMOUNT_LAZY,
    UNMOUNT_RETRY,
    UNMOUNT_RETRY_THEN_LAZY,
    _unmount_force,
    _unmount_lazy,
    _unmount_normal,
    compose,
    retry,
)
