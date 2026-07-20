import json
import os
import queue
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from proxy_tester import gui_about


class FakeVar:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)


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

    def test_available_update_opens_release_download_page(self):
        app = object.__new__(gui_about.AboutMixin)
        app.update_button = FakeButton()
        app.update_status_var = FakeVar()
        app._open_web_page = Mock(return_value=True)
        result = {"available": True, "version": "v1.0.4", "url": "https://example.test/release"}

        app._handle_update_check_result(result)

        self.assertEqual(app.update_button.state, "normal")
        self.assertIn("v1.0.4", app.update_status_var.value)
        app._open_web_page.assert_called_once_with(
            "https://example.test/release",
            "Unable to Open Download Page",
        )

    def test_current_version_reports_no_update(self):
        app = object.__new__(gui_about.AboutMixin)
        app.update_button = FakeButton()
        app.update_status_var = FakeVar()

        with patch.object(gui_about.messagebox, "showinfo") as showinfo:
            app._handle_update_check_result(
                {"available": False, "version": "v1.0.4", "url": "https://example.test/release"}
            )

        self.assertIn("latest version", app.update_status_var.value)
        showinfo.assert_called_once()

    def test_update_error_restores_button(self):
        app = object.__new__(gui_about.AboutMixin)
        app.update_button = FakeButton()
        app.update_status_var = FakeVar()

        with patch.object(gui_about.messagebox, "showerror") as showerror:
            app._handle_update_check_error("offline")

        self.assertEqual(app.update_button.state, "normal")
        self.assertIn("Unable", app.update_status_var.value)
        showerror.assert_called_once()

    def test_update_worker_queues_success(self):
        app = object.__new__(gui_about.AboutMixin)
        app.events = queue.Queue()
        result = {"available": False, "version": "v1.0.4", "url": "https://example.test/release"}

        with patch.object(gui_about, "check_for_update", return_value=result):
            app._update_check_worker()

        self.assertEqual(app.events.get_nowait(), ("update_check_result", result))

    def test_update_worker_queues_failure(self):
        app = object.__new__(gui_about.AboutMixin)
        app.events = queue.Queue()

        with patch.object(gui_about, "check_for_update", side_effect=OSError("offline")):
            app._update_check_worker()

        self.assertEqual(app.events.get_nowait(), ("update_check_error", "offline"))


if __name__ == "__main__":
    unittest.main()
