import ipaddress
import os
import queue
import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from proxy_tester import gui, gui_config, gui_runner, gui_workers
from proxy_tester.settings import AppSettings
from tests.test_gui import FakeButton, FakeLog, FakeProgress, FakeTempDir, FakeVar


class GuiConfigExtendedTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.settings = AppSettings(10, 2000)
        app.concurrency_var = FakeVar("50")
        app.timeout_var = FakeVar("3000")
        app.speed_size_var = FakeVar("1.5")
        app.speed_timeout_var = FakeVar("7000")
        app.speed_fragment_enabled_var = FakeVar(False)
        app.output_var = FakeVar("")
        app.output_paths_by_name = {}
        app.profile = None
        return app

    def test_validate_scan_and_speed_settings(self):
        app = self.make_app()

        self.assertTrue(app._validate_settings())
        self.assertEqual((app.settings.concurrency, app.settings.timeout_ms), (50, 3000))
        self.assertEqual(app._speed_settings(), (int(1.5 * 1024 * 1024), 7000))

        app.timeout_var.set("0")
        app.speed_size_var.set("bad")
        with patch.object(gui_config.messagebox, "showerror") as showerror:
            self.assertFalse(app._validate_settings())
            self.assertIsNone(app._speed_settings())
        self.assertEqual(showerror.call_count, 2)

    def test_speed_fragment_settings_validate_required_values(self):
        app = self.make_app()
        self.assertEqual(app._speed_fragment_settings(), {})

        app.speed_fragment_enabled_var.set(True)
        app.speed_fragment_packets_var = FakeVar("1-3")
        app.speed_fragment_interval_var = FakeVar("")
        app.speed_fragment_length_var = FakeVar("1-7")
        with patch.object(gui_config.messagebox, "showerror") as showerror:
            self.assertIsNone(app._speed_fragment_settings())
        showerror.assert_called_once()

        app.speed_fragment_interval_var.set("1-1")
        self.assertEqual(
            app._speed_fragment_settings(),
            {"packets": "1-3", "interval": "1-1", "length": "1-7"},
        )

    def test_selected_paths_profiles_and_csv_defaults(self):
        app = self.make_app()
        with patch.object(gui_config.messagebox, "showwarning") as showwarning:
            self.assertIsNone(app._selected_output_path())
            self.assertIsNone(app._selected_profile())
        self.assertEqual(showwarning.call_count, 2)

        app.output_var.set("scan.csv")
        app.output_paths_by_name["scan.csv"] = "output/scan.csv"
        app.profile = object()
        self.assertEqual(app._selected_output_path(), "output/scan.csv")
        self.assertIs(app._selected_profile(), app.profile)
        self.assertEqual(
            app._result_from_csv_row({"ip": " 1.1.1.1 ", "latency_ms": "bad"}),
            {"ip": "1.1.1.1", "ok": True, "ms": -1, "download_mbps": "", "upload_mbps": ""},
        )
        self.assertEqual(
            app._result_from_csv_row(
                {
                    "ip": "1.1.1.1",
                    "latency_ms": "-1.0",
                    "download_mbps": "-1.0",
                    "upload_mbps": "-1",
                }
            ),
            {"ip": "1.1.1.1", "ok": True, "ms": -1, "download_mbps": -1, "upload_mbps": -1},
        )

    def test_select_config_handles_success_and_parse_failure(self):
        app = self.make_app()
        app.config_var = FakeVar("good.config")
        app.config_paths_by_name = {"good.config": "configs/good.config"}
        app._log = Mock()
        app.status_var = FakeVar()
        app._sync_config_action_state = Mock()
        profile = object()

        with patch.object(gui_config, "parse_proxy_config", return_value=profile):
            app._select_config()
        self.assertIs(app.profile, profile)
        app._log.assert_called_once()

        with patch.object(gui_config, "parse_proxy_config", side_effect=ValueError("invalid")), patch.object(
            gui_config.messagebox, "showerror"
        ) as showerror:
            app._select_config()
        self.assertIsNone(app.profile)
        showerror.assert_called_once()
        self.assertEqual(app._sync_config_action_state.call_count, 2)

    def test_config_management_buttons_follow_selected_file(self):
        app = self.make_app()
        app.config_var = FakeVar("demo.config")
        app.config_paths_by_name = {"demo.config": "configs/demo.config"}
        app.edit_config_button = FakeButton()
        app.remove_config_button = FakeButton()

        app._sync_config_management_state()

        self.assertEqual(app.edit_config_button.state, "normal")
        self.assertEqual(app.remove_config_button.state, "normal")
        app.config_var.set("")
        app._sync_config_management_state()
        self.assertEqual(app.edit_config_button.state, "disabled")
        self.assertEqual(app.remove_config_button.state, "disabled")

    def test_remove_selected_config_requires_confirmation(self):
        app = self.make_app()
        app.config_var = FakeVar("demo.config")
        app._load_configs = Mock()
        app._log = Mock()
        with tempfile.TemporaryDirectory() as config_dir:
            path = os.path.join(config_dir, "demo.config")
            with open(path, "w", encoding="utf-8") as config_file:
                config_file.write("vless://demo\n")
            app.config_paths_by_name = {"demo.config": path}

            with patch.object(gui_config.messagebox, "askyesno", return_value=False):
                app.remove_selected_config()
            self.assertTrue(os.path.exists(path))

            with patch.object(gui_config.messagebox, "askyesno", return_value=True):
                app.remove_selected_config()
            self.assertFalse(os.path.exists(path))

        app._load_configs.assert_called_once()
        app._log.assert_called_once_with("Removed configuration: demo.config")

    def test_create_proxy_configs_saves_rows_and_refreshes_outputs(self):
        app = self.make_app()
        app.profile = object()
        app.output_var.set("scan.csv")
        app.output_paths_by_name = {"scan.csv": "output/scan.csv"}
        app._load_outputs = Mock()
        rows = [{"ip": "1.1.1.1"}]
        with patch.object(gui_config, "read_working_ips", return_value=rows), patch.object(
            gui_config, "save_proxy_configs", return_value="output/configs.txt"
        ) as save, patch.object(gui_config.messagebox, "showinfo") as showinfo:
            app.create_proxy_configs()
        save.assert_called_once_with("output/scan.csv", rows, app.profile)
        app._load_outputs.assert_called_once()
        showinfo.assert_called_once()


class GuiWorkerExtendedTests(unittest.TestCase):
    def make_worker(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.events = queue.Queue()
        app.stop_event = threading.Event()
        app.active_processes_lock = threading.Lock()
        app.active_processes = set()
        app._track_process = Mock()
        app._untrack_process = Mock()
        return app

    def test_stop_current_kills_active_processes_and_updates_controls(self):
        app = self.make_worker()
        app.worker_thread = Mock(is_alive=Mock(return_value=True))
        app._kill_active_processes = Mock()
        app.status_var = FakeVar()
        app._log = Mock()
        app.stop_scan_button = FakeButton()
        app.stop_speed_button = FakeButton()

        app.stop_current()

        self.assertTrue(app.stop_event.is_set())
        app._kill_active_processes.assert_called_once()
        self.assertEqual(app.stop_scan_button.state, "disabled")
        self.assertEqual(app.stop_speed_button.state, "disabled")

    def test_kill_active_processes_ignores_process_errors(self):
        app = self.make_worker()
        good = Mock()
        bad = Mock(kill=Mock(side_effect=OSError("gone")))
        app.active_processes.update((good, bad))

        app._kill_active_processes()

        good.kill.assert_called_once()
        bad.kill.assert_called_once()

    def test_make_scan_ips_supports_all_full_and_validates_input(self):
        app = self.make_worker()
        app.mode_var = FakeVar("all_full")
        app.count_var = FakeVar("10")
        app.range_var = FakeVar("")
        app.ranges_by_label = {}
        with patch.object(gui_workers.cloudflare, "all_candidates", return_value=iter(["1.1.1.1"])):
            self.assertEqual(app._make_scan_ips(), (["1.1.1.1"], "all Cloudflare IPs"))

        app.mode_var.set("range")
        app.count_var.set("invalid")
        with patch.object(gui_workers.messagebox, "showerror") as showerror:
            self.assertEqual(app._make_scan_ips(), (None, None))
        showerror.assert_called_once()

    def test_make_scan_ips_supports_saved_custom_ranges(self):
        app = self.make_worker()
        app.mode_var = FakeVar("custom")
        app.count_var = FakeVar("3")
        app.range_var = FakeVar("")
        app.ranges_by_label = {}
        app.custom_networks = [ipaddress.ip_network("192.0.2.0/29")]

        ips, source = app._make_scan_ips()

        self.assertEqual(len(ips), 3)
        self.assertEqual(source, "1 custom ranges")
        self.assertTrue(all(ipaddress.ip_address(ip) in app.custom_networks[0] for ip in ips))

        app.custom_networks = []
        with patch.object(gui_workers.messagebox, "showerror") as showerror:
            self.assertEqual(app._make_scan_ips(), (None, None))
        showerror.assert_called_once()

    def test_make_scan_ips_supports_every_ip_in_selected_range(self):
        app = self.make_worker()
        network = ipaddress.ip_network("192.0.2.0/30")
        app.mode_var = FakeVar("range_full")
        app.count_var = FakeVar("ignored")
        app.range_var = FakeVar("selected")
        app.ranges_by_label = {"selected": network}

        self.assertEqual(
            app._make_scan_ips(),
            (["192.0.2.1", "192.0.2.2"], "every IP in 192.0.2.0/30"),
        )

    def test_scan_worker_saves_passed_results_and_reports_done(self):
        app = self.make_worker()
        results = [
            {"ip": "1.1.1.1", "ok": True, "ms": 20},
            {"ip": "1.0.0.1", "ok": False, "ms": -1, "error": "failed"},
        ]
        with patch.object(gui_workers, "test_ip", side_effect=results), patch.object(
            gui_workers, "save_scan_results", return_value=("output/run.csv", "output/latest.csv")
        ) as save:
            app._scan_worker(
                ["1.1.1.1", "1.0.0.1"], "all", object(), None, AppSettings(2, 2000), 1024, 7000
            )

        save.assert_called_once_with([results[0]], prefix="working-cloudflare-proxy-ips")
        events = list(app.events.queue)
        self.assertEqual([event[0] for event in events].count("result"), 2)
        self.assertEqual(events[-1][0], "done")
        self.assertFalse(events[-1][4])

    def test_speed_worker_preserves_unrequested_metric(self):
        app = self.make_worker()
        initial = [{"ip": "1.1.1.1", "ok": True, "ms": 30, "download_mbps": 4.0, "upload_mbps": 8.0}]
        result = {"ip": "1.1.1.1", "ok": True, "ms": 20, "download_mbps": 9.0}
        with patch.object(gui_workers, "test_ip", return_value=result), patch.object(
            gui_workers, "save_scan_results", return_value=("output/run.csv", "output/latest.csv")
        ) as save:
            app._scan_worker(
                ["1.1.1.1"], "selected", object(), "download", AppSettings(50, 7000), 1024, 7000,
                initial_results=initial,
            )

        saved = save.call_args.args[0][0]
        self.assertEqual(saved["download_mbps"], 9.0)
        self.assertEqual(saved["upload_mbps"], 8.0)

    def test_scan_worker_reports_preexisting_stop_without_submitting(self):
        app = self.make_worker()
        app.stop_event.set()
        with patch.object(gui_workers, "test_ip") as test_ip, patch.object(
            gui_workers, "save_scan_results", return_value=("output/run.csv", "output/latest.csv")
        ):
            app._scan_worker(["1.1.1.1"], "all", object(), None, AppSettings(2, 2000), 1024, 7000)

        test_ip.assert_not_called()
        done = list(app.events.queue)[-1]
        self.assertEqual(done[0], "done")
        self.assertTrue(done[4])

    def test_scan_worker_converts_executor_failure_to_error_event(self):
        app = self.make_worker()
        with patch.object(gui_workers, "ThreadPoolExecutor", side_effect=RuntimeError("boom")):
            app._scan_worker(["1.1.1.1"], "all", object(), None, AppSettings(2, 2000), 1024, 7000)
        self.assertEqual(app.events.get_nowait(), ("error", "boom"))

    def test_drain_events_dispatches_results_runner_events_and_reschedules(self):
        app = self.make_worker()
        app.progress = FakeProgress()
        app.status_var = FakeVar()
        app._upsert_table_result = Mock()
        app._log = Mock()
        app._set_ip_active = Mock()
        app._append_runner_log = Mock()
        app._handle_runner_speed_result = Mock()
        app._handle_update_check_result = Mock()
        app._handle_update_check_error = Mock()
        app.after = Mock()
        app.events.put(("result", 1, 2, {"ip": "1.1.1.1", "ok": False, "error": "x", "speed_debug": "d"}, True))
        app.events.put(("active_start", "1.1.1.1"))
        app.events.put(("active_done", "1.1.1.1"))
        app.events.put(("runner_log", "line"))
        app.events.put(("runner_speed_result", "download", {"ok": True}))
        app.events.put(("update_check_result", {"available": False}))
        app.events.put(("update_check_error", "offline"))

        app._drain_events()

        self.assertEqual(app.progress.value, 50)
        self.assertEqual(app._log.call_count, 2)
        self.assertEqual(app._set_ip_active.call_count, 2)
        app._append_runner_log.assert_called_once_with("line")
        app._handle_runner_speed_result.assert_called_once()
        app._handle_update_check_result.assert_called_once_with({"available": False})
        app._handle_update_check_error.assert_called_once_with("offline")
        app.after.assert_called_once_with(100, app._drain_events)

    def test_drain_events_logs_partial_speed_warning(self):
        app = self.make_worker()
        app.progress = FakeProgress()
        app.status_var = FakeVar()
        app._upsert_table_result = Mock()
        app._log = Mock()
        app.after = Mock()
        app.events.put(
            (
                "result",
                1,
                1,
                {
                    "ip": "1.1.1.1",
                    "ok": True,
                    "ms": 20,
                    "upload_mbps": 0.42,
                    "speed_warnings": ["upload partial: confirmed 262144 bytes"],
                },
                True,
            )
        )

        app._drain_events()

        self.assertEqual(app._log.call_count, 2)
        self.assertIn("WARN 1.1.1.1 upload partial", app._log.call_args_list[1].args[0])


class GuiRunnerExtendedTests(unittest.TestCase):
    def make_runner(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.profile = object()
        app.events = queue.Queue()
        app.runner_ip_var = FakeVar("1.1.1.1")
        app.runner_port_var = FakeVar("1080")
        app.runner_share_var = FakeVar(False)
        app.fragment_enabled_var = FakeVar(False)
        app.runner_system_proxy_mode_var = FakeVar(gui_runner.SYSTEM_PROXY_DO_NOT_TOUCH)
        app.runner_process = None
        app.runner_temp_dir = None
        app.runner_system_proxy_applied = False
        app.runner_start_button = FakeButton()
        app.runner_stop_button = FakeButton()
        app.runner_status_var = FakeVar()
        app.runner_log = FakeLog()
        app.log = FakeLog()
        app.current_log_path = None
        app._set_runner_config_state = Mock()
        app._set_runner_speed_state = Mock()
        app._start_runner_log_threads = Mock()
        app._track_process = Mock()
        app._untrack_process = Mock()
        return app

    def test_runner_settings_validation(self):
        app = self.make_runner()
        app.runner_speed_size_var = FakeVar("2")
        app.runner_speed_timeout_var = FakeVar("9000")
        self.assertEqual(app._runner_port(), 1080)
        self.assertEqual(app._runner_fragment_settings(), {})
        self.assertEqual(app._runner_speed_settings(), (2 * 1024 * 1024, 9000))

        app.runner_port_var.set("70000")
        app.runner_speed_timeout_var.set("0")
        with patch.object(gui_runner.messagebox, "showerror") as showerror:
            self.assertIsNone(app._runner_port())
            self.assertIsNone(app._runner_speed_settings())
        self.assertEqual(showerror.call_count, 2)

    def test_current_xray_runner_config_includes_enabled_fragment(self):
        app = self.make_runner()
        profile = SimpleNamespace(name="demo.config")
        app._selected_profile = Mock(return_value=profile)
        app.fragment_enabled_var.set(True)
        app.fragment_packets_var = FakeVar("tlshello")
        app.fragment_interval_var = FakeVar("1-2")
        app.fragment_length_var = FakeVar("5-10")
        expected_config = {"inbounds": [], "outbounds": []}

        with patch.object(gui_runner, "make_xray_runner_config", return_value=expected_config) as make_config:
            result = app._current_xray_runner_config()

        fragment = {"packets": "tlshello", "interval": "1-2", "length": "5-10"}
        self.assertEqual(result["config"], expected_config)
        self.assertEqual(result["fragment"], fragment)
        make_config.assert_called_once_with("1.1.1.1", 1080, "127.0.0.1", profile, fragment)

    def test_export_xray_config_writes_complete_json(self):
        app = self.make_runner()
        app._append_runner_log = Mock()
        config = {"inbounds": [{"port": 1080}], "outbounds": [{"tag": "fragment"}]}
        app._current_xray_runner_config = Mock(
            return_value={
                "ip": "1.1.1.1",
                "profile": SimpleNamespace(name="demo.config"),
                "config": config,
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "runner.json")
            with patch.object(gui_runner.filedialog, "asksaveasfilename", return_value=path), patch.object(
                gui_runner.messagebox, "showinfo"
            ) as showinfo:
                app.export_xray_config()
            with open(path, "r", encoding="utf-8") as config_file:
                saved = json.load(config_file)

        self.assertEqual(saved, config)
        app._append_runner_log.assert_called_once()
        showinfo.assert_called_once()

    def test_export_xray_config_does_nothing_when_dialog_is_cancelled(self):
        app = self.make_runner()
        app._current_xray_runner_config = Mock(
            return_value={
                "ip": "1.1.1.1",
                "profile": SimpleNamespace(name="demo.config"),
                "config": {},
            }
        )
        with patch.object(gui_runner.filedialog, "asksaveasfilename", return_value=""), patch(
            "builtins.open"
        ) as open_file:
            app.export_xray_config()
        open_file.assert_not_called()

    def test_start_xray_runner_cleans_up_after_process_failure(self):
        app = self.make_runner()
        app._selected_profile = Mock(return_value=app.profile)
        temp_dir = MagicMock()
        temp_dir.name = os.getcwd()
        with patch.object(gui_runner, "make_xray_runner_config", return_value={}), patch.object(
            gui_runner.tempfile, "TemporaryDirectory", return_value=temp_dir
        ), patch("builtins.open", MagicMock()), patch.object(
            gui_runner.subprocess, "Popen", side_effect=OSError("cannot start")
        ), patch.object(gui_runner.messagebox, "showerror") as showerror:
            app.start_xray_runner()

        temp_dir.cleanup.assert_called_once()
        self.assertIsNone(app.runner_process)
        showerror.assert_called_once()

    def test_start_and_stop_xray_runner_manage_process_and_ui(self):
        app = self.make_runner()
        app._selected_profile = Mock(return_value=app.profile)
        app._apply_runner_system_proxy_mode = Mock()
        proc = Mock()
        proc.poll.return_value = None
        temp_dir = MagicMock()
        temp_dir.name = os.getcwd()
        with patch.object(gui_runner, "make_xray_runner_config", return_value={}), patch.object(
            gui_runner.tempfile, "TemporaryDirectory", return_value=temp_dir
        ), patch("builtins.open", MagicMock()), patch.object(gui_runner, "json"), patch.object(
            gui_runner.subprocess, "Popen", return_value=proc
        ):
            app.start_xray_runner()

        self.assertIs(app.runner_process, proc)
        self.assertEqual(app.runner_start_button.state, "disabled")
        app._start_runner_log_threads.assert_called_once_with(proc)

        app._clear_runner_system_proxy_if_needed = Mock()
        app.stop_xray_runner()
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=1)
        temp_dir.cleanup.assert_called_once()
        self.assertIsNone(app.runner_process)
        self.assertEqual(app.runner_stop_button.state, "disabled")

    def test_runner_speed_worker_reports_exceptions(self):
        app = self.make_runner()
        with patch.object(gui_runner, "test_ip", side_effect=RuntimeError("failed")):
            app._runner_speed_worker("1.1.1.1", app.profile, "upload", 1024, 7000, {})
        event = app.events.get_nowait()
        self.assertEqual(event[0:2], ("runner_speed_result", "upload"))
        self.assertFalse(event[2]["ok"])
        self.assertIn("RuntimeError", event[2]["error"])

    def test_system_proxy_modes_are_applied_and_cleared(self):
        app = self.make_runner()
        with patch.object(gui_runner.system_proxy, "set_socks_proxy", return_value="set"), patch.object(
            gui_runner.system_proxy, "clear_proxy", return_value="cleared"
        ) as clear:
            app.runner_system_proxy_mode_var.set(gui_runner.SYSTEM_PROXY_SET)
            app._apply_runner_system_proxy_mode(1080)
            self.assertTrue(app.runner_system_proxy_applied)
            app._clear_runner_system_proxy_if_needed()
        clear.assert_called_once()
        self.assertFalse(app.runner_system_proxy_applied)


if __name__ == "__main__":
    unittest.main()
