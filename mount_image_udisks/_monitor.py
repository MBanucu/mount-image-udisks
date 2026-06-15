"""udisksctl monitor integration — parser, monitor thread, detach thread."""

import re
import subprocess
import threading
import time

from mount_image_udisks._helpers import loop_delete
from mount_image_udisks._strategy import _unmount_normal

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
_BACKING_RE = re.compile(r'BackingFile:\s+(.*)')
_OP_RE = re.compile(r'Operation:\s+(\S+)')
_OBJ_RE = re.compile(r'Objects:\s+(\S+)')


def _device_name_from_path(line: str) -> str | None:
    """Extract ``'loop0'`` from ``/org/.../block_devices/loop0:``."""
    idx = line.find('/block_devices/')
    if idx == -1:
        return None
    rest = line[idx + len('/block_devices/'):]
    colon = rest.find(':')
    if colon != -1:
        rest = rest[:colon]
    return rest.strip()


class _MonitorParser:
    """Stateful line parser for ``udisksctl monitor`` output.

    Feeds one stripped line at a time.  Tracks job context (creation,
    removal, operation, target objects) so that each ``(operation,
    objects)`` pair is emitted exactly once per job, and remembers the
    last-seen block device so that indented property lines are
    attributed correctly.
    """
    __slots__ = ('_in_job', '_job_op', '_job_objects', '_emitted',
                 '_current_device')

    def __init__(self):
        self._in_job = False
        self._job_op = ''
        self._job_objects = ''
        self._emitted = False
        self._current_device = ''

    def feed(self, line: str) -> tuple[str, dict] | None:
        """Parse one line.  Returns ``(event_type, data)`` or ``None``."""
        clean = _ANSI_RE.sub('', line)

        if clean.startswith('Added /org/freedesktop/UDisks2/jobs/'):
            self._in_job = True
            self._job_op = ''
            self._job_objects = ''
            self._emitted = False
            return None

        if clean.startswith('Removed /org/freedesktop/UDisks2/jobs/'):
            self._in_job = False
            return None

        if self._in_job and not self._emitted:
            m = _OP_RE.search(clean)
            if m:
                self._job_op = m.group(1)
            m = _OBJ_RE.search(clean)
            if m:
                self._job_objects = m.group(1)
            if self._job_op and self._job_objects:
                self._emitted = True
                return ('job', {'op': self._job_op,
                                'objects': self._job_objects})
            return None

        device = _device_name_from_path(clean)
        if device:
            self._current_device = device

        if self._current_device:
            m = _BACKING_RE.search(clean)
            if m:
                return ('loop_prop', {
                    'device': self._current_device,
                    'prop': 'BackingFile',
                    'value': m.group(1).strip(),
                })
        return None


class _UdisksMonitor(threading.Thread):
    """Background thread: ``udisksctl monitor`` -> parsed events.

    Sets :attr:`backing_cleared` when *device_name*'s ``BackingFile``
    property becomes empty, and :attr:`mount_detected` when a
    ``filesystem-mount`` job targeting *device_name* appears.
    """

    def __init__(self, device_name: str):
        super().__init__(daemon=True)
        self._name = device_name
        self.backing_cleared = threading.Event()
        self.mount_detected = threading.Event()
        self._stop = threading.Event()
        self._parser = _MonitorParser()

    def reset_events(self):
        self.backing_cleared.clear()
        self.mount_detected.clear()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            proc = subprocess.Popen(
                ['udisksctl', 'monitor'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            return

        try:
            for line in proc.stdout:
                if self._stop.is_set():
                    break
                event = self._parser.feed(line)
                if event is None:
                    continue
                etype, data = event
                if etype == 'job':
                    if (data['op'] == 'filesystem-mount' and
                            self._name in data['objects']):
                        self.mount_detected.set()
                elif etype == 'loop_prop':
                    if (data['device'] == self._name and
                            data['prop'] == 'BackingFile' and
                            not data['value']):
                        self.backing_cleared.set()
        finally:
            proc.stdout.close()
            proc.terminate()
            proc.wait()


class _DetachThread(threading.Thread):
    """Daemon thread: runs the detach state machine.

    Issues ``loop-delete``, then waits for ``udisksctl monitor``
    feedback.  If the auto-mounter re-mounts, unmounts and retries.
    Exits once the device is confirmed fully detached.
    """

    def __init__(self, device: str):
        super().__init__(daemon=True)
        self._device = device
        self._name = device.split('/')[-1]

    def run(self):
        monitor = _UdisksMonitor(self._name)
        monitor.start()
        try:
            while True:
                monitor.reset_events()
                loop_delete(self._device)
                print(f"device {self._device}: loop-delete issued, "
                      f"waiting for monitor...")

                deadline = time.monotonic() + 30.0
                while time.monotonic() < deadline:
                    if monitor.mount_detected.is_set():
                        print(f"device {self._device}: auto-mounter "
                              f"re-mounted, unmounting...")
                        _unmount_normal(self._device, None)
                        break

                    if monitor.backing_cleared.is_set():
                        time.sleep(0.3)
                        if monitor.mount_detected.is_set():
                            _unmount_normal(self._device, None)
                            break
                        print(f"device {self._device} detached")
                        return
                    time.sleep(0.1)
                else:
                    print(f"device {self._device}: detach timed out, "
                          f"giving up")
                    return
        finally:
            monitor.stop()
            monitor.join(timeout=3)


def detach_loop(device: str):
    """Detach *device* in a background thread (non-blocking).

    Spawns a daemon thread that issues ``loop-delete`` and watches
    ``udisksctl monitor`` for the device to confirm full detachment.
    If the desktop auto-mounter (gvfs) re-attaches and re-mounts the
    device between delete attempts, the thread unmounts and retries.
    """
    print("")
    _DetachThread(device).start()
