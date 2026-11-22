import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0]))
from netlist import NETS, PARTS, PERFBOARD


class NetlistTest(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(PARTS), 38)
        self.assertEqual(set(NETS), {"+12V_IN", "+12V", "+12V_SW", "3V3", "GND", "RST", "EN", "IO0", "IO15", "IO16", "IO12", "IO13",
                                     "DQ", "TACH1", "TACH2", "TACH3", "TX", "RX", "PWM", "GATE", "Q1_B", "Q2_B", "Q4_B", "FLOW"})
        for net, pins in NETS.items():
            self.assertGreaterEqual(len(pins), 2, net)

    def test_fuse_and_diode(self):
        self.assertEqual(PARTS["J2"].pins, {"1": "+12V_IN", "2": "GND"})
        self.assertEqual(PARTS["F1"].pins, {"1": "+12V_IN", "2": "+12V"})
        self.assertEqual(PARTS["D2"].pins, {"1": "+12V", "2": "GND"})
        self.assertEqual(NETS["+12V_IN"], {("J2", "1"), ("F1", "1")})
        self.assertEqual(PARTS["F1"].value, "MF-R250")

    def test_module(self):
        p = PARTS["U1"].pins
        self.assertEqual({k: p[k] for k in "1 3 4 5 6 7 8 15 16 17 18 19 20 21 22".split()},
                         {"1": "RST", "3": "EN", "4": "IO16", "5": "TACH3", "6": "IO12", "7": "IO13", "8": "3V3", "15": "GND",
                          "16": "IO15", "17": "DQ", "18": "IO0", "19": "TACH2", "20": "TACH1", "21": "RX", "22": "TX"})
        self.assertTrue(all(p[k] is None for k in "2 9 10 11 12 13 14".split()))

    def test_stages(self):
        self.assertEqual(PARTS["Q1"].pins, {"1": "GND", "2": "Q1_B", "3": "PWM"})
        self.assertEqual(PARTS["Q3"].pins, {"1": "GATE", "2": "+12V_SW", "3": "+12V"})
        self.assertEqual(PARTS["Q4"].pins, {"1": "GND", "2": "Q4_B", "3": "IO13"})
        self.assertEqual(PARTS["D1"].pins, {"1": "+12V_SW", "2": "GND"})
        self.assertEqual(PARTS["J3"].pins, {"1": "GND", "2": "+12V_SW", "3": "TACH1", "4": "PWM"})
        self.assertEqual(PARTS["J7"].pins, {"1": "+12V", "2": "GND", "3": "FLOW"})
        self.assertEqual(PARTS["J6"].pins, {"1": "3V3", "2": "DQ", "3": "GND"})
        self.assertEqual(PARTS["U2"].pins, {"1": "+12V", "2": "GND", "3": "3V3", "4": "GND"})
        self.assertEqual(PARTS["SW1"].pins, {"1": "RST", "2": "GND"})
        self.assertEqual(PARTS["H1"].pins, {"1": "GND"})
        self.assertEqual(PARTS["R5"].value, "1k")
        self.assertEqual(PARTS["R10"].value, "4.7k")

    def test_perfboard_plan_is_clean(self):
        self.assertEqual(PERFBOARD.check()[0], [])


if __name__ == "__main__":
    unittest.main()
