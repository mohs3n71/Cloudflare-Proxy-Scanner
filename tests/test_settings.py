import json
import os
import tempfile
import unittest

from proxy_tester.settings import (
    DEFAULT_APPEARANCE_MODE,
    DEFAULT_FRAGMENT_ENABLED,
    DEFAULT_FRAGMENT_INTERVAL,
    DEFAULT_FRAGMENT_LENGTH,
    DEFAULT_FRAGMENT_PACKETS,
    DEFAULT_RESTRICTED_NETWORK_MODE,
    DEFAULT_SCAN_IP_COUNT,
    RunnerSettings,
    SYSTEM_PROXY_SET,
    load_custom_range_values,
    load_appearance_mode,
    load_runner_settings,
    save_custom_range_values,
    save_appearance_mode,
    save_runner_settings,
)


class RunnerSettingsTests(unittest.TestCase):
    def test_default_scan_ip_count_is_one_thousand(self):
        self.assertEqual(DEFAULT_SCAN_IP_COUNT, 1000)

    def test_appearance_round_trip_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            save_runner_settings(RunnerSettings(port="2080"), path)

            save_appearance_mode("dark", path)

            self.assertEqual(load_appearance_mode(path), "dark")
            self.assertEqual(load_runner_settings(path).port, "2080")

    def test_invalid_appearance_uses_default_and_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump({"appearance": "neon"}, settings_file)

            self.assertEqual(load_appearance_mode(path), DEFAULT_APPEARANCE_MODE)
            with self.assertRaises(ValueError):
                save_appearance_mode("neon", path)

    def test_fragmentation_is_disabled_by_default(self):
        self.assertFalse(DEFAULT_FRAGMENT_ENABLED)
        self.assertFalse(DEFAULT_RESTRICTED_NETWORK_MODE)
        self.assertFalse(RunnerSettings().fragment_enabled)

    def test_fragment_defaults_target_real_clienthello(self):
        settings = RunnerSettings()

        self.assertEqual(DEFAULT_FRAGMENT_PACKETS, "tlshello")
        self.assertEqual(DEFAULT_FRAGMENT_INTERVAL, "1-2")
        self.assertEqual(DEFAULT_FRAGMENT_LENGTH, "5-10")
        self.assertEqual(settings.fragment_packets, DEFAULT_FRAGMENT_PACKETS)
        self.assertEqual(settings.fragment_interval, DEFAULT_FRAGMENT_INTERVAL)
        self.assertEqual(settings.fragment_length, DEFAULT_FRAGMENT_LENGTH)

    def test_runner_settings_round_trip(self):
        expected = RunnerSettings(
            ip="104.16.1.1",
            port="2080",
            share=True,
            system_proxy_mode=SYSTEM_PROXY_SET,
            fragment_enabled=False,
            fragment_packets="tlshello",
            fragment_interval="2-5",
            fragment_length="5-15",
            speed_size_mb="2.5",
            speed_timeout_ms="9000",
            fragment_scan_mode="upload",
            custom_fragments_text="1-3,1-1,1-7",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")

            save_runner_settings(expected, path)

            self.assertEqual(load_runner_settings(path), expected)

    def test_save_runner_settings_preserves_other_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump({"scanner": {"parallel": 50}}, settings_file)

            save_runner_settings(RunnerSettings(port="2080"), path)

            with open(path, "r", encoding="utf-8") as settings_file:
                saved = json.load(settings_file)
            self.assertEqual(saved["scanner"], {"parallel": 50})
            self.assertEqual(saved["xray_runner"]["port"], "2080")

    def test_custom_ranges_round_trip_and_preserve_runner_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            save_runner_settings(RunnerSettings(port="2080"), path)
            save_custom_range_values(["192.0.2.0/24", "198.51.100.7/32"], path)

            self.assertEqual(load_custom_range_values(path), ["192.0.2.0/24", "198.51.100.7/32"])
            self.assertEqual(load_runner_settings(path).port, "2080")

    def test_load_runner_settings_uses_defaults_for_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump(
                    {
                        "xray_runner": {
                            "port": "70000",
                            "share": "yes",
                            "system_proxy_mode": "invalid",
                            "speed_size_mb": "0",
                            "speed_timeout_ms": "bad",
                            "fragment_scan_mode": "both",
                        }
                    },
                    settings_file,
                )

            loaded = load_runner_settings(path)

            self.assertEqual(loaded.port, "1080")
            self.assertFalse(loaded.share)
            self.assertEqual(loaded.speed_size_mb, "1")
            self.assertEqual(loaded.speed_timeout_ms, "7000")
            self.assertEqual(loaded.fragment_scan_mode, "download")

    def test_load_runner_settings_recovers_from_damaged_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as settings_file:
                settings_file.write("not json")

            self.assertEqual(load_runner_settings(path), RunnerSettings())

    def test_load_runner_settings_migrates_legacy_system_proxy_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as settings_file:
                json.dump({"xray_runner": {"system_proxy_mode": "Set system proxy"}}, settings_file)

            loaded = load_runner_settings(path)

            self.assertEqual(loaded.system_proxy_mode, SYSTEM_PROXY_SET)


if __name__ == "__main__":
    unittest.main()
