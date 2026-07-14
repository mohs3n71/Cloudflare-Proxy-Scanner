import unittest
from unittest.mock import patch

from proxy_tester import colors


class ColorTests(unittest.TestCase):
    def test_paint_adds_ansi_when_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(colors.paint("ok", colors.GREEN), "\033[32mok\033[0m")

    def test_paint_respects_no_color(self):
        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=True):
            self.assertEqual(colors.paint("ok", colors.GREEN), "ok")

    def test_helper_functions_return_text_when_color_disabled(self):
        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=True):
            self.assertEqual(colors.success("done"), "done")
            self.assertEqual(colors.error("bad"), "bad")


if __name__ == "__main__":
    unittest.main()

