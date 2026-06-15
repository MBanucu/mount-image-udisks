"""Integration tests — mount images with multiple filesystem types."""

import os
import re
import subprocess
import tempfile
import unittest

_IMG_SIZE_MB = 1

_ALREADY_MOUNTED_RE = re.compile(
    r"is already mounted at [`']([^`']+)")

_FSTYPES = {
    'vfat':  'mkfs.fat',
    'ext4':  'mkfs.ext4',
    'exfat': 'mkfs.exfat',
}


def _sudo_available():
    return subprocess.run(
        ['sudo', '-n', 'true'], capture_output=True).returncode == 0


def _available_fstypes():
    available = []
    for name, mkfs_bin in _FSTYPES.items():
        if subprocess.run(
            ['which', mkfs_bin],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            available.append(name)
    return available


def _create_image(fstype, path):
    mkfs_bin = _FSTYPES[fstype]
    subprocess.run(
        ['truncate', '-s', f'{_IMG_SIZE_MB}M', path], check=True)
    cmd = [mkfs_bin, path]
    if fstype == 'ext4':
        cmd.extend([
            '-E', f'root_owner={os.getuid()}:{os.getgid()},root_perms=0755',
        ])
    subprocess.run(cmd, check=True, capture_output=True)


class TestUdisksMultiFs(unittest.TestCase):
    _images: dict[str, str]

    @classmethod
    def setUpClass(cls):
        if not _sudo_available():
            raise unittest.SkipTest('sudo passwordless access required')

        cls._images = {}
        for fstype in _available_fstypes():
            fd, path = tempfile.mkstemp(
                suffix='.img', prefix=f'mount_image_test_{fstype}_'
            )
            os.close(fd)
            _create_image(fstype, path)
            cls._images[fstype] = path

        if not cls._images:
            raise unittest.SkipTest('no mkfs tools available')

    @classmethod
    def tearDownClass(cls):
        for path in cls._images.values():
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _mount(image_path, fstype=None):
        from mount_image_udisks import mount_image
        try:
            return mount_image(image_path, fstype=fstype)
        except RuntimeError as e:
            m = _ALREADY_MOUNTED_RE.search(str(e))
            if not m:
                raise unittest.SkipTest(
                    f'udisksctl not functional: {e}') from e
            # DE auto-mounted — unmount and retry
            mp = m.group(1)
            r = subprocess.run(
                ['findmnt', '-n', '-o', 'SOURCE', mp],
                capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                subprocess.run(
                    ['udisksctl', 'unmount', '-b', r.stdout.strip(),
                     '--no-user-interaction'],
                    capture_output=True)
            return mount_image(image_path, fstype=fstype)

    def test_mount_and_umount(self):
        from mount_image_udisks import umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=fstype)
                self.assertIn('loop', dev)
                umount_image(dev, mp)

    def test_write_to_mounted_image(self):
        from mount_image_udisks import umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=fstype)
                try:
                    test_file = os.path.join(mp, 'test_write.txt')
                    content = f'hello from {fstype}'
                    with open(test_file, 'w') as f:
                        f.write(content)
                    with open(test_file) as f:
                        self.assertEqual(f.read(), content)
                    os.unlink(test_file)
                finally:
                    umount_image(dev, mp)

    def test_mount_auto_fstype(self):
        from mount_image_udisks import umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=None)
                self.assertIn('loop', dev)
                umount_image(dev, mp)

    def test_attach_and_detach(self):
        from mount_image_udisks import attach_image, detach_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                try:
                    dev = attach_image(path)
                except RuntimeError as e:
                    raise unittest.SkipTest(
                        f'udisksctl not functional: {e}'
                    ) from e
                self.assertIn('loop', dev)
                self.assertTrue(os.path.exists(dev))
                subprocess.run(
                    ['udisksctl', 'unmount', '-b', dev,
                     '--no-user-interaction'],
                    capture_output=True)
                detach_image(dev)
