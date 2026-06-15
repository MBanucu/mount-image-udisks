"""Integration tests — mount a real FAT image via udisksctl."""

import gzip
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_FAT_IMG_SIZE_MB = 1


def _mkfs_available():
    return subprocess.run(
        ['which', 'mkfs.fat'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _create_fat_image(path):
    subprocess.run(['truncate', '-s', f'{_FAT_IMG_SIZE_MB}M', path], check=True)
    subprocess.run(['mkfs.fat', path], check=True, capture_output=True)


def _decompress_image(gz_path, dest_path):
    CHUNK = 1024 * 1024
    zero = b'\x00' * CHUNK
    full_size = _FAT_IMG_SIZE_MB * 1024 * 1024

    fd = os.open(dest_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    os.ftruncate(fd, full_size)
    os.close(fd)

    offset = 0
    with gzip.open(gz_path, 'rb') as src, open(dest_path, 'rb+') as dst:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            if chunk != zero[:len(chunk)]:
                os.lseek(dst.fileno(), offset, os.SEEK_SET)
                dst.write(chunk)
            offset += len(chunk)


def _prepare_image():
    if _mkfs_available():
        fd, path = tempfile.mkstemp(suffix='.img', prefix='mount_image_test_')
        os.close(fd)
        _create_fat_image(path)
        return path

    gz_path = Path(__file__).parent / 'fat.img.gz'
    if not gz_path.exists():
        raise unittest.SkipTest('mkfs.fat not available and fat.img.gz fixture not found')

    fd, path = tempfile.mkstemp(suffix='.img', prefix='mount_image_test_')
    os.close(fd)
    _decompress_image(gz_path, path)
    return path


class TestUdisksIntegration(unittest.TestCase):
    _img: str

    @classmethod
    def setUpClass(cls):
        cls._img = _prepare_image()

    @classmethod
    def tearDownClass(cls):
        from mount_image_udisks._monitor import join_pending_detaches
        join_pending_detaches(timeout=15)
        try:
            os.unlink(cls._img)
        except OSError:
            pass

    def test_mount_and_umount(self):
        from mount_image_udisks import mount_image, umount_image
        try:
            dev, mp = mount_image(self._img, fstype='vfat')
        except RuntimeError as e:
            raise unittest.SkipTest(f'udisksctl not functional: {e}')
        self.assertIn('loop', dev)
        umount_image(dev, mp)

    def test_write_to_mounted_image(self):
        from mount_image_udisks import mount_image, umount_image
        try:
            dev, mp = mount_image(self._img, fstype='vfat')
        except RuntimeError as e:
            raise unittest.SkipTest(f'udisksctl not functional: {e}')

        try:
            test_file = os.path.join(mp, 'test_write.txt')
            content = 'hello from test'
            with open(test_file, 'w') as f:
                f.write(content)
            with open(test_file) as f:
                self.assertEqual(f.read(), content)
            os.unlink(test_file)
        finally:
            umount_image(dev, mp)

    def test_mount_auto_fstype(self):
        from mount_image_udisks import mount_image, umount_image
        try:
            dev, mp = mount_image(self._img, fstype=None)
        except RuntimeError as e:
            raise unittest.SkipTest(f'udisksctl not functional: {e}')
        self.assertIn('loop', dev)
        umount_image(dev, mp)

    def test_mount_with_options(self):
        from mount_image_udisks import mount_image, umount_image
        try:
            dev, mp = mount_image(self._img, fstype='vfat', options=['ro'])
        except RuntimeError as e:
            raise unittest.SkipTest(f'udisksctl not functional: {e}')
        self.assertIn('loop', dev)
        umount_image(dev, mp)

    def test_attach_and_detach(self):
        from mount_image_udisks import attach_image, detach_image
        import subprocess as sp
        try:
            dev = attach_image(self._img)
        except RuntimeError as e:
            raise unittest.SkipTest(f'udisksctl not functional: {e}')
        self.assertIn('loop', dev)
        self.assertTrue(os.path.exists(dev))
        mp = sp.run(
            ['findmnt', '-n', '-o', 'TARGET', dev],
            capture_output=True, text=True).stdout.strip()
        if mp:
            from mount_image_udisks import umount_image
            umount_image(dev, mp)
        else:
            detach_image(dev)
