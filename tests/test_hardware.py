"""Optional test against a real battery: set PYLONTECH_DEVICE (and optionally
PYLONTECH_BAUD / PYLONTECH_ADDRESS). Skipped otherwise."""
import os
import unittest

from pylontech_rs485 import Battery

DEV = os.environ.get("PYLONTECH_DEVICE")


@unittest.skipUnless(DEV, "PYLONTECH_DEVICE not set")
class HardwareTest(unittest.TestCase):
    def test_read(self):
        with Battery(DEV, int(os.environ.get("PYLONTECH_BAUD", 115200)),
                     int(os.environ.get("PYLONTECH_ADDRESS", 2))) as bat:
            info = bat.info()
            d = bat.read_all()
        self.assertTrue(info["model"])
        a = d["analog"]
        self.assertTrue(2500 < a["cell_min_mv"] <= a["cell_max_mv"] < 3700)
        self.assertAlmostEqual(sum(a["cells_mv"]) / 1000.0, a["voltage_v"], delta=0.5)


if __name__ == "__main__":
    unittest.main()
