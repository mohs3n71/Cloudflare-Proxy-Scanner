import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools import build_release, xray_release


class XrayReleaseTests(unittest.TestCase):
    def test_normalize_os_supports_runtime_names(self):
        self.assertEqual(xray_release.normalize_os("win32"), "windows")
        self.assertEqual(xray_release.normalize_os("darwin"), "macos")
        self.assertEqual(xray_release.normalize_os("linux"), "linux")

    def test_normalize_arch_supports_common_names(self):
        self.assertEqual(xray_release.normalize_arch("AMD64"), "x64")
        self.assertEqual(xray_release.normalize_arch("i686"), "x86")
        self.assertEqual(xray_release.normalize_arch("aarch64"), "arm64")

    def test_xray_asset_name_covers_release_targets(self):
        expected = {
            ("windows", "x64"): "Xray-windows-64.zip",
            ("windows", "x86"): "Xray-windows-32.zip",
            ("windows", "arm64"): "Xray-windows-arm64-v8a.zip",
            ("linux", "x64"): "Xray-linux-64.zip",
            ("linux", "x86"): "Xray-linux-32.zip",
            ("linux", "arm64"): "Xray-linux-arm64-v8a.zip",
            ("macos", "x64"): "Xray-macos-64.zip",
            ("macos", "arm64"): "Xray-macos-arm64-v8a.zip",
        }

        self.assertEqual(xray_release.XRAY_ASSETS, expected)
        for target, asset_name in expected.items():
            self.assertEqual(xray_release.xray_asset_name(*target), asset_name)

    def test_release_api_url_supports_latest_and_version_tags(self):
        self.assertTrue(xray_release.release_api_url("latest").endswith("/releases?per_page=100"))
        self.assertTrue(xray_release.release_api_url("26.3.27").endswith("/tags/v26.3.27"))

    def test_select_latest_published_release_includes_prereleases(self):
        releases = [
            {"tag_name": "v1", "published_at": "2026-01-01T00:00:00Z", "draft": False, "prerelease": False},
            {"tag_name": "v2", "published_at": "2026-02-01T00:00:00Z", "draft": False, "prerelease": True},
            {"tag_name": "v3", "published_at": "2026-03-01T00:00:00Z", "draft": True, "prerelease": False},
        ]

        selected = xray_release.select_latest_published_release(releases)

        self.assertEqual(selected["tag_name"], "v2")

    def test_resolve_release_uses_newest_published_release_for_latest(self):
        releases = [
            {"tag_name": "v1", "published_at": "2026-01-01T00:00:00Z", "draft": False},
            {"tag_name": "v2", "published_at": "2026-02-01T00:00:00Z", "draft": False},
        ]
        with patch.object(xray_release, "_read_json", return_value=releases):
            release = xray_release.resolve_release("latest")

        self.assertEqual(release["tag_name"], "v2")

    def test_select_release_asset_returns_matching_download(self):
        release = {
            "tag_name": "v1",
            "assets": [{"name": "Xray-linux-64.zip", "browser_download_url": "https://example.com/xray.zip"}],
        }

        self.assertEqual(
            xray_release.select_release_asset(release, "Xray-linux-64.zip"),
            "https://example.com/xray.zip",
        )

    def test_find_archive_member_accepts_nested_binary(self):
        self.assertEqual(
            xray_release.find_archive_member(["docs/LICENSE", "release/xray", "README"], "xray"),
            "release/xray",
        )

    def test_detect_arch_uses_x86_for_32_bit_python(self):
        with patch.object(xray_release.struct, "calcsize", return_value=4):
            self.assertEqual(xray_release.detect_arch(), "x86")

    def test_xray_metadata_matches_version_and_platform(self):
        with tempfile.TemporaryDirectory() as output_dir:
            xray_release.write_xray_metadata(output_dir, "linux", "arm64", "v2")

            self.assertTrue(xray_release.installed_xray_matches(output_dir, "linux", "arm64", "v2"))
            self.assertFalse(xray_release.installed_xray_matches(output_dir, "linux", "x64", "v2"))

    def test_if_missing_uses_existing_binary_when_release_check_is_offline(self):
        with tempfile.TemporaryDirectory() as output_dir:
            binary_path = os.path.join(output_dir, "xray")
            with open(binary_path, "wb") as binary_file:
                binary_file.write(b"existing")
            with patch.object(xray_release, "resolve_release", side_effect=OSError("offline")):
                path, version = xray_release.download_xray(
                    "linux",
                    "x64",
                    output_dir,
                    if_missing=True,
                )

        self.assertEqual(path, binary_path)
        self.assertIsNone(version)

    def test_if_missing_reuses_binary_when_latest_metadata_matches(self):
        release = {"tag_name": "v2", "assets": []}
        with tempfile.TemporaryDirectory() as output_dir:
            binary_path = os.path.join(output_dir, "xray")
            with open(binary_path, "wb") as binary_file:
                binary_file.write(b"current")
            xray_release.write_xray_metadata(output_dir, "linux", "x64", "v2")
            with patch.object(xray_release, "resolve_release", return_value=release):
                with patch.object(xray_release, "_read_bytes") as read_bytes:
                    path, version = xray_release.download_xray(
                        "linux",
                        "x64",
                        output_dir,
                        if_missing=True,
                    )

        self.assertEqual(path, binary_path)
        self.assertIsNone(version)
        read_bytes.assert_not_called()

    def test_request_bytes_retries_transient_network_errors(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"ready"
        with patch.object(
            xray_release.urllib.request,
            "urlopen",
            side_effect=[xray_release.urllib.error.URLError("timeout"), response],
        ):
            with patch.object(xray_release.time, "sleep") as sleep:
                content = xray_release._request_bytes(object(), timeout=1)

        self.assertEqual(content, b"ready")
        sleep.assert_called_once_with(1)


class BuildReleaseTests(unittest.TestCase):
    def test_release_name_contains_platform_and_architecture(self):
        self.assertEqual(
            build_release.release_name("windows", "arm64"),
            "cloudflare-proxy-scanner-windows-arm64",
        )

    def test_validate_native_target_rejects_cross_compile(self):
        with self.assertRaisesRegex(RuntimeError, "cannot cross-compile"):
            build_release.validate_native_target("linux", "arm64", "windows", "x64")

    def test_validate_build_dependencies_lists_missing_packages(self):
        available = {"PyInstaller": object(), "qrcode": None}
        with patch.object(build_release.importlib.util, "find_spec", side_effect=available.get):
            with self.assertRaisesRegex(RuntimeError, "qrcode"):
                build_release.validate_build_dependencies()

    def test_pyinstaller_command_bundles_staged_xray(self):
        command = build_release.pyinstaller_command(
            "linux",
            "x64",
            "runtime/xray",
            "dist",
            "work",
            "spec",
        )

        self.assertIn("--onefile", command)
        self.assertIn("--windowed", command)
        self.assertIn(f"runtime/xray{os.pathsep}bin/xray", command)


if __name__ == "__main__":
    unittest.main()
