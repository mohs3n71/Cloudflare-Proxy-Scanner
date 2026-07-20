import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from proxy_tester import gui_about


class AboutTests(unittest.TestCase):
    def test_xray_version_uses_packaged_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "xray")
            metadata_path = os.path.join(directory, gui_about.XRAY_METADATA_FILE)
            with open(metadata_path, "w", encoding="utf-8") as metadata_file:
                json.dump({"version": "v26.7.19"}, metadata_file)

            with patch.object(gui_about, "_xray_version_command") as command:
                self.assertEqual(gui_about.get_xray_version(executable), "v26.7.19")
            command.assert_not_called()

    def test_xray_version_falls_back_to_binary(self):
        completed = subprocess.CompletedProcess(
            args=["xray", "version"], returncode=0, stdout="Xray 26.7.19 (Xray, Penetrates Everything.)\n"
        )
        with patch.object(gui_about.subprocess, "run", return_value=completed):
            self.assertEqual(gui_about.get_xray_version("missing/xray"), "v26.7.19")

    def test_xray_version_is_unavailable_when_detection_fails(self):
        with patch.object(gui_about.subprocess, "run", side_effect=OSError("missing")):
            self.assertEqual(gui_about.get_xray_version("missing/xray"), "Unavailable")

    def test_xray_version_handles_invalid_metadata_and_command_output(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata_path = os.path.join(directory, gui_about.XRAY_METADATA_FILE)
            with open(metadata_path, "w", encoding="utf-8") as metadata_file:
                metadata_file.write("not json")
            completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="")
            with patch.object(gui_about.subprocess, "run", return_value=completed):
                self.assertEqual(gui_about.get_xray_version(os.path.join(directory, "xray")), "Unavailable")

    def test_open_github_repository_opens_new_browser_tab(self):
        app = object.__new__(gui_about.AboutMixin)
        with patch.object(gui_about.webbrowser, "open_new_tab", return_value=True) as open_tab:
            app._open_github_repository()
        open_tab.assert_called_once_with(gui_about.GITHUB_URL)

    def test_open_github_repository_reports_failure(self):
        app = object.__new__(gui_about.AboutMixin)
        with patch.object(gui_about.webbrowser, "open_new_tab", return_value=False), patch.object(
            gui_about.messagebox, "showerror"
        ) as showerror:
            app._open_github_repository()
        showerror.assert_called_once()

    def test_open_github_repository_reports_browser_error(self):
        app = object.__new__(gui_about.AboutMixin)
        with patch.object(
            gui_about.webbrowser,
            "open_new_tab",
            side_effect=gui_about.webbrowser.Error("failed"),
        ), patch.object(gui_about.messagebox, "showerror") as showerror:
            app._open_github_repository()
        showerror.assert_called_once()


if __name__ == "__main__":
    unittest.main()
