import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from proxy_tester import storage
from tests.helpers import sample_profile


class StorageTests(unittest.TestCase):
    def test_config_files_lists_files_sorted(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "CONFIG_DIR", td):
            open(os.path.join(td, "b.config"), "w", encoding="utf-8").close()
            open(os.path.join(td, "a.config"), "w", encoding="utf-8").close()
            open(os.path.join(td, "ignore.txt"), "w", encoding="utf-8").close()
            os.mkdir(os.path.join(td, "folder"))

            names = [os.path.basename(path) for path in storage.config_files()]

        self.assertEqual(names, ["a.config", "b.config"])

    def test_output_csv_files_lists_csv_by_newest_first(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            old_path = os.path.join(td, "old.csv")
            new_path = os.path.join(td, "new.csv")
            txt_path = os.path.join(td, "ignore.txt")
            for path in (old_path, new_path, txt_path):
                open(path, "w", encoding="utf-8").close()
            os.utime(old_path, (100, 100))
            os.utime(new_path, (200, 200))

            names = [os.path.basename(path) for path in storage.output_csv_files()]

        self.assertEqual(names, ["new.csv", "old.csv"])

    def test_output_csv_files_excludes_fragment_scan_results(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            scan_path = os.path.join(td, "working-cloudflare-proxy-ips.csv")
            fragment_path = os.path.join(td, "fragment-scan-demo-104-16-1-1-download.csv")
            for path in (scan_path, fragment_path):
                open(path, "w", encoding="utf-8").close()

            names = [os.path.basename(path) for path in storage.output_csv_files()]

        self.assertEqual(names, ["working-cloudflare-proxy-ips.csv"])

    def test_safe_filename_part_replaces_unsafe_characters(self):
        self.assertEqual(storage.safe_filename_part("a/b:c name"), "a-b-c-name")
        self.assertEqual(storage.safe_filename_part("///"), "cloudflare")

    def test_read_working_ips_skips_empty_ip_rows(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ip", "latency_ms"])
            writer.writerow(["104.16.1.1", "100"])
            writer.writerow(["", "200"])
            path = f.name
        try:
            rows = storage.read_working_ips(path)
        finally:
            os.remove(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ip"], "104.16.1.1")

    def test_save_scan_results_writes_latest_and_speed_columns(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            out_path, latest_path = storage.save_scan_results(
                [
                    {
                        "ip": "104.16.1.1",
                        "ms": 100,
                        "colo": "AMS",
                        "warp": "off",
                        "download_mbps": 12.5,
                        "upload_mbps": 6.25,
                    }
                ],
                prefix="speed-test",
            )

            self.assertTrue(os.path.exists(out_path))
            self.assertTrue(os.path.exists(latest_path))
            with open(out_path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(rows[0]["ip"], "104.16.1.1")
        self.assertEqual(rows[0]["latency_ms"], "100")
        self.assertEqual(rows[0]["download_mbps"], "12.5")
        self.assertEqual(rows[0]["upload_mbps"], "6.25")

    def test_save_scan_results_omits_speed_columns_when_absent(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            out_path, _ = storage.save_scan_results([{"ip": "104.16.1.1", "ms": 100}])
            with open(out_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                headers = next(reader)

        self.assertEqual(headers, ["ip", "latency_ms", "colo", "warp"])

    def test_save_scan_results_normalizes_float_failure_values(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            out_path, _ = storage.save_scan_results(
                [{"ip": "104.16.1.1", "ms": -1.0, "download_mbps": "-1.0", "upload_mbps": -1.00}]
            )
            with open(out_path, "r", encoding="utf-8", newline="") as output_file:
                row = next(csv.DictReader(output_file))

        self.assertEqual(row["latency_ms"], "-1")
        self.assertEqual(row["download_mbps"], "-1")
        self.assertEqual(row["upload_mbps"], "-1")

    def test_save_proxy_configs_writes_one_link_per_row(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            csv_path = os.path.join(td, "working.csv")
            out_path = storage.save_proxy_configs(
                csv_path,
                [
                    {"ip": "104.16.1.1", "latency_ms": "100", "colo": "AMS"},
                    {"ip": "104.16.1.2", "latency_ms": "200", "colo": ""},
                ],
                sample_profile(),
            )
            with open(out_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.startswith("vless://") for line in lines))
        self.assertIn("@104.16.1.1:443?", lines[0])

    def test_log_file_helpers_create_and_append_log_lines(self):
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "LOG_DIR", td):
            path = storage.create_log_file("speed selected/table")
            storage.append_log_line(path, "hello upload diagnostics")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        self.assertEqual(os.path.dirname(path), td)
        self.assertTrue(os.path.basename(path).startswith("speed-selected-table-"))
        self.assertIn("hello upload diagnostics", content)

    def test_best_fragment_helpers_save_and_load_by_ip_config_and_mode(self):
        fragment = {"packets": "1-3", "interval": "1-1", "length": "1-7"}
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            storage.save_best_fragment("104.16.1.1", "demo.config", "download", fragment, 12.5, 100)

            saved = storage.get_best_fragment("104.16.1.1", "demo.config", "download")

        self.assertEqual(saved["fragment"], fragment)
        self.assertEqual(saved["speed_mbps"], 12.5)
        self.assertEqual(saved["latency_ms"], 100)

    def test_save_fragment_scan_results_writes_csv(self):
        fragment = {"packets": "1-3", "interval": "1-1", "length": "1-7"}
        rows = [{"fragment": fragment, "value": 12.5, "result": {"ok": True, "ms": 100}}]
        with tempfile.TemporaryDirectory() as td, patch.object(storage, "OUTPUT_DIR", td):
            path = storage.save_fragment_scan_results("104.16.1.1", "demo.config", "download", rows)
            with open(path, "r", encoding="utf-8", newline="") as f:
                saved_rows = list(csv.DictReader(f))

        self.assertEqual(saved_rows[0]["ip"], "104.16.1.1")
        self.assertEqual(saved_rows[0]["packets"], "1-3")
        self.assertEqual(saved_rows[0]["latency_ms"], "100")
        self.assertEqual(saved_rows[0]["speed_mbps"], "12.5")


if __name__ == "__main__":
    unittest.main()
