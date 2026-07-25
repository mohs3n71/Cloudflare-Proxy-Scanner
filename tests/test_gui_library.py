import queue
import threading
import unittest
from unittest.mock import Mock, patch

from proxy_tester import gui, gui_library
from proxy_tester.proxy_library import make_library_entry
from tests.test_proxy_library import TROJAN_URL, VLESS_URL
from tests.test_gui import FakeButton, FakeProgress, FakeVar


class FakeLibraryTable:
    def __init__(self):
        self.rows = {}
        self.selected = []
        self.headings = {}
        self.moved = []
        self.focused = None
        self.seen = None

    def selection(self):
        return tuple(self.selected)

    def selection_set(self, items):
        self.selected = list(items) if isinstance(items, (list, tuple, set)) else [items]

    def get_children(self):
        return list(self.rows)

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, parent, index, iid, values, tags=()):
        self.rows[iid] = {"values": values, "tags": tags}
        return iid

    def item(self, item, **kwargs):
        if kwargs:
            self.rows[item].update(kwargs)
        return self.rows[item]

    def move(self, item, parent, index):
        self.moved.append((item, index))

    def focus(self, item):
        self.focused = item

    def see(self, item):
        self.seen = item

    def heading(self, column, **kwargs):
        self.headings.setdefault(column, {}).update(kwargs)


class FakeText:
    def __init__(self, value=""):
        self.value = value

    def get(self, start, end):
        return self.value

    def delete(self, start, end):
        self.value = ""


class FakeThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started


class ProxyLibraryGuiTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.proxy_library_entries = [make_library_entry(VLESS_URL), make_library_entry(TROJAN_URL)]
        app.proxy_library_items = {}
        app.proxy_library_sort_column = "name"
        app.proxy_library_sort_reverse = False
        app.proxy_library_active_id = None
        app.proxy_library_log_path = None
        app.proxy_library_table = FakeLibraryTable()
        app.proxy_library_status_var = FakeVar()
        app.proxy_library_progress = FakeProgress()
        app.proxy_library_stop_event = threading.Event()
        app.proxy_library_worker = None
        app.events = queue.Queue()
        app._track_process = Mock()
        app._untrack_process = Mock()
        app._kill_active_processes = Mock()
        for name in (
            "proxy_library_import_button",
            "proxy_library_remove_button",
            "proxy_library_clear_results_button",
            "proxy_library_run_button",
            "proxy_library_download_button",
            "proxy_library_upload_button",
            "proxy_library_both_button",
            "proxy_library_stop_button",
            "proxy_library_size_entry",
            "proxy_library_timeout_entry",
            "proxy_library_fragment_enabled_check",
            "proxy_library_fragment_packets_entry",
            "proxy_library_fragment_interval_entry",
            "proxy_library_fragment_length_entry",
        ):
            setattr(app, name, FakeButton())
        app.proxy_library_size_var = FakeVar("1")
        app.proxy_library_timeout_var = FakeVar("7000")
        app.proxy_library_fragment_enabled_var = FakeVar(False)
        app.proxy_library_fragment_packets_var = FakeVar("tlshello")
        app.proxy_library_fragment_interval_var = FakeVar("1-2")
        app.proxy_library_fragment_length_var = FakeVar("5-10")
        return app

    def test_import_configs_persists_valid_entries(self):
        app = self.make_app()
        app.proxy_library_entries = []
        app.proxy_library_input = FakeText(f"{VLESS_URL}\n{TROJAN_URL}")

        with patch.object(gui_library, "save_proxy_library") as save:
            app.import_proxy_library_configs()

        self.assertEqual(len(app.proxy_library_entries), 2)
        save.assert_called_once()
        self.assertEqual(app.proxy_library_input.value, "")

    def test_import_without_supported_urls_warns(self):
        app = self.make_app()
        app.proxy_library_input = FakeText("not a proxy link")

        with patch.object(gui_library.messagebox, "showwarning") as showwarning:
            app.import_proxy_library_configs()

        showwarning.assert_called_once()

    def test_init_library_recovers_from_invalid_saved_file(self):
        app = object.__new__(gui.ProxyTesterGui)

        with patch.object(gui_library, "load_proxy_library", side_effect=ValueError("bad json")):
            app._init_proxy_library()

        self.assertEqual(app.proxy_library_entries, [])
        self.assertEqual(app.proxy_library_load_error, "bad json")

    def test_test_settings_validate_positive_values(self):
        app = self.make_app()

        self.assertEqual(app._proxy_library_test_settings(), (1024 * 1024, 7000))
        app.proxy_library_timeout_var.set("0")
        with patch.object(gui_library.messagebox, "showerror") as showerror:
            self.assertIsNone(app._proxy_library_test_settings())
        showerror.assert_called_once()

    def test_fragment_settings_are_disabled_by_default_and_validate_enabled_values(self):
        app = self.make_app()

        self.assertEqual(app._proxy_library_fragment_settings(), {})
        app.proxy_library_fragment_enabled_var.set(True)
        self.assertEqual(
            app._proxy_library_fragment_settings(),
            {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
        )
        app.proxy_library_fragment_interval_var.set("")
        with patch.object(gui_library.messagebox, "showerror") as showerror:
            self.assertIsNone(app._proxy_library_fragment_settings())
        showerror.assert_called_once()

    def test_fragment_fields_follow_checkbox_state(self):
        app = self.make_app()

        app._sync_proxy_library_fragment_state()
        self.assertEqual(app.proxy_library_fragment_packets_entry.state, "disabled")
        app.proxy_library_fragment_enabled_var.set(True)
        app._sync_proxy_library_fragment_state()
        self.assertEqual(app.proxy_library_fragment_packets_entry.state, "normal")

    def test_worker_tests_original_servers_sequentially(self):
        app = self.make_app()
        results = [
            {"ok": True, "ip": "example.com", "ms": 50, "download_mbps": 10},
            {"ok": True, "ip": "trojan.example", "ms": 60, "download_mbps": 9},
        ]

        with patch.object(gui_library, "test_ip", side_effect=results) as test:
            app._proxy_library_test_worker(
                app.proxy_library_entries,
                "download",
                1024,
                7000,
                {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
            )

        self.assertEqual(test.call_count, 2)
        self.assertEqual(test.call_args_list[0].args[0], "example.com")
        self.assertEqual(test.call_args_list[1].args[0], "trojan.example")
        self.assertEqual(
            test.call_args_list[0].kwargs["fragment"],
            {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
        )
        events = list(app.events.queue)
        self.assertEqual(events[-1][:3], ("proxy_library_done", 2, 2))

    def test_start_uses_selected_rows_or_all_when_selection_is_empty(self):
        app = self.make_app()
        selected_id = app.proxy_library_entries[1]["id"]
        app.proxy_library_table.selected = [selected_id]

        with patch.object(gui_library.threading, "Thread", FakeThread), patch.object(
            gui_library, "create_log_file", return_value="logs/library.log"
        ), patch.object(gui_library, "append_log_line"):
            app.start_proxy_library_test("upload")

        self.assertTrue(app.proxy_library_worker.started)
        self.assertEqual([entry["id"] for entry in app.proxy_library_worker.args[0]], [selected_id])
        self.assertEqual(app.proxy_library_worker.args[1], "upload")
        self.assertEqual(app.proxy_library_worker.args[4], {})
        self.assertEqual(app.proxy_library_stop_button.state, "normal")
        self.assertEqual(app.proxy_library_fragment_enabled_check.state, "disabled")

    def test_start_warns_when_library_is_empty(self):
        app = self.make_app()
        app.proxy_library_entries = []

        with patch.object(gui_library.messagebox, "showwarning") as showwarning:
            app.start_proxy_library_test("download")

        showwarning.assert_called_once()

    def test_apply_result_preserves_untested_direction_and_selects_row(self):
        app = self.make_app()
        entry = app.proxy_library_entries[0]
        entry["upload_mbps"] = 4
        app._render_proxy_library()

        with patch.object(gui_library, "save_proxy_library"):
            app._apply_proxy_library_result(
                entry["id"],
                "download",
                {"ok": True, "ms": 80, "download_mbps": 20},
            )

        updated = app.proxy_library_entries[0]
        self.assertEqual(updated["download_mbps"], 20)
        self.assertEqual(updated["upload_mbps"], 4)
        self.assertEqual(app.proxy_library_table.selected, [entry["id"]])

    def test_sorting_uses_numeric_download_values_and_marks_heading(self):
        app = self.make_app()
        app.proxy_library_entries[0]["download_mbps"] = 2
        app.proxy_library_entries[1]["download_mbps"] = 20

        app.sort_proxy_library_by("download")

        self.assertTrue(app.proxy_library_sort_reverse)
        ordered = app._sorted_proxy_library_entries()
        self.assertEqual(ordered[0]["download_mbps"], 20)
        self.assertIn("\u25bc", app.proxy_library_table.headings["download"]["text"])

    def test_stop_sets_event_and_kills_active_process(self):
        app = self.make_app()

        app.stop_proxy_library_tests()

        self.assertTrue(app.proxy_library_stop_event.is_set())
        app._kill_active_processes.assert_called_once()
        self.assertEqual(app.proxy_library_stop_button.state, "disabled")

    def test_remove_selected_configs_persists_after_confirmation(self):
        app = self.make_app()
        removed_id = app.proxy_library_entries[0]["id"]
        app.proxy_library_table.selected = [removed_id]

        with patch.object(gui_library.messagebox, "askyesno", return_value=True), patch.object(
            gui_library, "save_proxy_library"
        ) as save:
            app.remove_proxy_library_configs()

        self.assertNotIn(removed_id, [entry["id"] for entry in app.proxy_library_entries])
        save.assert_called_once()

    def test_clear_results_only_changes_selected_rows(self):
        app = self.make_app()
        first, second = app.proxy_library_entries
        first.update(download_mbps=10, status="Passed")
        second.update(download_mbps=20, status="Passed")
        app.proxy_library_table.selected = [first["id"]]

        with patch.object(gui_library, "save_proxy_library"):
            app.clear_proxy_library_results()

        self.assertEqual(first["download_mbps"], "")
        self.assertEqual(first["status"], "Not tested")
        self.assertEqual(second["download_mbps"], 20)

    def test_event_handler_updates_active_row_result_and_completion(self):
        app = self.make_app()
        app._render_proxy_library()
        entry_id = app.proxy_library_entries[0]["id"]

        app.handle_proxy_library_event(("proxy_library_active", entry_id, True))
        self.assertEqual(app.proxy_library_table.rows[entry_id]["tags"], ("active",))
        with patch.object(gui_library, "save_proxy_library"):
            app.handle_proxy_library_event(
                (
                    "proxy_library_result",
                    entry_id,
                    "download",
                    {"ok": True, "ms": 40, "download_mbps": 15},
                    1,
                    2,
                )
            )
        self.assertEqual(app.proxy_library_progress.value, 50)
        app.handle_proxy_library_event(("proxy_library_done", 1, 2, True))
        self.assertIn("Stopped", app.proxy_library_status_var.value)
        self.assertEqual(app.proxy_library_download_button.state, "normal")

    def test_failed_result_is_written_to_dedicated_log(self):
        app = self.make_app()
        app._render_proxy_library()
        app.proxy_library_log_path = "logs/library.log"
        entry_id = app.proxy_library_entries[0]["id"]

        with patch.object(gui_library, "save_proxy_library"), patch.object(
            gui_library, "append_log_line"
        ) as append:
            app.handle_proxy_library_event(
                (
                    "proxy_library_result",
                    entry_id,
                    "upload",
                    {"ok": False, "ip": "example.com", "ms": -1, "error": "timeout"},
                    1,
                    1,
                )
            )

        append.assert_called_once()
        self.assertEqual(append.call_args.args[0], "logs/library.log")
        self.assertIn("FAIL example.com", append.call_args.args[1])

    def test_run_selected_hands_profile_and_address_to_runner(self):
        app = self.make_app()
        selected = app.proxy_library_entries[1]
        app.proxy_library_table.selected = [selected["id"]]
        app.runner_profile_var = FakeVar()
        app.runner_ip_var = FakeVar()
        app.notebook = Mock()
        app.runner_tab = object()
        app.start_xray_runner = Mock()

        app.run_library_config_with_xray()

        self.assertEqual(app.runner_profile.protocol, "trojan")
        self.assertEqual(app.runner_ip_var.value, "trojan.example")
        app.notebook.select.assert_called_once_with(app.runner_tab)
        app.start_xray_runner.assert_called_once_with("trojan.example")

    def test_run_requires_exactly_one_selected_configuration(self):
        app = self.make_app()

        with patch.object(gui_library.messagebox, "showwarning") as showwarning:
            app.run_library_config_with_xray()

        showwarning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
