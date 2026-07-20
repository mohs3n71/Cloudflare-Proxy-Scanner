import json
import os
import tempfile
import unittest

from proxy_tester.settings import (
    DEFAULT_FRAGMENT_ENABLED,
    RunnerSettings,
    SYSTEM_PROXY_SET,
    load_runner_settings,
    save_runner_settings,
)


class RunnerSettingsTests(unittest.TestCase):
    def test_fragmentation_is_disabled_by_default(self):
        self.assertFalse(DEFAULT_FRAGMENT_ENABLED)
        self.assertFalse(RunnerSettings().fragment_enabled)

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
