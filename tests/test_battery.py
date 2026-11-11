import unittest

from pylontech_rs485 import Battery, NoResponse
from pylontech_rs485 import protocol as P
from tests.frames import FRAMES


class FakePort:
    """Replays recorded replies by request; `script` can inject failures per call."""

    def __init__(self, script=None):
        self.by_request = {req.encode(): resp.encode() for req, resp in FRAMES.values()}
        self.script = list(script or [])
        self.sent = []

    def open(self):
        return self

    def close(self):
        pass

    def transact(self, data, timeout=2.0):
        self.sent.append(data)
        if self.script:
            return self.script.pop(0)
        return self.by_request.get(data, b"")


def battery(script=None):
    return Battery(None, port=FakePort(script), retries=3)


class BatteryTest(unittest.TestCase):
    def test_read_all(self):
        with battery() as bat:
            d = bat.read_all()
        self.assertEqual(d["analog"]["cycles"], 799)
        self.assertEqual(d["alarms"]["active"], [])
        self.assertEqual(d["management"]["charge_voltage_limit_v"], 53.25)

    def test_info(self):
        with battery() as bat:
            self.assertEqual(bat.info(), {"model": "US3000C", "software_version": "2.2",
                                          "manufacturer": "Pylon", "serial": "TESTSERIAL000001",
                                          "protocol_version": "2.0"})

    def test_retry_after_noise_then_ok(self):
        good = FRAMES[P.CMD_MANAGEMENT][1].encode()
        bat = battery([b"", b"\xbf\xed", good])
        bat.timeout = 0
        self.assertEqual(bat.management()["charge_current_limit_a"], 37.0)
        self.assertEqual(len(bat.port.sent), 3)

    def test_no_response(self):
        bat = battery([b"", b"", b""])
        with self.assertRaises(NoResponse):
            bat.analog()

    def test_return_code_not_retried(self):
        body = "20024604" + "0000"
        bad = ("~%s%04X\r" % (body, P.checksum(body))).encode()
        bat = battery([bad, bad, bad])
        with self.assertRaises(P.ReturnCodeError):
            bat.analog()
        self.assertEqual(len(bat.port.sent), 1)


if __name__ == "__main__":
    unittest.main()
