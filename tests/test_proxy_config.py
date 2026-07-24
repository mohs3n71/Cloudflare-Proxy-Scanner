import os
import json
import urllib.parse
import unittest

from proxy_tester.proxy_config import (
    encode_base64,
    find_proxy_config_line,
    first_query_value,
    make_proxy_url,
    parse_proxy_config,
    parse_proxy_url,
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

    def test_parse_vmess_preserves_disabled_transport_security(self):
        payload = {
            "add": "direct.example",
            "port": "80",
            "id": "11111111-1111-1111-1111-111111111111",
            "net": "tcp",
            "tls": "",
        }

        profile = parse_proxy_url(f"vmess://{encode_base64(json.dumps(payload))}")

        self.assertEqual(profile.address, "direct.example")
        self.assertEqual(profile.network, "tcp")
        self.assertEqual(profile.security, "none")

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
        url = "vless://uuid@example.com:443?type=udp"

        with temp_text_file(url) as path:
            with self.assertRaises(ValueError):
                parse_proxy_config(path)

    def test_parse_vless_reality_tcp_retains_original_endpoint(self):
        profile = parse_proxy_url(
            "vless://uuid@direct.example:443"
            "?security=reality&type=tcp&sni=www.example.com&fp=chrome"
            "&pbk=public-key&sid=abcd&spx=%2F&flow=xtls-rprx-vision#Direct"
        )

        self.assertEqual(profile.address, "direct.example")
        self.assertEqual(profile.name, "Direct")
        self.assertEqual(profile.network, "tcp")
        self.assertEqual(profile.security, "reality")
        self.assertEqual(profile.flow, "xtls-rprx-vision")
        self.assertEqual(profile.reality_public_key, "public-key")
        self.assertEqual(profile.reality_short_id, "abcd")

    def test_parse_trojan_grpc_reads_service_and_authority(self):
        profile = parse_proxy_url(
            "trojan://secret@example.com:443?security=tls&type=grpc"
            "&serviceName=my-service&authority=cdn.example.com#Trojan-gRPC"
        )

        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.network, "grpc")
        self.assertEqual(profile.grpc_service_name, "my-service")
        self.assertEqual(profile.grpc_authority, "cdn.example.com")

    def test_parse_shadowsocks_supports_sip002_and_legacy_urls(self):
        credentials = encode_base64("aes-256-gcm:secret")
        modern = parse_proxy_url(f"ss://{credentials}@server.example:8388#Modern")
        legacy = parse_proxy_url(
            f"ss://{encode_base64('chacha20-ietf-poly1305:password@legacy.example:443')}#Legacy"
        )

        self.assertEqual(modern.protocol, "shadowsocks")
        self.assertEqual(modern.address, "server.example")
        self.assertEqual(modern.port, 8388)
        self.assertEqual(modern.shadowsocks_method, "aes-256-gcm")
        self.assertEqual(modern.password, "secret")
        self.assertEqual(legacy.address, "legacy.example")
        self.assertEqual(legacy.shadowsocks_method, "chacha20-ietf-poly1305")

    def test_parse_shadowsocks_rejects_plugin_urls(self):
        credentials = encode_base64("aes-256-gcm:secret")

        with self.assertRaisesRegex(ValueError, "plugins are not supported"):
            parse_proxy_url(f"ss://{credentials}@example.com:8388?plugin=v2ray-plugin")

    def test_parse_vless_xhttp_config_reads_transport_settings(self):
        extra = {"xPaddingBytes": "100-1000", "xmux": {"maxConcurrency": 1}}
        query = urllib.parse.urlencode(
            {
                "security": "tls",
                "type": "xhttp",
                "host": "cdn.example.com",
                "path": "/xhttp",
                "mode": "packet-up",
                "extra": json.dumps(extra),
                "sni": "example.com",
                "alpn": "h2",
            }
        )
        with temp_text_file(f"vless://uuid@example.com:443?{query}") as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.network, "xhttp")
        self.assertEqual(profile.ws_host, "cdn.example.com")
        self.assertEqual(profile.ws_path, "/xhttp")
        self.assertEqual(profile.xhttp_mode, "packet-up")
        self.assertEqual(profile.xhttp_extra, extra)

    def test_parse_vless_normalizes_splithttp_alias(self):
        with temp_text_file("vless://uuid@example.com:443?type=splithttp&path=%2Fold") as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.network, "xhttp")
        self.assertEqual(profile.ws_path, "/old")

    def test_parse_vmess_xhttp_accepts_extra_object(self):
        payload = {
            "add": "example.com",
            "port": "443",
            "id": "11111111-1111-1111-1111-111111111111",
            "net": "xhttp",
            "host": "cdn.example.com",
            "path": "/xhttp",
            "mode": "stream-up",
            "extra": {"noGRPCHeader": True},
        }
        with temp_text_file(f"vmess://{encode_base64(json.dumps(payload))}") as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.network, "xhttp")
        self.assertEqual(profile.xhttp_mode, "stream-up")
        self.assertEqual(profile.xhttp_extra, {"noGRPCHeader": True})

    def test_parse_trojan_xhttp_config_reads_transport_settings(self):
        url = "trojan://secret@example.com:443?security=tls&type=xhttp&path=%2Fx&mode=stream-one&extra=%7B%22xPaddingBytes%22%3A%2210-20%22%7D"
        with temp_text_file(url) as path:
            profile = parse_proxy_config(path)

        self.assertEqual(profile.network, "xhttp")
        self.assertEqual(profile.xhttp_mode, "stream-one")
        self.assertEqual(profile.xhttp_extra, {"xPaddingBytes": "10-20"})

    def test_parse_xhttp_rejects_invalid_extra_json(self):
        with temp_text_file("vless://uuid@example.com:443?type=xhttp&extra=not-json") as path:
            with self.assertRaisesRegex(ValueError, "Invalid XHTTP extra JSON"):
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

    def test_make_proxy_url_preserves_xhttp_settings(self):
        source = "vless://uuid@example.com:443?type=xhttp&host=cdn.example.com&path=%2Fx&mode=packet-up&extra=%7B%22xPaddingBytes%22%3A%2210-20%22%7D"
        with temp_text_file(source) as path:
            profile = parse_proxy_config(path)

        generated = make_proxy_url("104.16.1.1", "xhttp result", profile)
        parsed = urllib.parse.urlparse(generated)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(query["type"], ["xhttp"])
        self.assertEqual(query["mode"], ["packet-up"])
        self.assertEqual(json.loads(query["extra"][0]), {"xPaddingBytes": "10-20"})

    def test_xhttp_generated_urls_round_trip_for_all_protocols(self):
        extra = {"xmux": {"maxConcurrency": 1}}
        encoded_extra = urllib.parse.quote(json.dumps(extra), safe="")
        vmess_payload = {
            "add": "example.com",
            "port": "443",
            "id": "11111111-1111-1111-1111-111111111111",
            "net": "xhttp",
            "path": "/x",
            "mode": "stream-up",
            "extra": json.dumps(extra),
        }
        sources = (
            f"vless://uuid@example.com:443?type=xhttp&path=%2Fx&mode=stream-up&extra={encoded_extra}",
            f"vmess://{encode_base64(json.dumps(vmess_payload))}",
            f"trojan://secret@example.com:443?type=xhttp&path=%2Fx&mode=stream-up&extra={encoded_extra}",
        )

        for source in sources:
            with self.subTest(scheme=source.split(":", 1)[0]):
                with temp_text_file(source) as source_path:
                    generated = make_proxy_url("104.16.1.1", "result", parse_proxy_config(source_path))
                with temp_text_file(generated) as generated_path:
                    reparsed = parse_proxy_config(generated_path)

                self.assertEqual(reparsed.network, "xhttp")
                self.assertEqual(reparsed.xhttp_mode, "stream-up")
                self.assertEqual(reparsed.xhttp_extra, extra)

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

    def test_make_shadowsocks_url_round_trips(self):
        credentials = encode_base64("aes-128-gcm:secret")
        profile = parse_proxy_url(f"ss://{credentials}@example.com:8388#Original")

        generated = make_proxy_url("1.1.1.1", "New name", profile)
        reparsed = parse_proxy_url(generated)

        self.assertEqual(reparsed.address, "1.1.1.1")
        self.assertEqual(reparsed.name, "New name")
        self.assertEqual(reparsed.shadowsocks_method, "aes-128-gcm")
        self.assertEqual(reparsed.password, "secret")


if __name__ == "__main__":
    unittest.main()
