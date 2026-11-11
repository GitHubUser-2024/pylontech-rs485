import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from pylontech_rs485 import cli
from tests.test_battery import FakePort


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        buf = io.StringIO()
        with mock.patch("pylontech_rs485.battery.SerialPort", lambda *a, **k: FakePort()), redirect_stdout(buf):
            rc = cli.main(argv)
        return rc, buf.getvalue()

    def test_read_with_history(self):
        with tempfile.TemporaryDirectory() as d:
            h = os.path.join(d, "h.json")
            rc, out = self.run_cli(["-d", "/dev/null", "read", "--history", h])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["analog"]["cell_spread_mv"], 1)
            self.assertEqual(data["history"]["samples"], 1)
            rc, out = self.run_cli(["stats", "--history", h])
            self.assertEqual(json.loads(out)["cells"][8]["now_mv"], 3312)

    def test_info(self):
        rc, out = self.run_cli(["-d", "/dev/null", "--pretty", "info"])
        self.assertEqual(json.loads(out)["model"], "US3000C")

    def test_raw(self):
        rc, out = self.run_cli(["-d", "/dev/null", "raw", "92"])
        d = json.loads(out)
        self.assertEqual(d["request"], "~20024692E00202FD2E")
        self.assertEqual(d["parsed"]["info"], "02D002AFC80172FE8EC0")

    def test_no_device(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            cli.main(["read"])


if __name__ == "__main__":
    unittest.main()
