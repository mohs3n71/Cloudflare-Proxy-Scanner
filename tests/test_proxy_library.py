import json
import os
import tempfile
import unittest

from proxy_tester.proxy_config import encode_base64
from proxy_tester.proxy_library import (
    entry_id_for,
    extract_proxy_urls,
    import_library_text,
    load_proxy_library,
    make_library_entry,
    save_proxy_library,
    update_library_result,
)


VLESS_URL = "vless://uuid@example.com:443?security=tls&type=ws&host=example.com&path=%2Fws#VLESS"
TROJAN_URL = "trojan://secret@trojan.example:443?security=tls&type=grpc&serviceName=service#Trojan"
SS_URL = f"ss://{encode_base64('aes-256-gcm:secret')}@ss.example:8388#Shadowsocks"


class ProxyLibraryTests(unittest.TestCase):
    def test_extract_proxy_urls_finds_supported_links_and_deduplicates(self):
        text = f"first: {VLESS_URL}\n{TROJAN_URL}\n{VLESS_URL}\n{SS_URL}"

        self.assertEqual(extract_proxy_urls(text), [VLESS_URL, TROJAN_URL, SS_URL])

    def test_make_library_entry_uses_parsed_metadata_and_stable_id(self):
        entry = make_library_entry(TROJAN_URL)

        self.assertEqual(entry["id"], entry_id_for(TROJAN_URL))
        self.assertEqual(entry["name"], "Trojan")
        self.assertEqual(entry["protocol"], "trojan")
        self.assertEqual(entry["address"], "trojan.example")
        self.assertEqual(entry["port"], 443)
        self.assertEqual(entry["status"], "Not tested")

    def test_import_library_text_adds_valid_unique_entries_and_reports_invalid(self):
        existing = [make_library_entry(VLESS_URL)]
        invalid_ss = "ss://not-valid"

        merged, added, errors = import_library_text(
            existing,
            f"{VLESS_URL}\n{TROJAN_URL}\n{invalid_ss}",
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual([entry["config"] for entry in added], [TROJAN_URL])
        self.assertEqual(len(errors), 1)

    def test_library_save_and_load_round_trip(self):
        entries = [make_library_entry(VLESS_URL), make_library_entry(SS_URL)]
        entries[0]["download_mbps"] = 12.5
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "library.json")

            save_proxy_library(entries, path)
            loaded = load_proxy_library(path)
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["download_mbps"], 12.5)
        self.assertEqual(loaded[1]["protocol"], "shadowsocks")

    def test_load_missing_library_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_proxy_library(os.path.join(directory, "missing.json")), [])

    def test_update_library_result_only_changes_requested_speed_columns(self):
        entry = make_library_entry(VLESS_URL)
        entry.update(download_mbps=50, upload_mbps=5)

        upload = update_library_result(
            entry,
            {"ok": True, "ms": 90, "upload_mbps": 8},
            "upload",
        )
        failed_download = update_library_result(
            upload,
            {"ok": False, "ms": -1, "error": "timeout"},
            "download",
        )

        self.assertEqual(upload["download_mbps"], 50)
        self.assertEqual(upload["upload_mbps"], 8)
        self.assertEqual(failed_download["download_mbps"], -1)
        self.assertEqual(failed_download["upload_mbps"], 8)
        self.assertEqual(failed_download["status"], "Failed")


if __name__ == "__main__":
    unittest.main()
