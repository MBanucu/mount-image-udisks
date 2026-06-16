"""Integration tests — mount images with multiple filesystem types."""

import gzip
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_FIXTURE_DIR = Path(__file__).parent

# (mkfs_binary, image_size_mb, gzip_fixture_name)
_FSTYPES = {
    'vfat':  ('mkfs.fat',   1, 'fat.img.gz'),
    'ext4':  ('mkfs.ext4',  1, 'ext4.img.gz'),
    'exfat': ('mkfs.exfat', 4, 'exfat.img.gz'),
}


def _mkfs_available(mkfs_bin):
    return subprocess.run(
        ['which', mkfs_bin],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _fixture_available(fixture_name):
    return (_FIXTURE_DIR / fixture_name).exists()


def _available_fstypes():
    available = []
    for name, (mkfs_bin, _size, fixture) in _FSTYPES.items():
        if _mkfs_available(mkfs_bin) or _fixture_available(fixture):
            available.append(name)
    return available


def _decompress_image(gz_path, dest_path, full_size_mb):
    CHUNK = 1024 * 1024
    zero = b'\x00' * CHUNK
    full_size = full_size_mb * 1024 * 1024

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


def _create_image(fstype, path):
    mkfs_bin, size_mb, fixture = _FSTYPES[fstype]

    if _mkfs_available(mkfs_bin):
        subprocess.run(
            ['truncate', '-s', f'{size_mb}M', path], check=True)
        cmd = [mkfs_bin]
        if fstype == 'ext4':
            cmd.extend(['-E', 'root_perms=0777'])
        cmd.append(path)
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # fall back to plain mkfs if extended options are unsupported
            subprocess.run(
                [mkfs_bin, path], check=True, capture_output=True)
        return

    gz_path = _FIXTURE_DIR / fixture
    if not gz_path.exists():
        raise unittest.SkipTest(
            f'{mkfs_bin} not available and {fixture} fixture not found')
    _decompress_image(gz_path, path, size_mb)


class TestUdisksMultiFs(unittest.TestCase):
    _images: dict[str, str]

    @classmethod
    def setUpClass(cls):
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
        from unmount_image._monitor import join_pending_detaches
        join_pending_detaches(timeout=60)
        for path in cls._images.values():
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _mount(image_path, fstype=None, options=None):
        from mount_image_udisks import mount_image
        try:
            return mount_image(image_path, fstype=fstype, options=options)
        except RuntimeError as e:
            raise unittest.SkipTest(
                f'udisksctl not functional: {e}') from e

    def test_mount_and_umount(self):
        from mount_image_udisks import umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=fstype)
                self.assertIn('loop', dev)
                umount_image(dev, mp)

    def test_write_to_mounted_image(self):
        from mount_image_udisks import mount_image, umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=fstype)
                if not os.access(mp, os.W_OK):
                    umount_image(dev, mp)
                    # try fixture as fallback
                    _, _, fixture_name = _FSTYPES[fstype]
                    fixture_path = _FIXTURE_DIR / fixture_name
                    if fixture_path.exists():
                        fd, fb_path = tempfile.mkstemp(
                            suffix='.img', prefix='mount_image_fb_')
                        os.close(fd)
                        try:
                            _decompress_image(
                                fixture_path, fb_path,
                                _FSTYPES[fstype][1])
                            dev, mp = self._mount(fb_path, fstype=fstype)
                            if not os.access(mp, os.W_OK):
                                umount_image(dev, mp)
                                raise unittest.SkipTest(
                                    f'{fstype} mount not user-writable')
                        finally:
                            try:
                                os.unlink(fb_path)
                            except OSError:
                                pass
                    else:
                        raise unittest.SkipTest(
                            f'{fstype} mount not user-writable')
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

    def test_mount_with_options(self):
        from mount_image_udisks import umount_image
        for fstype, path in self._images.items():
            with self.subTest(fstype=fstype):
                dev, mp = self._mount(path, fstype=fstype, options=['ro'])
                self.assertIn('loop', dev)
                umount_image(dev, mp)

    def test_attach_and_detach(self):
        from mount_image_udisks import attach_image, detach_image, umount_image
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
                mp = subprocess.run(
                    ['findmnt', '-n', '-o', 'TARGET', dev],
                    capture_output=True, text=True).stdout.strip()
                if mp:
                    umount_image(dev, mp)
                else:
                    detach_image(dev)
