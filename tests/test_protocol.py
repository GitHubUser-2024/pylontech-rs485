import unittest

from pylontech_rs485 import protocol as P
from tests.frames import FRAMES


def info_of(cid2):
    return P.parse_frame(FRAMES[cid2][1])["info"]


class FramingTest(unittest.TestCase):
    def test_requests_match_recorded(self):
        for cid2, (req, _) in FRAMES.items():
            info = "" if cid2 in (P.CMD_PROTOCOL_VERSION, P.CMD_MANUFACTURER) else "02"
            self.assertEqual(P.build_frame(2, cid2, info).decode(), req, hex(cid2))

    def test_length_field(self):
        self.assertEqual(P.length_field(0), 0x0000)
        self.assertEqual(P.length_field(2), 0xE002)
        self.assertEqual(P.length_field(0x7A), 0xF07A)
        with self.assertRaises(ValueError):
            P.length_field(0x1000)

    def test_all_recorded_replies_parse(self):
        for cid2, (_, resp) in FRAMES.items():
            f = P.parse_frame(resp.encode())
            self.assertEqual((f["address"], f["cid1"], f["rtn"]), (2, 0x46, 0), hex(cid2))

    def test_bad_checksum(self):
        bad = FRAMES[0x92][1].replace("F91C", "F91D")
        with self.assertRaisesRegex(P.ProtocolError, "CHKSUM"):
            P.parse_frame(bad)

    def test_bad_lchksum(self):
        body = "20024600" + "0014" + "02D002AFC80172FE8EC0"
        with self.assertRaisesRegex(P.ProtocolError, "LCHKSUM"):
            P.parse_frame("~%s%04X\r" % (body, P.checksum(body)))

    def test_return_code(self):
        body = "20024604" + "0000"
        with self.assertRaises(P.ReturnCodeError) as cm:
            P.parse_frame("~%s%04X\r" % (body, P.checksum(body)))
        self.assertEqual(cm.exception.rtn, 4)

    def test_garbage(self):
        for junk in (b"", b"\xbf\xed", b"~2002", "hello world, not a frame"):
            with self.assertRaises(P.ProtocolError):
                P.parse_frame(junk)


class DecodeTest(unittest.TestCase):
    def test_analog(self):
        a = P.decode_analog(info_of(P.CMD_ANALOG))
        self.assertEqual(a["cells_mv"], [3313] * 8 + [3312] + [3313] * 6)
        self.assertEqual((a["cell_min_mv"], a["cell_max_mv"], a["cell_spread_mv"]), (3312, 3313, 1))
        self.assertEqual((a["cell_min_index"], a["cell_max_index"]), (9, 1))
        self.assertEqual(a["temperatures_c"], {"bms": 18.8, "cells_1_4": 15.9, "cells_5_8": 15.6,
                                               "cells_9_12": 15.4, "cells_13_15": 17.1})
        self.assertAlmostEqual(a["current_a"], 0.6)
        self.assertAlmostEqual(a["voltage_v"], 49.694)
        self.assertAlmostEqual(a["remaining_ah"], 21.127)
        self.assertAlmostEqual(a["full_ah"], 74.0)
        self.assertEqual(a["soc_pct"], 28.6)
        self.assertEqual(a["cycles"], 799)

    def test_analog_negative_current_and_2byte_capacity(self):
        # synthetic: 2 cells, 1 temp, -7.6 A, 2-byte capacities (user-defined byte 02)
        info = "0002" "02" "0D040D05" "01" "0B71" "FFB4" "C343" "2710" "02" "C350" "0010"
        a = P.decode_analog(info)
        self.assertAlmostEqual(a["current_a"], -7.6)
        self.assertEqual((a["remaining_ah"], a["full_ah"], a["soc_pct"]), (10.0, 50.0, 20.0))
        self.assertEqual(a["temperatures_c"], {"t1": 19.8})

    def test_alarm_all_normal(self):
        al = P.decode_alarm(info_of(P.CMD_ALARM))
        self.assertEqual(al["active"], [])
        self.assertEqual(len(al["cells"]), 15)
        self.assertEqual(al["status_bytes"], [0x00, 0x0E, 0x80, 0x00, 0x00, 0x00])
        st = al["status"]
        self.assertEqual(st["protections"], [])
        self.assertTrue(st["charge_mosfet"] and st["discharge_mosfet"] and st["using_battery_power"])
        self.assertFalse(st["precharge_mosfet"])
        self.assertTrue(st["charge_current"])
        self.assertFalse(st["discharge_current"] or st["fully_charged"] or st["heater"] or st["buzzer"])
        self.assertEqual(st["cell_errors"], [])
        self.assertEqual(st["extra"], [0x00])

    def test_status_bits(self):
        st = P.decode_status([0x81, 0x05, 0x69, 0x02, 0x40])
        self.assertEqual(st["protections"], ["module over voltage", "module under voltage"])
        self.assertTrue(st["precharge_mosfet"] and st["discharge_mosfet"])
        self.assertFalse(st["charge_mosfet"] or st["using_battery_power"])
        self.assertTrue(st["buzzer"] and st["fully_charged"] and st["heater"] and st["discharge_current"])
        self.assertFalse(st["charge_current"])
        self.assertEqual(st["cell_errors"], [2, 15])
        self.assertEqual(st["extra"], [])

    def test_status_short(self):
        st = P.decode_status([])
        self.assertEqual(st["protections"], [])
        self.assertFalse(st["charge_mosfet"])

    def test_alarm_protection_listed(self):
        info = "0002" "01" "00" "01" "00" "000000" "10" "00" "00" "01" "00"
        al = P.decode_alarm(info)
        self.assertEqual(al["active"], ["protection: discharge over current", "cell 1 error"])

    def test_alarm_active(self):
        info = "0002" "03" "000200" "01" "01" "00" "02" "00" "00"
        al = P.decode_alarm(info)
        self.assertEqual(al["active"], ["cell 2 above upper limit", "temperature t1 below lower limit",
                                        "pack voltage above upper limit"])

    def test_management(self):
        m = P.decode_management(info_of(P.CMD_MANAGEMENT))
        self.assertEqual((m["charge_voltage_limit_v"], m["discharge_voltage_limit_v"]), (53.25, 45.0))
        self.assertEqual((m["charge_current_limit_a"], m["discharge_current_limit_a"]), (37.0, 37.0))
        self.assertTrue(m["charge_enabled"] and m["discharge_enabled"])
        self.assertFalse(m["charge_immediately"] or m["full_charge_request"])

    def test_manufacturer(self):
        self.assertEqual(P.decode_manufacturer(info_of(P.CMD_MANUFACTURER)),
                         {"model": "US3000C", "software_version": "2.2", "manufacturer": "Pylon"})

    def test_serial(self):
        self.assertEqual(P.decode_serial(info_of(P.CMD_SERIAL))["serial"], "TESTSERIAL000001")

    def test_short_info(self):
        with self.assertRaises(P.ProtocolError):
            P.decode_management("02D002")


if __name__ == "__main__":
    unittest.main()
