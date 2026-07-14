import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from proxy_tester import system_proxy


class SystemProxyTests(unittest.TestCase):
    def test_set_socks_proxy_is_safe_noop_outside_windows(self):
        with patch.object(system_proxy.os, "name", "posix"):
            self.assertIn("only supported on Windows", system_proxy.set_socks_proxy(1080))

    def test_clear_proxy_is_safe_noop_outside_windows(self):
        with patch.object(system_proxy.os, "name", "posix"):
            self.assertIn("only supported on Windows", system_proxy.clear_proxy())

    def test_set_socks_proxy_updates_windows_registry_and_refreshes(self):
        key = MagicMock()
        open_key = MagicMock()
        open_key.return_value.__enter__.return_value = key
        winreg = SimpleNamespace(
            HKEY_CURRENT_USER=object(),
            KEY_SET_VALUE=1,
            REG_DWORD=2,
            REG_SZ=3,
            OpenKey=open_key,
            SetValueEx=MagicMock(),
        )
        with patch.object(system_proxy.os, "name", "nt"):
            with patch.dict("sys.modules", {"winreg": winreg}):
                with patch.object(system_proxy, "refresh_windows_proxy") as refresh:
                    message = system_proxy.set_socks_proxy(1080, "0.0.0.0")

        self.assertEqual(message, "System proxy set to socks=0.0.0.0:1080")
        winreg.SetValueEx.assert_has_calls(
            [
                call(key, "ProxyEnable", 0, winreg.REG_DWORD, 1),
                call(key, "ProxyServer", 0, winreg.REG_SZ, "socks=0.0.0.0:1080"),
            ]
        )
        refresh.assert_called_once_with()

    def test_clear_proxy_disables_windows_registry_proxy(self):
        key = MagicMock()
        open_key = MagicMock()
        open_key.return_value.__enter__.return_value = key
        winreg = SimpleNamespace(
            HKEY_CURRENT_USER=object(),
            KEY_SET_VALUE=1,
            REG_DWORD=2,
            OpenKey=open_key,
            SetValueEx=MagicMock(),
        )
        with patch.object(system_proxy.os, "name", "nt"):
            with patch.dict("sys.modules", {"winreg": winreg}):
                with patch.object(system_proxy, "refresh_windows_proxy") as refresh:
                    message = system_proxy.clear_proxy()

        self.assertEqual(message, "System proxy cleared.")
        winreg.SetValueEx.assert_called_once_with(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        refresh.assert_called_once_with()

    def test_refresh_windows_proxy_broadcasts_both_notifications(self):
        internet_set_option = MagicMock()
        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(Wininet=SimpleNamespace(InternetSetOptionW=internet_set_option))
        )
        with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
            system_proxy.refresh_windows_proxy()

        internet_set_option.assert_has_calls([call(0, 39, 0, 0), call(0, 37, 0, 0)])


if __name__ == "__main__":
    unittest.main()
