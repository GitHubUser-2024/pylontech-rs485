"""High-level access to one Pylontech battery module over RS485."""

import time

from . import protocol as P
from .port import SerialPort

DEFAULT_BAUD = 115200
DEFAULT_ADDRESS = 2


class NoResponse(P.ProtocolError):
    """The battery did not send anything (wiring, baud rate, address, adapter)."""


class Battery:
    """One battery module on an RS485 bus.

    ::

        with Battery("/dev/serial/by-id/usb-...") as bat:
            print(bat.read_all())
    """

    def __init__(self, device, baud=DEFAULT_BAUD, address=DEFAULT_ADDRESS, timeout=2.0, retries=3,
                 port=None):
        self.address, self.timeout, self.retries = address, timeout, retries
        self.port = port if port is not None else SerialPort(device, baud)

    def __enter__(self):
        self.port.open()
        return self

    def __exit__(self, *exc):
        self.port.close()

    def raw(self, cid2, info=None, address=None):
        """Send one command, return the raw reply bytes (no validation, no retry)."""
        adr = self.address if address is None else address
        if info is None:
            info = "%02X" % adr
        return self.port.transact(P.build_frame(adr, cid2, info), self.timeout)

    def command(self, cid2, info=None):
        """Send one command and return the validated response INFO (hex string).

        Retries on missing or corrupt replies; a valid frame with a non-OK RTN is
        raised immediately (ReturnCodeError).
        """
        last = None
        for attempt in range(self.retries):
            reply = self.raw(cid2, info)
            if not reply:
                last = NoResponse("no reply to command 0x%02X at address %d" % (cid2, self.address))
            else:
                try:
                    return P.parse_frame(reply)["info"]
                except P.ReturnCodeError:
                    raise
                except P.ProtocolError as e:
                    last = e
            time.sleep(0.3)
        raise last

    def protocol_version(self):
        """Ping: returns the protocol version byte from the reply's VER field, e.g. '2.0'."""
        adr = self.address
        for attempt in range(self.retries):
            reply = self.port.transact(P.build_frame(adr, P.CMD_PROTOCOL_VERSION, ""), self.timeout)
            if reply:
                ver = P.parse_frame(reply)["ver"]
                return "%d.%d" % (ver >> 4, ver & 0xF)
            time.sleep(0.3)
        raise NoResponse("no reply at address %d" % adr)

    def analog(self):
        return P.decode_analog(self.command(P.CMD_ANALOG))

    def alarms(self):
        return P.decode_alarm(self.command(P.CMD_ALARM))

    def management(self):
        return P.decode_management(self.command(P.CMD_MANAGEMENT))

    def manufacturer(self):
        return P.decode_manufacturer(self.command(P.CMD_MANUFACTURER, ""))

    def serial_number(self):
        return P.decode_serial(self.command(P.CMD_SERIAL))["serial"]

    def info(self):
        """Static identity: model, software version, manufacturer, serial, protocol version."""
        out = self.manufacturer()
        out["serial"] = self.serial_number()
        out["protocol_version"] = self.protocol_version()
        return out

    def read_all(self):
        """Live values: analog + alarms + management limits, with a unix timestamp."""
        return {
            "timestamp": int(time.time()),
            "address": self.address,
            "analog": self.analog(),
            "alarms": self.alarms(),
            "management": self.management(),
        }
