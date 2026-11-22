import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from sexp import Sym, dump, find, find_all, parse


class SexpTest(unittest.TestCase):
    def test_round_trip_stock_library(self):
        text = open("/usr/share/kicad/symbols/Device.kicad_sym", encoding="utf-8").read()
        node = parse(text)
        self.assertEqual(node[0], Sym("kicad_symbol_lib"))
        self.assertEqual(parse(dump(node)), node)

    def test_strings_keep_quotes_and_escapes(self):
        node = parse(r'(a "x y" "q\"z" 1.5 -2 name)')
        self.assertEqual(node, [Sym("a"), "x y", 'q"z', Sym("1.5"), Sym("-2"), Sym("name")])
        self.assertEqual(dump(node), '(a "x y" "q\\"z" 1.5 -2 name)')

    def test_find(self):
        node = parse("(s (pin a) (pin b) (other))")
        self.assertEqual(find(node, "other"), [Sym("other")])
        self.assertEqual(len(find_all(node, "pin")), 2)
        self.assertIsNone(find(node, "none"))


if __name__ == "__main__":
    unittest.main()
