import queue
import unittest
from unittest.mock import Mock, patch

from proxy_tester import launcher


class FakeProgress:
    def __init__(self):
        self.config = {}
        self.started = False

    def stop(self):
        self.started = False

    def start(self, _interval):
        self.started = True

    def configure(self, **kwargs):
        self.config.update(kwargs)


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class LauncherTests(unittest.TestCase):
    def make_bootstrap(self):
        bootstrap = object.__new__(launcher.XrayBootstrap)
        bootstrap.events = queue.Queue()
        bootstrap.progress = FakeProgress()
        bootstrap.status_var = FakeVar()
        return bootstrap

    def test_prepare_worker_queues_progress_and_completion(self):
        bootstrap = self.make_bootstrap()

        def download(*_args, **kwargs):
            kwargs["progress"](25, 100)

        with patch.object(launcher, "download_xray", side_effect=download):
            bootstrap._prepare_xray()

        self.assertEqual(bootstrap.events.get_nowait(), ("progress", 25, 100))
        self.assertEqual(bootstrap.events.get_nowait(), ("done",))

    def test_prepare_worker_queues_download_error(self):
        bootstrap = self.make_bootstrap()
        with patch.object(launcher, "download_xray", side_effect=OSError("offline")):
            bootstrap._prepare_xray()

        event = bootstrap.events.get_nowait()
        self.assertEqual(event[0], "error")
        self.assertEqual(event[3], "offline")

    def test_known_download_size_shows_percentage(self):
        bootstrap = self.make_bootstrap()

        bootstrap._show_download_progress(50, 100)

        self.assertEqual(bootstrap.progress.config["mode"], "determinate")
        self.assertEqual(bootstrap.progress.config["value"], 50)
        self.assertIn("50%", bootstrap.status_var.value)

    def test_unknown_download_size_shows_megabytes(self):
        bootstrap = self.make_bootstrap()

        bootstrap._show_download_progress(2 * 1024 * 1024, 0)

        self.assertEqual(bootstrap.progress.config["mode"], "indeterminate")
        self.assertTrue(bootstrap.progress.started)
        self.assertIn("2.0 MB", bootstrap.status_var.value)

    def test_completion_stops_animation_before_destroying_window(self):
        bootstrap = self.make_bootstrap()
        bootstrap.succeeded = False
        bootstrap.destroy = Mock()
        bootstrap.after = Mock()
        bootstrap.progress.start(12)
        bootstrap.events.put(("done",))

        bootstrap._drain_events()

        self.assertTrue(bootstrap.succeeded)
        self.assertFalse(bootstrap.progress.started)
        bootstrap.destroy.assert_called_once()
        bootstrap.after.assert_not_called()


if __name__ == "__main__":
    unittest.main()
