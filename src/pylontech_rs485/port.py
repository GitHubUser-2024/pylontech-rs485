"""Minimal POSIX serial port using only the standard library (termios)."""

import errno
import fcntl
import os
import termios
import time

BAUD_RATES = {
    1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800, 9600: termios.B9600,
    19200: termios.B19200, 38400: termios.B38400, 57600: termios.B57600, 115200: termios.B115200,
}


class PortBusy(OSError):
    """Another process holds the lock on the serial device."""


class SerialPort:
    """Raw 8N1 serial port. Takes an exclusive flock so two readers never interleave.

    Use as a context manager::

        with SerialPort("/dev/ttyUSB0", 115200) as p:
            reply = p.transact(b"...", timeout=2.0)
    """

    def __init__(self, device, baud=115200, lock_timeout=10.0):
        if baud not in BAUD_RATES:
            raise ValueError("unsupported baud rate %r (supported: %s)" % (baud, sorted(BAUD_RATES)))
        self.device, self.baud, self.lock_timeout = device, baud, lock_timeout
        self.fd = None

    def open(self):
        fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            self._lock(fd)
            a = termios.tcgetattr(fd)
            a[0] = 0                                                   # iflag: raw
            a[1] = 0                                                   # oflag: raw
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL        # 8N1, no flow control
            a[3] = 0                                                   # lflag: raw
            a[4] = a[5] = BAUD_RATES[self.baud]
            a[6][termios.VMIN] = 0
            a[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, a)
        except Exception:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def _lock(self, fd):
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() > deadline:
                    raise PortBusy("%s is locked by another process" % self.device)
                time.sleep(0.1)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)  # also releases the flock
            self.fd = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def transact(self, data, timeout=2.0, terminator=b"\r"):
        """Flush, write `data`, read until `terminator` or `timeout` seconds. Returns bytes."""
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        os.write(self.fd, data)
        termios.tcdrain(self.fd)
        buf = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                chunk = b""
            if chunk:
                buf += chunk
                if terminator and buf.endswith(terminator):
                    break
            else:
                time.sleep(0.01)
        return buf
