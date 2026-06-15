"""Unit tests for mount_image_udisks — mocked subprocess calls."""

import unittest
from unittest.mock import patch, MagicMock


class TestUdisksMount(unittest.TestCase):
    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_success(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # _mount
            MagicMock(returncode=0,
                      stdout='Mounted /dev/loop0 at /media/user/NO NAME.\n'),
        ]
        from mount_image_udisks import mount_image
        dev, mp = mount_image('/tmp/test.img', 'vfat', None)
        self.assertEqual(dev, '/dev/loop0')
        self.assertEqual(mp, '/media/user/NO NAME')

    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_loop_setup_fails(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='error')
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('loop-setup failed', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_mount_fails_cleans_up(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # _mount fails
            MagicMock(returncode=1, stdout='', stderr='mount error'),
            # _loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('mount failed', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_unparsable_device(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='garbage\n', stderr='')
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('could not parse device', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_unparsable_mount_point(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # _mount — success but unparsable
            MagicMock(returncode=0, stdout='no mount here\n', stderr=''),
            # _loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('could not parse mount point', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_mount_image_already_mounted_by_auto_mounter(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # _mount fails — auto-mounter beat us to it
            MagicMock(returncode=1, stdout='',
                      stderr="Error mounting /dev/loop0: "
                             "GDBus.Error:org.freedesktop.UDisks2.Error."
                             "AlreadyMounted: Device /dev/loop0 is already "
                             "mounted at `/run/media/user/IMG'."),
            # findmnt lookup for the mount point
            MagicMock(returncode=0,
                      stdout='/run/media/user/IMG /dev/loop0\n'),
            # _loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        dev, mp = mount_image('/tmp/test.img', 'vfat', None)
        self.assertEqual(dev, '/dev/loop0')
        self.assertEqual(mp, '/run/media/user/IMG')

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image(self, mock_loop_size, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        from mount_image_udisks import umount_image
        umount_image('/dev/loop0')
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True, text=True)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_force_fallback(self, mock_loop_size, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)
        mock_run.assert_any_call(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--force', '--no-user-interaction'],
            capture_output=True, text=True)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_lazy_fallback(self, mock_loop_size, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_LAZY
        umount_image('/dev/loop0', mount_point='/mnt/img',
                     strategy=UNMOUNT_LAZY)
        mock_run.assert_any_call(
            ['umount', '-l', '/mnt/img'], capture_output=True)

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_image_no_mount_point_exhausted(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)
        self.assertIn('unmount failed', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_image_strategy_fail_fast(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image, UNMOUNT_FAIL_FAST
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=UNMOUNT_FAIL_FAST)
        self.assertIn('unmount failed', str(ctx.exception))
        self.assertEqual(mock_run.call_count, 1)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_custom_strategy(self, mock_loop_size, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=''),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        umount_image('/dev/loop0', strategy=strategy)
        self.assertEqual(mock_run.call_count, 2)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_retry_success_after_fail(self, mock_loop_size,
                                                    mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        umount_image('/dev/loop0', strategy=strategy)
        self.assertEqual(mock_run.call_count, 3)

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_image_retry_exhausted(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=strategy)
        self.assertIn('unmount failed', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_strategy_force(self, mock_loop_size, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_umount_image_default_retries_then_lazy(self, mock_loop_size,
                                                     mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image
        umount_image('/dev/loop0', mount_point='/mnt/img')
        mock_run.assert_any_call(
            ['umount', '-l', '/mnt/img'], capture_output=True)

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_image_default_retries_exhausted_no_mount_point(self,
                                                                   mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0')
        self.assertIn('unmount failed', str(ctx.exception))

    @patch('mount_image_udisks.subprocess.run')
    def test_attach_image_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Mapped file img as /dev/loop0.\n')
        from mount_image_udisks import attach_image
        dev = attach_image('/tmp/test.img')
        self.assertEqual(dev, '/dev/loop0')

    @patch('mount_image_udisks.subprocess.run')
    def test_attach_image_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr='error')
        from mount_image_udisks import attach_image
        with self.assertRaises(RuntimeError):
            attach_image('/tmp/test.img')

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_detach_image(self, mock_loop_size, mock_run):
        from mount_image_udisks import detach_image
        detach_image('/dev/loop0')
        mock_run.assert_called_once_with(
            ['udisksctl', 'loop-delete', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size', side_effect=[2048, 0])
    def test_detach_inner(self, mock_loop_size, mock_run):
        from mount_image_udisks import detach_inner
        detach_inner('/dev/loop0')
        mock_run.assert_called_once_with(
            ['udisksctl', 'loop-delete', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True)

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_inner_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        from mount_image_udisks import umount_inner
        umount_inner('/dev/loop0')
        mock_run.assert_called_once_with(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True, text=True)

    @patch('mount_image_udisks.subprocess.run')
    def test_umount_inner_fails(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='unmount error')
        from mount_image_udisks import umount_inner
        with self.assertRaises(RuntimeError) as ctx:
            umount_inner('/dev/loop0')
        self.assertIn('unmount failed', str(ctx.exception))


class TestUdisksMountDetachRetry(unittest.TestCase):
    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size')
    def test_detach_skipped_when_already_detached(
            self, mock_size, mock_run):
        from mount_image_udisks import umount_image
        mock_size.return_value = 0
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        umount_image('/dev/loop0')
        # Only the unmount subprocess.run call; no loop-delete
        self.assertEqual(mock_run.call_count, 1)

    @patch('mount_image_udisks.subprocess.run')
    @patch('mount_image_udisks._loop_size')
    def test_detach_retries_when_still_attached(
            self, mock_size, mock_run):
        from mount_image_udisks import umount_image
        mock_size.side_effect = [2048, 0]
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        umount_image('/dev/loop0')
        # Unmount + loop-delete
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_any_call(
            ['udisksctl', 'loop-delete', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True)


class TestParsing(unittest.TestCase):
    def test_parse_dev(self):
        from mount_image_udisks import _parse_dev
        self.assertEqual(
            _parse_dev('Mapped file img.img as /dev/loop0.\n'),
            '/dev/loop0')

    def test_parse_dev_no_match(self):
        from mount_image_udisks import _parse_dev
        self.assertIsNone(_parse_dev('garbage\n'))
        self.assertIsNone(_parse_dev(''))

    def test_parse_mount(self):
        from mount_image_udisks import _parse_mount
        self.assertEqual(
            _parse_mount(
                'Mounted /dev/loop0 at /media/user/NO NAME.\n'),
            '/media/user/NO NAME')

    def test_parse_mount_no_match(self):
        from mount_image_udisks import _parse_mount
        self.assertIsNone(_parse_mount('garbage\n'))
        self.assertIsNone(_parse_mount(''))
