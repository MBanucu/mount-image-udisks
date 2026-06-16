"""Unit tests for mount_image_udisks — mocked subprocess calls."""

import unittest
from unittest.mock import patch, MagicMock


class TestUdisksMount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from unmount_image._monitor import join_pending_detaches
        join_pending_detaches(timeout=60)

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
