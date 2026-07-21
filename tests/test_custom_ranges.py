import ipaddress
import unittest

from proxy_tester.custom_ranges import custom_ranges_text, parse_custom_ranges


class CustomRangeTests(unittest.TestCase):
    def test_parser_normalizes_deduplicates_and_accepts_single_ips(self):
        networks = parse_custom_ranges(
            """# office ranges
198.51.100.9
203.0.113.7/24
203.0.113.0/24
"""
        )

        self.assertEqual(
            networks,
            [ipaddress.ip_network("198.51.100.9/32"), ipaddress.ip_network("203.0.113.0/24")],
        )
        self.assertEqual(custom_ranges_text(networks), "198.51.100.9/32\n203.0.113.0/24")

    def test_parser_rejects_invalid_and_ipv6_ranges_with_line_number(self):
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_custom_ranges("10.0.0.0/24\ninvalid")
        with self.assertRaisesRegex(ValueError, "Only IPv4"):
            parse_custom_ranges("2001:db8::/32")


if __name__ == "__main__":
    unittest.main()
