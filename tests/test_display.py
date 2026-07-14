import io
import unittest
from contextlib import redirect_stdout

from proxy_tester.display import print_passed_table, progress_text, speed_summary


class DisplayTests(unittest.TestCase):
    def test_progress_text_formats_percentage(self):
        self.assertEqual(progress_text(5, 20), "5/20 (25.0%)")
        self.assertEqual(progress_text(0, 0), "0/0 (0.0%)")

    def test_speed_summary_formats_present_values(self):
        self.assertEqual(speed_summary({}), "")
        self.assertEqual(speed_summary({"download_mbps": 10}), "down=10 Mbps")
        self.assertEqual(speed_summary({"upload_mbps": 5}), "up=5 Mbps")
        self.assertEqual(speed_summary({"download_mbps": 10, "upload_mbps": 5}), "down=10 Mbps | up=5 Mbps")

    def test_print_passed_table_handles_empty_list(self):
        out = io.StringIO()

        with redirect_stdout(out):
            print_passed_table([])

        self.assertIn("PASSED SO FAR: none", out.getvalue())

    def test_print_passed_table_sorts_by_latency(self):
        out = io.StringIO()
        rows = [
            {"ip": "104.16.1.1", "ms": 200, "colo": "AMS", "warp": "off"},
            {"ip": "104.16.1.2", "ms": 50, "colo": "FRA", "warp": "off"},
        ]

        with redirect_stdout(out):
            print_passed_table(rows)

        text = out.getvalue()
        self.assertLess(text.index("104.16.1.2"), text.index("104.16.1.1"))


if __name__ == "__main__":
    unittest.main()

