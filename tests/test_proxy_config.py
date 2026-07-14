import os
import urllib.parse
import unittest

from proxy_tester.proxy_config import (
    encode_base64,
    find_proxy_config_line,
    first_query_value,
    make_proxy_url,
    parse_proxy_config,
)
from tests.helpers import DEFAULT_VLESS_URL, sample_profile, temp_text_file


class VlessTests(unittest.TestCase):
    def test_find_proxy_config_line_ignores_other_lines(self):
        with temp_text_file(f"hello\n\n{DEFAULT_VLESS_URL}\n") as path:
            self.assertEqual(find_proxy_config_line(path), DEFAULT_VLESS_URL)

    def test_find_proxy_config_line_raises_when_missing(self):
        with temp_text_file("not a config\n") as path:
            with self.assertRaises(ValueError):
                find_proxy_config_line(path)

    def test_first_query_value_returns_value_or_default(self):
        query = {"a": ["one"], "empty": []}

        self.assertEqual(first_query_value(query, "a", "fallback"), "one")
        self.assertEqual(first_query_value(query, "missing", "fallback"), "fallback")
        self.assertEqual(first_query_value(query, "empty", "fallback"), "fallback")

    def test_parse_proxy_config_reads_profile(self):
        with temp_text_file(DEFAULT_VLESS_URL, suffix="-friendly-name.txt") as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.name, os.path.basename(path))
        self.assertEqual(profile.protocol, "vless")
        self.assertEqual(profile.uuid, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(profile.port, 443)
        self.assertEqual(profile.security, "tls")
        self.assertEqual(profile.sni, "example.com")
        self.assertEqual(profile.fingerprint, "chrome")
        self.assertEqual(profile.alpn, "h2,http/1.1")
        self.assertFalse(profile.allow_insecure)
        self.assertEqual(profile.network, "ws")
        self.assertEqual(profile.ws_host, "example.com")
        self.assertEqual(profile.ws_path, "/ws")
        self.assertEqual(profile.encryption, "none")

    def test_parse_vmess_config_reads_profile(self):
        payload = {
            "v": "2",
            "ps": "vmess-name",
            "add": "example.com",
            "port": "443",
            "id": "11111111-1111-1111-1111-111111111111",
            "aid": "0",
            "scy": "auto",
            "net": "ws",
            "type": "none",
            "host": "example.com",
            "path": "/ws",
            "tls": "tls",
            "sni": "example.com",
            "fp": "chrome",
            "alpn": "http/1.1",
        }
        url = f"vmess://{encode_base64(__import__('json').dumps(payload))}"

        with temp_text_file(url) as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.protocol, "vmess")
        self.assertEqual(profile.uuid, payload["id"])
        self.assertEqual(profile.port, 443)
        self.assertEqual(profile.ws_path, "/ws")
        self.assertEqual(profile.vmess_security, "auto")

    def test_parse_trojan_config_reads_profile(self):
        url = "trojan://secret@example.com:443?security=tls&type=ws&host=example.com&path=%2Ftrojan&sni=example.com"

        with temp_text_file(url) as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.protocol, "trojan")
        self.assertEqual(profile.password, "secret")
        self.assertEqual(profile.port, 443)
        self.assertEqual(profile.ws_path, "/trojan")

    def test_parse_proxy_config_uses_defaults(self):
        url = "vless://uuid@example.com:443"

        with temp_text_file(url) as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.security, "tls")
        self.assertEqual(profile.sni, "example.com")
        self.assertEqual(profile.fingerprint, "chrome")
        self.assertEqual(profile.alpn, "http/1.1")
        self.assertEqual(profile.ws_host, "example.com")
        self.assertEqual(profile.ws_path, "/")
        self.assertEqual(profile.encryption, "none")

    def test_parse_proxy_config_rejects_unsupported_network(self):
        url = "vless://uuid@example.com:443?type=tcp"

        with temp_text_file(url) as path:
            with self.assertRaises(ValueError):
                parse_proxy_config(path)

    def test_make_proxy_url_uses_profile_and_encodes_values(self):
        url = make_proxy_url("104.16.1.1", "name with spaces", sample_profile())
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "vless")
        self.assertEqual(parsed.username, sample_profile().uuid)
        self.assertEqual(parsed.hostname, "104.16.1.1")
        self.assertEqual(parsed.port, 443)
        self.assertEqual(query["sni"][0], "example.com")
        self.assertEqual(query["path"][0], "/ws")
        self.assertEqual(urllib.parse.unquote(parsed.fragment), "name with spaces")

    def test_make_vmess_url_uses_profile_and_ip(self):
        payload = {
            "v": "2",
            "ps": "vmess-name",
            "add": "example.com",
            "port": "443",
            "id": "11111111-1111-1111-1111-111111111111",
            "net": "ws",
            "host": "example.com",
            "path": "/ws",
            "tls": "tls",
        }
        with temp_text_file(f"vmess://{encode_base64(__import__('json').dumps(payload))}") as path:
            profile = parse_proxy_config(path)

        url = make_proxy_url("104.16.1.1", "new name", profile)
        parsed_payload = __import__("json").loads(__import__("base64").urlsafe_b64decode(url[len("vmess://"):] + "=="))

        self.assertEqual(parsed_payload["add"], "104.16.1.1")
        self.assertEqual(parsed_payload["ps"], "new name")

    def test_make_trojan_url_uses_profile_and_ip(self):
        with temp_text_file("trojan://secret@example.com:443?security=tls&type=ws&host=example.com&path=%2Fws") as path:
            profile = parse_proxy_config(path)

        url = make_proxy_url("104.16.1.1", "trojan name", profile)
        parsed = urllib.parse.urlparse(url)

        self.assertEqual(parsed.scheme, "trojan")
        self.assertEqual(parsed.username, "secret")
        self.assertEqual(parsed.hostname, "104.16.1.1")


if __name__ == "__main__":
    unittest.main()
