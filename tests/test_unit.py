"""Unit tests for mount_image_udisks — mocked subprocess calls."""

import unittest
from unittest.mock import patch, MagicMock


class TestUdisksMount(unittest.TestCase):
    @patch('subprocess.run')
    def test_mount_image_success(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # mount_device
            MagicMock(returncode=0,
                      stdout='Mounted /dev/loop0 at /media/user/NO NAME.\n'),
        ]
        from mount_image_udisks import mount_image
        dev, mp = mount_image('/tmp/test.img', 'vfat', None)
        self.assertEqual(dev, '/dev/loop0')
        self.assertEqual(mp, '/media/user/NO NAME')

    @patch('subprocess.run')
    def test_mount_image_loop_setup_fails(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='error')
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('loop-setup failed', str(ctx.exception))

    @patch('subprocess.run')
    def test_mount_image_mount_fails_cleans_up(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # mount_device fails
            MagicMock(returncode=1, stdout='', stderr='mount error'),
            # loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('mount failed', str(ctx.exception))

    @patch('subprocess.run')
    def test_mount_image_unparsable_device(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='garbage\n', stderr='')
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('could not parse device', str(ctx.exception))

    @patch('subprocess.run')
    def test_mount_image_unparsable_mount_point(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # mount_device — success but unparsable
            MagicMock(returncode=0, stdout='no mount here\n', stderr=''),
            # loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        with self.assertRaises(RuntimeError) as ctx:
            mount_image('/tmp/test.img', 'vfat', None)
        self.assertIn('could not parse mount point', str(ctx.exception))

    @patch('subprocess.run')
    def test_mount_image_already_mounted_by_auto_mounter(self, mock_run):
        mock_run.side_effect = [
            # loop_setup
            MagicMock(returncode=0,
                      stdout='Mapped file img as /dev/loop0.\n'),
            # mount_device fails — auto-mounter beat us to it
            MagicMock(returncode=1, stdout='',
                      stderr="Error mounting /dev/loop0: "
                             "GDBus.Error:org.freedesktop.UDisks2.Error."
                             "AlreadyMounted: Device /dev/loop0 is already "
                             "mounted at `/run/media/user/IMG'."),
            # findmnt lookup for the mount point
            MagicMock(returncode=0,
                      stdout='/run/media/user/IMG /dev/loop0\n'),
            # loop_delete cleanup
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import mount_image
        dev, mp = mount_image('/tmp/test.img', 'vfat', None)
        self.assertEqual(dev, '/dev/loop0')
        self.assertEqual(mp, '/run/media/user/IMG')

    # ── unmount tests ──────────────────────────────────────────

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image(self, mock_run, mock_thread):
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        from mount_image_udisks import umount_image
        umount_image('/dev/loop0')
        self.assertEqual(mock_run.call_count, 1)
        mock_run.assert_any_call(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True, text=True)
        mock_thread.assert_called_once_with('/dev/loop0')
        mock_thread.return_value.start.assert_called_once()

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_force_fallback(self, mock_run, mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)
        mock_run.assert_any_call(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--force', '--no-user-interaction'],
            capture_output=True, text=True)
        mock_thread.assert_called_once_with('/dev/loop0')

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_lazy_fallback(self, mock_run, mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_LAZY
        umount_image('/dev/loop0', mount_point='/mnt/img',
                     strategy=UNMOUNT_LAZY)
        mock_run.assert_any_call(
            ['umount', '-l', '/mnt/img'], capture_output=True)
        mock_thread.assert_called_once_with('/dev/loop0')

    @patch('subprocess.run')
    def test_umount_image_no_mount_point_exhausted(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)
        self.assertIn('unmount failed', str(ctx.exception))

    @patch('subprocess.run')
    def test_umount_image_strategy_fail_fast(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image, UNMOUNT_FAIL_FAST
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=UNMOUNT_FAIL_FAST)
        self.assertIn('unmount failed', str(ctx.exception))
        self.assertEqual(mock_run.call_count, 1)

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_custom_strategy(self, mock_run, mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=''),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        umount_image('/dev/loop0', strategy=strategy)
        self.assertEqual(mock_run.call_count, 1)

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_retry_success_after_fail(self, mock_run,
                                                    mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
        ]
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        umount_image('/dev/loop0', strategy=strategy)
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    def test_umount_image_retry_exhausted(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image, compose, retry,\
            _unmount_normal
        strategy = compose(retry(_unmount_normal, attempts=2, delay=0))
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0', strategy=strategy)
        self.assertIn('unmount failed', str(ctx.exception))

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_strategy_force(self, mock_run, mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0, stderr=''),
        ]
        from mount_image_udisks import umount_image, UNMOUNT_FORCE
        umount_image('/dev/loop0', strategy=UNMOUNT_FORCE)

    @patch('mount_image_udisks._monitor._DetachThread')
    @patch('subprocess.run')
    def test_umount_image_default_retries_then_lazy(self, mock_run,
                                                     mock_thread):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=1, stderr='error'),
            MagicMock(returncode=0),
        ]
        from mount_image_udisks import umount_image
        umount_image('/dev/loop0', mount_point='/mnt/img')
        mock_run.assert_any_call(
            ['umount', '-l', '/mnt/img'], capture_output=True)

    @patch('subprocess.run')
    def test_umount_image_default_retries_exhausted_no_mount_point(self,
                                                                   mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='error')
        from mount_image_udisks import umount_image
        with self.assertRaises(RuntimeError) as ctx:
            umount_image('/dev/loop0')
        self.assertIn('unmount failed', str(ctx.exception))

    # ── attach / detach tests ────────────────────────────────────

    @patch('subprocess.run')
    def test_attach_image_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Mapped file img as /dev/loop0.\n')
        from mount_image_udisks import attach_image
        dev = attach_image('/tmp/test.img')
        self.assertEqual(dev, '/dev/loop0')

    @patch('subprocess.run')
    def test_attach_image_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr='error')
        from mount_image_udisks import attach_image
        with self.assertRaises(RuntimeError):
            attach_image('/tmp/test.img')

    @patch('mount_image_udisks._monitor._DetachThread')
    def test_detach_image(self, mock_thread):
        from mount_image_udisks import detach_image
        detach_image('/dev/loop0')
        mock_thread.assert_called_once_with('/dev/loop0')
        mock_thread.return_value.start.assert_called_once()

    @patch('mount_image_udisks._monitor._DetachThread')
    def test_detach_inner(self, mock_thread):
        from mount_image_udisks import detach_inner
        detach_inner('/dev/loop0')
        mock_thread.assert_called_once_with('/dev/loop0')
        mock_thread.return_value.start.assert_called_once()

    # ── umount_inner ────────────────────────────────────────────

    @patch('subprocess.run')
    def test_umount_inner_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        from mount_image_udisks import umount_inner
        umount_inner('/dev/loop0')
        mock_run.assert_called_once_with(
            ['udisksctl', 'unmount', '-b', '/dev/loop0',
             '--no-user-interaction'], capture_output=True, text=True)

    @patch('subprocess.run')
    def test_umount_inner_fails(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stderr='unmount error')
        from mount_image_udisks import umount_inner
        with self.assertRaises(RuntimeError) as ctx:
            umount_inner('/dev/loop0')
        self.assertIn('unmount failed', str(ctx.exception))
