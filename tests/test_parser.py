"""Tests for parsing helpers and udisksctl monitor parser."""

import unittest


class TestMonitorParser(unittest.TestCase):
    """Tests for _MonitorParser — udisksctl monitor output parser."""

    def test_job_mount_on_loop_device(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        self.assertIsNone(p.feed('Added /org/freedesktop/UDisks2/jobs/1'))
        self.assertIsNone(p.feed('  org.freedesktop.UDisks2.Job:'))
        self.assertIsNone(p.feed('    Operation:          filesystem-mount'))
        result = p.feed('    Objects:            '
                        '/org/freedesktop/UDisks2/block_devices/loop0')
        self.assertEqual(result, ('job', {
            'op': 'filesystem-mount',
            'objects': '/org/freedesktop/UDisks2/block_devices/loop0',
        }))
        # No re-emit within same job
        self.assertIsNone(p.feed('    Bytes:              0'))
        # Removal exits job context
        self.assertIsNone(p.feed('Removed /org/freedesktop/UDisks2/jobs/1'))

    def test_job_with_ansi(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        p.feed('Added \x1b[1m\x1b[32m/org/freedesktop/UDisks2/jobs/2\x1b[0m')
        p.feed('  \x1b[1m\x1b[35morg.freedesktop.UDisks2.Job:\x1b[0m')
        p.feed('    \x1b[37mOperation:\x1b[0m          filesystem-unmount')
        result = p.feed('    \x1b[37mObjects:\x1b[0m            '
                        '/org/freedesktop/UDisks2/block_devices/loop0')
        self.assertEqual(result, ('job', {
            'op': 'filesystem-unmount',
            'objects': '/org/freedesktop/UDisks2/block_devices/loop0',
        }))

    def test_job_ignores_unrelated_operation(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        p.feed('Added /org/freedesktop/UDisks2/jobs/3')
        p.feed('    Operation:          loop-setup')
        result = p.feed('    Objects:            '
                        '/org/freedesktop/UDisks2/block_devices/loop1')
        # Still emitted — caller filters by operation
        self.assertEqual(result, ('job', {
            'op': 'loop-setup',
            'objects': '/org/freedesktop/UDisks2/block_devices/loop1',
        }))

    def test_backing_file_cleared(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        # Header line sets current device context
        result = p.feed(
            '/org/freedesktop/UDisks2/block_devices/loop0: '
            'org.freedesktop.UDisks2.Loop: Properties Changed')
        self.assertIsNone(result)
        # Indented property line uses current device
        result = p.feed('  BackingFile:          ')
        self.assertEqual(result, ('loop_prop', {
            'device': 'loop0',
            'prop': 'BackingFile',
            'value': '',
        }))

    def test_backing_file_set(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        p.feed(
            '/org/freedesktop/UDisks2/block_devices/loop1: '
            'org.freedesktop.UDisks2.Loop: Properties Changed')
        result = p.feed('  BackingFile:          /tmp/foo.img')
        self.assertEqual(result, ('loop_prop', {
            'device': 'loop1',
            'prop': 'BackingFile',
            'value': '/tmp/foo.img',
        }))

    def test_device_switch_resets_context(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        # Set context to loop0
        p.feed('/org/freedesktop/UDisks2/block_devices/loop0: '
               'org.freedesktop.UDisks2.Block: Properties Changed')
        self.assertIsNone(p.feed('  IdType:               vfat'))
        # Switch to loop1
        p.feed('/org/freedesktop/UDisks2/block_devices/loop1: '
               'org.freedesktop.UDisks2.Loop: Properties Changed')
        result = p.feed('  BackingFile:          /tmp/other.img')
        self.assertEqual(result, ('loop_prop', {
            'device': 'loop1',
            'prop': 'BackingFile',
            'value': '/tmp/other.img',
        }))

    def test_unrelated_lines_ignored(self):
        from mount_image_udisks._monitor import _MonitorParser
        p = _MonitorParser()
        self.assertIsNone(p.feed('Monitoring the udisks daemon. '
                                  'Press Ctrl+C to exit.'))
        self.assertIsNone(p.feed('The udisks-daemon is running '
                                  '(name-owner :1.72).'))
        self.assertIsNone(p.feed(''))


class TestParsing(unittest.TestCase):
    def test_parse_dev(self):
        from mount_image_udisks._helpers import parse_dev
        self.assertEqual(
            parse_dev('Mapped file img.img as /dev/loop0.\n'),
            '/dev/loop0')

    def test_parse_dev_no_match(self):
        from mount_image_udisks._helpers import parse_dev
        self.assertIsNone(parse_dev('garbage\n'))
        self.assertIsNone(parse_dev(''))

    def test_parse_mount(self):
        from mount_image_udisks._helpers import parse_mount
        self.assertEqual(
            parse_mount(
                'Mounted /dev/loop0 at /media/user/NO NAME.\n'),
            '/media/user/NO NAME')

    def test_parse_mount_no_match(self):
        from mount_image_udisks._helpers import parse_mount
        self.assertIsNone(parse_mount('garbage\n'))
        self.assertIsNone(parse_mount(''))
