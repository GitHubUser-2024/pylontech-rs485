import os
import tempfile
import unittest

from pylontech_rs485 import history


class HistoryTest(unittest.TestCase):
    def test_window_and_stats(self):
        s = []
        s = history.add(s, 1000, [3300, 3310, 3305], window_s=100)
        s = history.add(s, 1050, [3320, 3330, 3310], window_s=100)
        s = history.add(s, 1110, [3340, 3346, 3340], window_s=100)  # drops ts 1000
        self.assertEqual([x[0] for x in s], [1050, 1110])
        st = history.stats(s)
        self.assertEqual(st["samples"], 2)
        self.assertEqual(st["spread_now_mv"], 6)
        self.assertEqual((st["spread_min_mv"], st["spread_max_mv"], st["spread_avg_mv"]), (6, 20, 13.0))
        c2 = st["cells"][1]
        self.assertEqual((c2["now_mv"], c2["min_mv"], c2["max_mv"], c2["avg_mv"]), (3346, 3330, 3346, 3338.0))
        self.assertEqual(c2["dev_now_mv"], 4.0)
        self.assertEqual(c2["dev_avg_mv"], 7.0)
        self.assertEqual((c2["dev_max_mv"], c2["dev_max_ts"]), (10.0, 1050))  # +10 beats +4
        c3 = st["cells"][2]
        self.assertEqual((c3["dev_max_mv"], c3["dev_max_ts"]), (-10.0, 1050))  # sign kept

    def test_empty(self):
        self.assertIsNone(history.stats([]))

    def test_cell_count_change_uses_current_layout(self):
        s = [[1, [1, 2]], [2, [3300, 3301, 3302]]]
        self.assertEqual(history.stats(s)["samples"], 1)

    def test_save_load_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "h.json")
            self.assertEqual(history.load(p), [])
            history.save(p, [[1, [3300]]])
            self.assertEqual(history.load(p), [[1, [3300]]])
            with open(p, "w") as f:
                f.write("{broken")
            self.assertEqual(history.load(p), [])
            self.assertEqual([n for n in os.listdir(os.path.dirname(p)) if n.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
