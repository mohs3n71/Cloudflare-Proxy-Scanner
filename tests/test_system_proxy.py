import unittest
from unittest.mock import patch

from proxy_tester import system_proxy


class SystemProxyTests(unittest.TestCase):
    def test_set_socks_proxy_is_safe_noop_outside_windows(self):
        with patch.object(system_proxy.os, "name", "posix"):
            self.assertIn("only supported on Windows", system_proxy.set_socks_proxy(1080))

    def test_clear_proxy_is_safe_noop_outside_windows(self):
        with patch.object(system_proxy.os, "name", "posix"):
            self.assertIn("only supported on Windows", system_proxy.clear_proxy())


if __name__ == "__main__":
    unittest.main()
