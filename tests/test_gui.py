import ipaddress
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from proxy_tester import gui, gui_config, gui_runner, gui_table
from proxy_tester.version import APP_TITLE
from proxy_tester.settings import RunnerSettings


class FakeTable:
    def __init__(self, selected, values_by_item):
        self.selected = selected
        self.values_by_item = values_by_item

    def selection(self):
        return self.selected

    def item(self, item, option):
        if option != "values":
            return ()
        return self.values_by_item[item]


class FakeRefreshTable(FakeTable):
    def get_children(self):
        return []

    def delete(self, item):
        pass


class FakeHeadingTable(FakeRefreshTable):
    def __init__(self):
        super().__init__([], {})
        self.headings = {}

    def heading(self, column, **kwargs):
        self.headings.setdefault(column, {}).update(kwargs)


class FakeRenderTable(FakeRefreshTable):
    def __init__(self):
        super().__init__([], {})
        self.inserted = []
        self.items = {}
        self.deleted = []
        self.moved = []
        self.selected_items = []
        self.focused_item = None
        self.seen_item = None

    def insert(self, parent, index, values, tags=()):
        item = f"item-{len(self.inserted) + 1}"
        row = {"parent": parent, "index": index, "values": values, "tags": tags}
        self.inserted.append(row)
        self.items[item] = row
        return item

    def item(self, item, option=None, **kwargs):
        if kwargs:
            self.items[item].update(kwargs)
            return None
        if option:
            return self.items[item].get(option)
        return self.items[item]

    def delete(self, item):
        self.deleted.append(item)
        self.items.pop(item, None)

    def get_children(self):
        return list(self.items)

    def move(self, item, parent, index):
        self.moved.append((item, parent, index))

    def selection_set(self, items):
        self.selected_items = list(items) if isinstance(items, (list, tuple)) else [items]

    def focus(self, item):
        self.focused_item = item

    def see(self, item):
        self.seen_item = item


class FakeLog:
    def __init__(self):
        self.lines = []

    def delete(self, start, end):
        pass

    def insert(self, index, message):
        self.lines.append(message)

    def see(self, index):
        pass


class FakeProgress:
    def __setitem__(self, key, value):
        setattr(self, key, value)


class FakeTempDir:
    def __init__(self):
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True


class FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]


class FakeCombo:
    def __init__(self):
        self.values = None
        self.state = None

    def __setitem__(self, key, value):
        if key == "values":
            self.values = value

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def current(self, index):
        self.current_index = index


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class GuiTests(unittest.TestCase):
    def test_gui_module_exposes_app_class_and_main(self):
        self.assertTrue(hasattr(gui, "ProxyTesterGui"))
        self.assertTrue(callable(gui.main))
        self.assertEqual(APP_TITLE, "Cloudflare Proxy Scanner")

    def test_window_height_has_budget_for_left_panel_controls(self):
        self.assertGreaterEqual(gui.WINDOW_HEIGHT, gui.LEFT_PANEL_MIN_HEIGHT)

    def test_left_panel_width_has_budget_for_controls(self):
        self.assertGreaterEqual(gui.LEFT_PANEL_WIDTH, gui.LEFT_PANEL_MIN_WIDTH)

    def test_table_sort_value_sorts_ip_addresses_naturally(self):
        rows = [{"ip": "104.16.1.10"}, {"ip": "104.16.1.2"}]

        sorted_rows = sorted(rows, key=lambda row: gui.table_sort_value(row, "ip"))

        self.assertEqual([row["ip"] for row in sorted_rows], ["104.16.1.2", "104.16.1.10"])

    def test_table_sort_value_uses_numeric_values(self):
        rows = [
            {"ms": 200, "download_mbps": 5.5, "upload_mbps": 2.0},
            {"ms": 50, "download_mbps": 20.0, "upload_mbps": 1.0},
        ]

        self.assertEqual(sorted(rows, key=lambda row: gui.table_sort_value(row, "ping"))[0]["ms"], 50)
        self.assertEqual(sorted(rows, key=lambda row: gui.table_sort_value(row, "download"))[-1]["download_mbps"], 20.0)

    def test_table_values_display_failed_float_metrics_as_minus_one(self):
        app = object.__new__(gui.ProxyTesterGui)

        values = app._table_values(
            {"ip": "104.16.1.1", "ms": -1.0, "download_mbps": "-1.0", "upload_mbps": -1.00}
        )

        self.assertEqual(values, (-1, "104.16.1.1", -1, -1))

    def test_active_sort_heading_shows_direction_and_updates_on_click(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.table = FakeHeadingTable()
        app.passed_results = []
        app.table_items_by_ip = {}
        app.sort_column = "ping"
        app.sort_reverse = False

        app._update_sort_headings()

        self.assertEqual(app.table.headings["ping"]["text"], "▶ Latency (ms) ▲")
        self.assertEqual(app.table.headings["ip"]["text"], "IP")

        app._sort_by_column("ping")
        self.assertEqual(app.table.headings["ping"]["text"], "▶ Latency (ms) ▼")

        app._sort_by_column("ip")
        self.assertEqual(app.table.headings["ping"]["text"], "Latency (ms)")
        self.assertEqual(app.table.headings["ip"]["text"], "▶ IP ▲")

    def test_merge_rows_by_ip_preserves_existing_untested_speed_columns(self):
        rows = [
            {"ip": "104.16.1.1", "ms": 100, "download_mbps": 5, "upload_mbps": 3},
            {"ip": "104.16.1.2", "ms": 120, "download_mbps": 6, "upload_mbps": 4},
        ]
        updates = [{"ip": "104.16.1.1", "ms": 90, "download_mbps": 10}]

        merged = gui.merge_rows_by_ip(rows, updates)

        self.assertEqual(merged[0]["download_mbps"], 10)
        self.assertEqual(merged[0]["upload_mbps"], 3)
        self.assertEqual(merged[1]["upload_mbps"], 4)

    def test_speed_normalization_keeps_ping_for_failed_speed_test(self):
        app = object.__new__(gui.ProxyTesterGui)

        result = app._normalize_speed_result(
            {"ip": "104.16.1.1", "ok": False, "ms": 123, "error": "HTTP 429"},
            "download",
        )

        self.assertEqual(result["ms"], 123)
        self.assertEqual(result["download_mbps"], -1)

    def test_speed_normalization_converts_float_failure_sentinels(self):
        app = object.__new__(gui.ProxyTesterGui)

        result = app._normalize_speed_result(
            {"ip": "104.16.1.1", "ok": False, "ms": -1.0, "download_mbps": "-1.0"},
            "download",
        )

        self.assertEqual(result["ms"], -1)
        self.assertEqual(result["download_mbps"], -1)
        self.assertIsInstance(result["download_mbps"], int)

    def test_selected_table_ips_returns_unique_ips_in_selection_order(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.table = FakeTable(
            ["a", "b", "c"],
            {
                "a": (100, "104.16.1.1", "", ""),
                "b": (80, "104.16.1.2", "", ""),
                "c": (90, "104.16.1.1", "", ""),
            },
        )

        self.assertEqual(app._selected_table_ips(), ["104.16.1.1", "104.16.1.2"])

    def test_show_selected_config_qr_uses_selected_ip_and_profile(self):
        app = object.__new__(gui.ProxyTesterGui)
        profile = Mock(protocol="trojan")
        app._selected_single_ip = Mock(return_value="104.16.1.1")
        app._selected_profile = Mock(return_value=profile)

        with patch.object(gui_table, "make_proxy_url", return_value="trojan://generated") as make_url:
            with patch.object(gui_table, "open_config_qr") as open_qr:
                app.show_selected_config_qr()

        make_url.assert_called_once_with("104.16.1.1", "cf-104.16.1.1", profile)
        open_qr.assert_called_once_with(app, "trojan://generated", "trojan", "104.16.1.1")

    def test_show_selected_config_qr_requires_one_selected_ip(self):
        app = object.__new__(gui.ProxyTesterGui)
        app._selected_single_ip = Mock(return_value=None)
        app._selected_profile = Mock()

        with patch.object(gui_table, "open_config_qr") as open_qr:
            app.show_selected_config_qr()

        app._selected_profile.assert_not_called()
        open_qr.assert_not_called()

    def test_make_scan_ips_can_scan_all_cloudflare_ips(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.mode_var = FakeVar()
        app.mode_var.set("all_full")
        app.count_var = FakeVar()
        app.count_var.set("not-used")

        with patch.object(gui.cloudflare, "all_candidates", return_value=iter(["104.16.1.1", "104.16.1.2"])):
            ips, source = app._make_scan_ips()

        self.assertEqual(ips, ["104.16.1.1", "104.16.1.2"])
        self.assertEqual(source, "all Cloudflare IPs")

    def test_range_controls_follow_full_and_custom_modes(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.mode_var = FakeVar()
        app.mode_var.set("all_full")
        app.range_combo = FakeCombo()
        app.count_entry = FakeButton()

        app._sync_range_state()

        self.assertEqual(app.range_combo.state, "disabled")
        self.assertEqual(app.count_entry.state, "disabled")

        app.mode_var.set("range_full")
        app._sync_range_state()
        self.assertEqual(app.range_combo.state, "readonly")
        self.assertEqual(app.count_entry.state, "disabled")

        app.mode_var.set("custom")
        app._sync_range_state()
        self.assertEqual(app.range_combo.state, "disabled")
        self.assertEqual(app.count_entry.state, "normal")

    def test_custom_range_summary_uses_current_network_count(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.custom_networks = [object(), object()]
        app.custom_range_summary_var = FakeVar()

        app._refresh_custom_range_summary()

        self.assertEqual(app.custom_range_summary_var.value, "2 custom ranges")

    def test_custom_ranges_are_added_to_single_range_selector(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.cloudflare_networks = [ipaddress.ip_network("104.16.0.0/30")]
        app.custom_networks = [ipaddress.ip_network("192.0.2.0/30")]
        app.range_var = FakeVar("")
        app.range_combo = FakeCombo()

        app._refresh_range_options()

        self.assertEqual(len(app.ranges_by_label), 2)
        self.assertTrue(any(label.startswith("Custom: 192.0.2.0/30") for label in app.ranges_by_label))
        self.assertEqual(app.range_combo.current_index, 0)

    def test_safe_config_filename_uses_config_extension(self):
        app = object.__new__(gui.ProxyTesterGui)

        self.assertEqual(app._safe_config_filename("my config.txt"), "my-config.config")
        self.assertEqual(app._safe_config_filename("ready.config"), "ready.config")
        self.assertEqual(app._safe_config_filename(""), "config.config")

    def test_contains_supported_config_accepts_config_after_comment(self):
        app = object.__new__(gui.ProxyTesterGui)

        self.assertTrue(app._contains_supported_config("# primary\nvmess://encoded"))
        self.assertFalse(app._contains_supported_config("https://example.com"))

    def test_next_available_config_filename_adds_incrementing_suffix(self):
        app = object.__new__(gui.ProxyTesterGui)
        with patch.object(gui_config, "CONFIG_DIR", os.getcwd()), patch.object(
            gui_config.os.path,
            "exists",
            side_effect=lambda path: os.path.basename(path) in {"new-config.config", "new-config-2.config"},
        ):
            name = app._next_available_config_filename("new-config.config")

        self.assertEqual(name, "new-config-3.config")

    def test_create_config_file_keeps_existing_configs(self):
        app = object.__new__(gui.ProxyTesterGui)
        with tempfile.TemporaryDirectory() as config_dir, patch.object(gui_config, "CONFIG_DIR", config_dir), patch.object(
            gui_config, "parse_proxy_config"
        ):
            first_path = app._create_config_file("first.config", "vless://first")
            second_path = app._create_config_file("second.config", "trojan://second")
            with self.assertRaises(FileExistsError):
                app._create_config_file("first.config", "vmess://replacement")

            with open(first_path, encoding="utf-8") as first_file:
                self.assertEqual(first_file.read(), "vless://first\n")
            with open(second_path, encoding="utf-8") as second_file:
                self.assertEqual(second_file.read(), "trojan://second\n")

    def test_create_config_file_removes_only_new_invalid_file(self):
        app = object.__new__(gui.ProxyTesterGui)
        with tempfile.TemporaryDirectory() as config_dir, patch.object(gui_config, "CONFIG_DIR", config_dir), patch.object(
            gui_config, "parse_proxy_config", side_effect=ValueError("invalid")
        ):
            with self.assertRaisesRegex(ValueError, "invalid"):
                app._create_config_file("invalid.config", "vless://invalid")

            self.assertFalse(os.path.exists(os.path.join(config_dir, "invalid.config")))

    def test_replace_config_file_validates_then_renames(self):
        app = object.__new__(gui.ProxyTesterGui)
        with tempfile.TemporaryDirectory() as config_dir, patch.object(gui_config, "CONFIG_DIR", config_dir), patch.object(
            gui_config, "parse_proxy_config"
        ) as parse:
            source = os.path.join(config_dir, "old.config")
            with open(source, "w", encoding="utf-8") as config_file:
                config_file.write("vless://old\n")

            target = app._replace_config_file(source, "renamed.config", "trojan://new")

            self.assertFalse(os.path.exists(source))
            with open(target, "r", encoding="utf-8") as config_file:
                self.assertEqual(config_file.read(), "trojan://new\n")
            parse.assert_called_once()

    def test_replace_config_file_keeps_original_when_edit_is_invalid(self):
        app = object.__new__(gui.ProxyTesterGui)
        with tempfile.TemporaryDirectory() as config_dir, patch.object(gui_config, "CONFIG_DIR", config_dir), patch.object(
            gui_config, "parse_proxy_config", side_effect=ValueError("invalid")
        ):
            source = os.path.join(config_dir, "working.config")
            with open(source, "w", encoding="utf-8") as config_file:
                config_file.write("vless://working\n")

            with self.assertRaisesRegex(ValueError, "invalid"):
                app._replace_config_file(source, "working.config", "vless://broken")

            with open(source, "r", encoding="utf-8") as config_file:
                self.assertEqual(config_file.read(), "vless://working\n")
            self.assertEqual(os.listdir(config_dir), ["working.config"])

    def test_replace_config_file_refuses_duplicate_name(self):
        app = object.__new__(gui.ProxyTesterGui)
        with tempfile.TemporaryDirectory() as config_dir, patch.object(gui_config, "CONFIG_DIR", config_dir):
            source = os.path.join(config_dir, "first.config")
            target = os.path.join(config_dir, "second.config")
            for path in (source, target):
                with open(path, "w", encoding="utf-8") as config_file:
                    config_file.write("vless://original\n")

            with self.assertRaises(FileExistsError):
                app._replace_config_file(source, "second.config", "vless://replacement")

            self.assertTrue(os.path.exists(source))

    def test_speed_fragment_settings_uses_configured_values(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.speed_fragment_enabled_var = FakeVar(True)
        app.speed_fragment_packets_var = FakeVar("1-3")
        app.speed_fragment_interval_var = FakeVar("1-1")
        app.speed_fragment_length_var = FakeVar("1-7")

        self.assertEqual(
            app._speed_fragment_settings(),
            {"packets": "1-3", "interval": "1-1", "length": "1-7"},
        )

    def test_speed_fragment_settings_returns_empty_when_disabled(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.speed_fragment_enabled_var = FakeVar(False)

        self.assertEqual(app._speed_fragment_settings(), {})

    def test_sync_speed_fragment_state_disables_fragment_entries(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.speed_fragment_enabled_var = FakeVar(False)
        app.speed_fragment_packets_entry = FakeButton()
        app.speed_fragment_interval_entry = FakeButton()
        app.speed_fragment_length_entry = FakeButton()

        app._sync_speed_fragment_state()

        self.assertEqual(app.speed_fragment_packets_entry.state, "disabled")
        self.assertEqual(app.speed_fragment_interval_entry.state, "disabled")
        self.assertEqual(app.speed_fragment_length_entry.state, "disabled")

    def test_selected_speed_test_uses_only_selected_ips(self):
        app = object.__new__(gui.ProxyTesterGui)
        profile = object()
        app.speed_mode_var = Mock(get=Mock(return_value="both"))
        app.passed_results = [{"ip": "104.16.1.1"}, {"ip": "104.16.1.2"}, {"ip": "104.16.1.3"}]
        app._selected_profile = Mock(return_value=profile)
        app._speed_settings = Mock(return_value=(1024, 5000))
        app._speed_fragment_settings = Mock(return_value={"packets": "1-3"})
        app._selected_table_ips = Mock(return_value=["104.16.1.1", "104.16.1.3"])
        app._start_worker = Mock()

        app.start_speed_test_for_selected("upload")

        app._start_worker.assert_called_once_with(
            ["104.16.1.1", "104.16.1.3"],
            "selected table IPs",
            profile,
            speed_mode="upload",
            initial_results=app.passed_results,
            speed_test_bytes=1024,
            speed_timeout_ms=5000,
            speed_fragment={"packets": "1-3"},
            restore_selection_ips=["104.16.1.1", "104.16.1.3"],
            reset_sort=False,
        )

    def test_clear_results_can_preserve_current_sort(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.passed_results = []
        app.sort_column = "upload"
        app.sort_reverse = True
        app.table = FakeRefreshTable([], {})
        app.progress = FakeProgress()
        app.log = FakeLog()
        app._refresh_passed_table = Mock()

        app._clear_results(initial_results=[{"ip": "104.16.1.1"}], reset_sort=False)

        self.assertEqual(app.sort_column, "upload")
        self.assertTrue(app.sort_reverse)
        self.assertEqual(app.passed_results, [{"ip": "104.16.1.1"}])

    def test_upsert_table_result_preserves_existing_speed_columns(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.sort_column = "ping"
        app.sort_reverse = False
        app.passed_results = [
            {
                "ip": "104.16.1.1",
                "ok": True,
                "ms": 100,
                "download_mbps": 12.5,
                "upload_mbps": 3.5,
            }
        ]
        app.table = FakeRenderTable()
        app.table_items_by_ip = {"104.16.1.1": "item-1"}
        app.table.items["item-1"] = {"values": (100, "104.16.1.1", 12.5, 3.5), "tags": ()}
        app._move_table_item_to_sorted_position = Mock()

        app._upsert_table_result({"ip": "104.16.1.1", "ok": True, "ms": 90, "upload_mbps": 4.25})

        self.assertEqual(app.passed_results[0]["download_mbps"], 12.5)
        self.assertEqual(app.passed_results[0]["upload_mbps"], 4.25)
        self.assertEqual(app.passed_results[0]["ms"], 90)
        self.assertEqual(app.table.items["item-1"]["values"], (90, "104.16.1.1", 12.5, 4.25))

    def test_set_ip_active_marks_row_for_highlight(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.active_test_ips = set()
        app.passed_results = [{"ip": "104.16.1.1", "ms": 100}]
        app.table = FakeRenderTable()
        app.table_items_by_ip = {"104.16.1.1": "item-1"}
        app.table.items["item-1"] = {"values": (100, "104.16.1.1", "", ""), "tags": ()}

        app._set_ip_active("104.16.1.1", True)

        self.assertIn("104.16.1.1", app.active_test_ips)
        self.assertTrue(app.passed_results[0]["active"])
        self.assertEqual(app.table.items["item-1"]["tags"], ("active",))

    def test_refresh_passed_table_applies_active_tag(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.table = FakeRenderTable()
        app.passed_results = [{"ip": "104.16.1.1", "ms": 100, "active": True}]
        app._sorted_results = Mock(return_value=app.passed_results)

        app._refresh_passed_table()

        self.assertEqual(app.table.inserted[0]["tags"], ("active",))
        self.assertEqual(app.table_items_by_ip["104.16.1.1"], "item-1")

    def test_restore_table_selection_by_ips_selects_and_scrolls_single_row(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.table = FakeRenderTable()
        app.table_items_by_ip = {"104.16.1.1": "item-1"}

        app._restore_table_selection_by_ips(["104.16.1.1"])

        self.assertEqual(app.table.selected_items, ["item-1"])
        self.assertEqual(app.table.focused_item, "item-1")
        self.assertEqual(app.table.seen_item, "item-1")

    def test_upsert_table_result_inserts_new_row_without_full_refresh(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.sort_column = "ping"
        app.sort_reverse = False
        app.passed_results = []
        app.table = FakeRenderTable()
        app.table_items_by_ip = {}
        app._move_table_item_to_sorted_position = Mock()

        app._upsert_table_result({"ip": "104.16.1.1", "ok": True, "ms": 100})

        self.assertEqual(len(app.table.inserted), 1)
        self.assertEqual(app.table.inserted[0]["values"], (100, "104.16.1.1", "", ""))
        self.assertIn("104.16.1.1", app.table_items_by_ip)

    def test_load_configs_disables_actions_when_no_config_exists(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.config_combo = FakeCombo()
        app.config_var = FakeVar()
        app.status_var = FakeVar()
        app.start_button = FakeButton()
        app.speed_button = FakeButton()
        app.proxy_config_button = FakeButton()
        app.runner_start_button = FakeButton()
        app.runner_export_button = FakeButton()
        app.runner_process = None
        app._set_runner_speed_state = Mock()

        with patch.object(gui_config, "config_files", return_value=[]):
            app._load_configs()

        self.assertIsNone(app.profile)
        self.assertEqual(app.config_combo.values, [])
        self.assertEqual(app.config_var.value, "")
        self.assertIn("No proxy configuration found", app.status_var.value)
        self.assertEqual(app.start_button.state, "disabled")
        self.assertEqual(app.speed_button.state, "disabled")
        self.assertEqual(app.proxy_config_button.state, "disabled")
        self.assertEqual(app.runner_start_button.state, "disabled")
        self.assertEqual(app.runner_export_button.state, "disabled")

    def test_set_running_disables_output_selector_and_refresh_button(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.profile = object()
        app.start_button = FakeButton()
        app.speed_button = FakeButton()
        app.proxy_config_button = FakeButton()
        app.remove_failed_button = FakeButton()
        app.output_combo = FakeCombo()
        app.refresh_outputs_button = FakeButton()
        app.stop_scan_button = FakeButton()
        app.stop_speed_button = FakeButton()

        app._set_running(True, operation="scan")

        self.assertEqual(app.output_combo.state, "disabled")
        self.assertEqual(app.refresh_outputs_button.state, "disabled")
        self.assertEqual(app.stop_scan_button.state, "normal")

        app._set_running(False)

        self.assertEqual(app.output_combo.state, "readonly")
        self.assertEqual(app.refresh_outputs_button.state, "normal")

    def test_select_output_path_loads_saved_scan_result(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.output_var = FakeVar()
        app.output_paths_by_name = {}
        app.load_selected_output_into_table = Mock()
        output_path = os.path.join("output", "scan.csv")

        def load_outputs():
            app.output_paths_by_name = {"scan.csv": output_path}

        app._load_outputs = load_outputs

        app._select_output_path(output_path)

        self.assertEqual(app.output_var.value, "scan.csv")
        app.load_selected_output_into_table.assert_called_once()

    def test_has_failed_metric_checks_ping_download_and_upload(self):
        app = object.__new__(gui.ProxyTesterGui)

        self.assertTrue(app._has_failed_metric({"ms": -1}))
        self.assertTrue(app._has_failed_metric({"download_mbps": -1}))
        self.assertTrue(app._has_failed_metric({"upload_mbps": "-1"}))
        self.assertFalse(app._has_failed_metric({"ms": 10, "download_mbps": "", "upload_mbps": ""}))

    def test_remove_failed_rows_removes_any_row_with_negative_one_metric(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.passed_results = [
            {"ip": "ok", "ms": 10, "download_mbps": 2, "upload_mbps": 1},
            {"ip": "bad-ping", "ms": -1, "download_mbps": 2, "upload_mbps": 1},
            {"ip": "bad-down", "ms": 10, "download_mbps": -1, "upload_mbps": 1},
            {"ip": "bad-up", "ms": 10, "download_mbps": 2, "upload_mbps": -1, "active": True},
        ]
        app.active_test_ips = {"bad-up"}
        app.status_var = FakeVar()
        app.current_log_path = None
        app.log = FakeLog()
        app._select_output_path = Mock()

        with patch.object(gui_config, "save_scan_results", return_value=("filtered.csv", "latest.csv")) as save:
            app.remove_failed_rows()

        self.assertEqual(app.passed_results, [{"ip": "ok", "ms": 10, "download_mbps": 2, "upload_mbps": 1}])
        self.assertEqual(app.active_test_ips, set())
        self.assertIn("Removed 3 failed results", app.status_var.value)
        save.assert_called_once_with(app.passed_results, prefix="filtered-cloudflare-proxy-ips")
        app._select_output_path.assert_called_once_with("filtered.csv")

    def test_should_auto_speed_after_scan_requires_completed_scan_with_passed_ips(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.auto_speed_after_scan_var = Mock(get=Mock(return_value=True))

        self.assertTrue(app._should_auto_speed_after_scan(False, False, 2))
        self.assertFalse(app._should_auto_speed_after_scan(True, False, 2))
        self.assertFalse(app._should_auto_speed_after_scan(False, True, 2))
        self.assertFalse(app._should_auto_speed_after_scan(False, False, 0))

    def test_done_event_starts_auto_speed_test_after_completed_scan(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.auto_speed_after_scan_var = Mock(get=Mock(return_value=True))
        app.status_var = FakeVar()
        app.current_log_path = None
        app.log = FakeLog()
        app._set_running = Mock()
        app._select_output_path = Mock()
        app.start_speed_test = Mock()

        app._handle_done_event(2, "scan.csv", "latest.csv", False, 10, 10, False)

        app._select_output_path.assert_called_once_with("scan.csv")
        app.start_speed_test.assert_called_once()

    def test_done_event_restores_selected_speed_test_row(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.auto_speed_after_scan_var = Mock(get=Mock(return_value=False))
        app.status_var = FakeVar()
        app.current_log_path = None
        app.log = FakeLog()
        app._set_running = Mock()
        app._select_output_path = Mock()
        app._restore_table_selection_by_ips = Mock()

        app._handle_done_event(
            1,
            "speed.csv",
            "latest.csv",
            False,
            1,
            1,
            True,
            ["104.16.1.1"],
        )

        app._restore_table_selection_by_ips.assert_called_once_with(["104.16.1.1"])

    def test_done_event_does_not_auto_speed_test_after_stop(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.auto_speed_after_scan_var = Mock(get=Mock(return_value=True))
        app.status_var = FakeVar()
        app.current_log_path = None
        app.log = FakeLog()
        app._set_running = Mock()
        app._select_output_path = Mock()
        app.start_speed_test = Mock()

        app._handle_done_event(2, "scan.csv", "latest.csv", True, 5, 10, False)

        app.start_speed_test.assert_not_called()

    def test_runner_fragment_settings_uses_configured_values(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.fragment_enabled_var = FakeVar(True)
        app.fragment_packets_var = FakeVar("1-3")
        app.fragment_interval_var = FakeVar("1-1")
        app.fragment_length_var = FakeVar("1-7")

        self.assertEqual(
            app._runner_fragment_settings(),
            {"packets": "1-3", "interval": "1-1", "length": "1-7"},
        )

    def test_runner_fragment_settings_returns_empty_when_disabled(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.fragment_enabled_var = FakeVar(False)

        self.assertEqual(app._runner_fragment_settings(), {})

    def test_sync_fragment_state_disables_fragment_entries(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.fragment_enabled_var = FakeVar(False)
        app.runner_process = None
        app.fragment_packets_entry = FakeButton()
        app.fragment_interval_entry = FakeButton()
        app.fragment_length_entry = FakeButton()

        app._sync_fragment_state()

        self.assertEqual(app.fragment_packets_entry.state, "disabled")
        self.assertEqual(app.fragment_interval_entry.state, "disabled")
        self.assertEqual(app.fragment_length_entry.state, "disabled")

    def test_set_runner_config_state_disables_runner_inputs_while_running(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_process = None
        app.fragment_enabled_var = FakeVar(True)
        app.runner_ip_entry = FakeButton()
        app.runner_port_entry = FakeButton()
        app.runner_share_check = FakeButton()
        app.runner_system_proxy_combo = FakeButton()
        app.fragment_enabled_check = FakeButton()
        app.fragment_packets_entry = FakeButton()
        app.fragment_interval_entry = FakeButton()
        app.fragment_length_entry = FakeButton()

        app._set_runner_config_state(True)

        self.assertEqual(app.runner_ip_entry.state, "disabled")
        self.assertEqual(app.runner_port_entry.state, "disabled")
        self.assertEqual(app.runner_share_check.state, "disabled")
        self.assertEqual(app.runner_system_proxy_combo.state, "disabled")
        self.assertEqual(app.fragment_enabled_check.state, "disabled")
        self.assertEqual(app.fragment_packets_entry.state, "disabled")

    def test_runner_port_validates_range(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_port_var = FakeVar("1080")

        self.assertEqual(app._runner_port(), 1080)

        app.runner_port_var = FakeVar("70000")
        with patch.object(gui_runner.messagebox, "showerror") as showerror:
            self.assertIsNone(app._runner_port())

        showerror.assert_called_once()

    def test_run_selected_ip_with_xray_sets_ip_selects_tab_and_starts(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_ip_var = FakeVar()
        app.runner_tab = object()
        app.notebook = Mock()
        app._selected_single_ip = Mock(return_value="104.16.1.1")
        app.start_xray_runner = Mock()

        app.run_selected_ip_with_xray()

        self.assertEqual(app.runner_ip_var.value, "104.16.1.1")
        app.notebook.select.assert_called_once_with(app.runner_tab)
        app.start_xray_runner.assert_called_once_with("104.16.1.1")

    def test_append_runner_log_writes_to_runner_log_widget(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_log = FakeLog()

        app._append_runner_log("runner started")

        self.assertEqual(app.runner_log.lines, ["runner started\n"])

    def test_handle_runner_exit_resets_buttons_and_cleans_temp_dir(self):
        app = object.__new__(gui.ProxyTesterGui)
        proc = object()
        temp_dir = FakeTempDir()
        app.runner_process = proc
        app.runner_temp_dir = temp_dir
        app.profile = object()
        app.runner_start_button = FakeButton()
        app.runner_stop_button = FakeButton()
        app.runner_status_var = FakeVar()
        app.runner_log = FakeLog()

        app._handle_runner_exit(proc, 0)

        self.assertIsNone(app.runner_process)
        self.assertIsNone(app.runner_temp_dir)
        self.assertTrue(temp_dir.cleaned)
        self.assertEqual(app.runner_start_button.state, "normal")
        self.assertEqual(app.runner_stop_button.state, "disabled")
        self.assertIn("exited with code 0", app.runner_status_var.value)

    def test_handle_runner_speed_result_updates_download_result(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_download_result_var = FakeVar()
        app.runner_upload_result_var = FakeVar()
        app.runner_download_button = FakeButton()
        app.runner_upload_button = FakeButton()
        app.profile = object()
        app.runner_log = FakeLog()

        app._handle_runner_speed_result(
            "download",
            {"ok": True, "download_mbps": 12.5, "speed_warnings": ["upload partial: confirmed bytes"]},
        )

        self.assertEqual(app.runner_download_result_var.value, "12.5 Mbps")
        self.assertEqual(app.runner_upload_result_var.value, None)
        self.assertEqual(app.runner_download_button.state, "normal")
        self.assertIn("Download speed test passed", "".join(app.runner_log.lines))
        self.assertIn("WARNING upload partial", "".join(app.runner_log.lines))

    def test_fragment_scan_variations_have_expected_size(self):
        self.assertEqual(len(gui_runner.FRAGMENT_SCAN_VARIATIONS), 24)
        self.assertEqual(len(gui_runner.UPLOAD_FRAGMENT_SCAN_VARIATIONS), 24)

    def test_fragment_scanner_uses_upload_defaults_for_upload_mode(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_custom_fragments_text = ""
        app.runner_fragment_scan_mode_var = FakeVar("upload")

        variations = app._runner_fragment_scan_variations()

        self.assertEqual(variations, gui_runner.UPLOAD_FRAGMENT_SCAN_VARIATIONS)
        self.assertIsNot(variations, gui_runner.UPLOAD_FRAGMENT_SCAN_VARIATIONS)

    def test_fragment_scanner_uses_download_defaults_for_download_mode(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_custom_fragments_text = ""
        app.runner_fragment_scan_mode_var = FakeVar("download")

        self.assertEqual(app._runner_fragment_scan_variations(), gui_runner.FRAGMENT_SCAN_VARIATIONS)

    def test_custom_fragment_variations_override_mode_defaults(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_custom_fragments_text = "1-2,0-1,100-200"
        app.runner_fragment_scan_mode_var = FakeVar("upload")

        self.assertEqual(
            app._runner_fragment_scan_variations(),
            [{"packets": "1-2", "interval": "0-1", "length": "100-200"}],
        )

    def test_parse_fragment_variations_accepts_lines_and_key_value_format(self):
        text = "1-3,1-1,1-7\npackets=tlshello, interval=1-2, length=5-10"

        variations = gui_runner.parse_fragment_variations(text)

        self.assertEqual(variations[0], {"packets": "1-3", "interval": "1-1", "length": "1-7"})
        self.assertEqual(variations[1], {"packets": "tlshello", "interval": "1-2", "length": "5-10"})

    def test_custom_fragment_placeholder_is_not_saved(self):
        app = object.__new__(gui.ProxyTesterGui)

        self.assertEqual(app._custom_fragment_text_to_save(gui_runner.CUSTOM_FRAGMENT_PLACEHOLDER), "")

    def test_custom_fragment_real_text_is_saved(self):
        app = object.__new__(gui.ProxyTesterGui)

        self.assertEqual(app._custom_fragment_text_to_save("1-3,1-1,1-7"), "1-3,1-1,1-7")

    def test_best_fragment_scan_result_uses_speed_then_latency(self):
        app = object.__new__(gui.ProxyTesterGui)
        rows = [
            {"fragment": {"packets": "a", "interval": "1", "length": "1"}, "value": 10, "result": {"ms": 200}},
            {"fragment": {"packets": "b", "interval": "1", "length": "1"}, "value": 10, "result": {"ms": 100}},
            {"fragment": {"packets": "c", "interval": "1", "length": "1"}, "value": 9, "result": {"ms": 50}},
        ]

        best = app._best_fragment_scan_result(rows)

        self.assertEqual(best["fragment"]["packets"], "b")

    def test_set_runner_speed_state_controls_fragment_scan_button(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.profile = object()
        app.runner_download_button = FakeButton()
        app.runner_upload_button = FakeButton()
        app.runner_fragment_scan_button = FakeButton()
        app.runner_fragment_scan_stop_button = FakeButton()
        app.runner_apply_best_button = FakeButton()
        app.runner_speed_size_entry = FakeButton()
        app.runner_speed_timeout_entry = FakeButton()

        app._set_runner_speed_state(True)

        self.assertEqual(app.runner_download_button.state, "disabled")
        self.assertEqual(app.runner_upload_button.state, "disabled")
        self.assertEqual(app.runner_fragment_scan_button.state, "disabled")
        self.assertEqual(app.runner_fragment_scan_stop_button.state, "normal")
        self.assertEqual(app.runner_apply_best_button.state, "disabled")
        self.assertEqual(app.runner_speed_size_entry.state, "disabled")
        self.assertEqual(app.runner_speed_timeout_entry.state, "disabled")

        app._set_runner_speed_state(False)

        self.assertEqual(app.runner_fragment_scan_stop_button.state, "disabled")
        self.assertEqual(app.runner_apply_best_button.state, "normal")

    def test_runner_speed_settings_uses_runner_specific_values(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_speed_size_var = FakeVar("2")
        app.runner_speed_timeout_var = FakeVar("9000")

        self.assertEqual(app._runner_speed_settings(), (2 * 1024 * 1024, 9000))

    def test_runner_speed_settings_rejects_invalid_values(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_speed_size_var = FakeVar("0")
        app.runner_speed_timeout_var = FakeVar("9000")

        with patch.object(gui_runner.messagebox, "showerror") as showerror:
            self.assertIsNone(app._runner_speed_settings())

        showerror.assert_called_once()

    def test_current_runner_settings_collects_all_persisted_fields(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_ip_var = FakeVar("104.16.1.1")
        app.runner_port_var = FakeVar("2080")
        app.runner_share_var = FakeVar(True)
        app.runner_system_proxy_mode_var = FakeVar(gui_runner.SYSTEM_PROXY_SET)
        app.fragment_enabled_var = FakeVar(True)
        app.fragment_packets_var = FakeVar("tlshello")
        app.fragment_interval_var = FakeVar("2-5")
        app.fragment_length_var = FakeVar("5-15")
        app.runner_speed_size_var = FakeVar("2")
        app.runner_speed_timeout_var = FakeVar("9000")
        app.runner_fragment_scan_mode_var = FakeVar("upload")
        app.runner_custom_fragments_text = "1-3,1-1,1-7"

        self.assertEqual(
            app._current_runner_settings(),
            RunnerSettings(
                ip="104.16.1.1",
                port="2080",
                share=True,
                system_proxy_mode=gui_runner.SYSTEM_PROXY_SET,
                fragment_enabled=False,
                fragment_packets="tlshello",
                fragment_interval="2-5",
                fragment_length="5-15",
                speed_size_mb="2",
                speed_timeout_ms="9000",
                fragment_scan_mode="upload",
                custom_fragments_text="1-3,1-1,1-7",
            ),
        )

    def test_apply_runner_system_proxy_mode_sets_socks_proxy(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_system_proxy_mode_var = FakeVar(gui_runner.SYSTEM_PROXY_SET)
        app.runner_log = FakeLog()

        with patch.object(gui_runner.system_proxy, "set_socks_proxy", return_value="set") as set_proxy:
            app._apply_runner_system_proxy_mode(1080)

        set_proxy.assert_called_once_with(1080)
        self.assertTrue(app.runner_system_proxy_applied)

    def test_apply_runner_system_proxy_mode_clears_proxy(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_system_proxy_mode_var = FakeVar(gui_runner.SYSTEM_PROXY_CLEAR)
        app.runner_log = FakeLog()

        with patch.object(gui_runner.system_proxy, "clear_proxy", return_value="cleared") as clear_proxy:
            app._apply_runner_system_proxy_mode(1080)

        clear_proxy.assert_called_once()
        self.assertFalse(app.runner_system_proxy_applied)

    def test_clear_runner_system_proxy_if_needed_only_clears_when_app_set_it(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_system_proxy_applied = True
        app.runner_log = FakeLog()

        with patch.object(gui_runner.system_proxy, "clear_proxy", return_value="cleared") as clear_proxy:
            app._clear_runner_system_proxy_if_needed()

        clear_proxy.assert_called_once()
        self.assertFalse(app.runner_system_proxy_applied)

    def test_stop_runner_fragment_scan_sets_event_and_kills_processes(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_fragment_scan_stop_event = Mock()
        app._kill_active_processes = Mock()
        app.runner_fragment_scan_result_var = FakeVar()
        app.runner_log = FakeLog()
        app.runner_fragment_scan_stop_button = FakeButton()

        app.stop_runner_fragment_scan()

        app.runner_fragment_scan_stop_event.set.assert_called_once()
        app._kill_active_processes.assert_called_once()
        self.assertIn("Stopping", app.runner_fragment_scan_result_var.value)
        self.assertEqual(app.runner_fragment_scan_stop_button.state, "disabled")

    def test_handle_runner_fragment_scan_result_applies_best_fragment(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.fragment_enabled_var = FakeVar(False)
        app.fragment_packets_var = FakeVar()
        app.fragment_interval_var = FakeVar()
        app.fragment_length_var = FakeVar()
        app.fragment_packets_entry = FakeButton()
        app.fragment_interval_entry = FakeButton()
        app.fragment_length_entry = FakeButton()
        app.runner_process = None
        app.runner_fragment_scan_result_var = FakeVar()
        app.runner_fragment_results = FakeRenderTable()
        app.runner_download_button = FakeButton()
        app.runner_upload_button = FakeButton()
        app.runner_fragment_scan_button = FakeButton()
        app.profile = object()
        app.runner_log = FakeLog()
        fragment = {"packets": "tlshello", "interval": "1-2", "length": "5-10"}
        rows = [{"fragment": fragment, "value": 12.5, "result": {"ok": True, "ms": 90}}]

        with patch.object(gui_runner, "save_fragment_scan_results", return_value="scan.csv") as save_results:
            with patch.object(gui_runner, "save_best_fragment") as save_best:
                app._handle_runner_fragment_scan_result(
                    "download",
                    "104.16.1.1",
                    "demo.config",
                    fragment,
                    12.5,
                    rows,
                )

        self.assertTrue(app.fragment_enabled_var.value)
        self.assertEqual(app.fragment_packets_var.value, "tlshello")
        self.assertEqual(app.fragment_interval_var.value, "1-2")
        self.assertEqual(app.fragment_length_var.value, "5-10")
        self.assertIn("Best download", app.runner_fragment_scan_result_var.value)
        self.assertEqual(app.runner_fragment_scan_button.state, "normal")
        save_results.assert_called_once()
        save_best.assert_called_once_with("104.16.1.1", "demo.config", "download", fragment, 12.5, 90)

    def test_sort_runner_fragment_results_by_speed(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_fragment_results = FakeRenderTable()
        app.runner_fragment_scan_rows = [
            {
                "fragment": {"packets": "a", "interval": "1", "length": "1"},
                "value": 5,
                "result": {"ms": 200},
                "scan_index": 1,
            },
            {
                "fragment": {"packets": "b", "interval": "1", "length": "1"},
                "value": 10,
                "result": {"ms": 100},
                "scan_index": 2,
            },
        ]
        app.runner_fragment_sort_column = "rank"
        app.runner_fragment_sort_reverse = False

        app._sort_runner_fragment_results_by_column("speed")

        self.assertEqual(app.runner_fragment_sort_column, "speed")
        self.assertTrue(app.runner_fragment_sort_reverse)
        self.assertEqual(app.runner_fragment_results.inserted[0]["values"][3], "b")

    def test_sorted_runner_fragment_results_by_latency_ascending(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_fragment_sort_column = "latency"
        app.runner_fragment_sort_reverse = False
        rows = [
            {"fragment": {"packets": "slow", "interval": "1", "length": "1"}, "value": 10, "result": {"ms": 200}},
            {"fragment": {"packets": "fast", "interval": "1", "length": "1"}, "value": 5, "result": {"ms": 80}},
        ]

        sorted_rows = app._sorted_runner_fragment_results(rows)

        self.assertEqual(sorted_rows[0]["fragment"]["packets"], "fast")

    def test_apply_saved_best_fragment_updates_fragment_fields(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_ip_var = FakeVar("104.16.1.1")
        app.runner_fragment_scan_mode_var = FakeVar("upload")
        app.fragment_enabled_var = FakeVar(False)
        app.fragment_packets_var = FakeVar()
        app.fragment_interval_var = FakeVar()
        app.fragment_length_var = FakeVar()
        app.fragment_packets_entry = FakeButton()
        app.fragment_interval_entry = FakeButton()
        app.fragment_length_entry = FakeButton()
        app.runner_process = None
        app.runner_fragment_scan_result_var = FakeVar()
        app.runner_log = FakeLog()
        profile = Mock(name="demo.config")
        profile.name = "demo.config"
        app._selected_profile = Mock(return_value=profile)
        saved = {
            "fragment": {"packets": "1-3", "interval": "1-1", "length": "1-7"},
            "speed_mbps": 5.5,
            "latency_ms": 120,
        }

        with patch.object(gui_runner, "get_best_fragment", return_value=saved):
            app.apply_saved_best_fragment()

        self.assertTrue(app.fragment_enabled_var.value)
        self.assertEqual(app.fragment_packets_var.value, "1-3")
        self.assertIn("Applied saved upload", app.runner_fragment_scan_result_var.value)

    def test_apply_saved_best_fragment_restarts_active_runner(self):
        app = object.__new__(gui.ProxyTesterGui)
        app.runner_ip_var = FakeVar("104.16.1.1")
        app.runner_fragment_scan_mode_var = FakeVar("download")
        app.fragment_enabled_var = FakeVar(False)
        app.fragment_packets_var = FakeVar()
        app.fragment_interval_var = FakeVar()
        app.fragment_length_var = FakeVar()
        app.fragment_packets_entry = FakeButton()
        app.fragment_interval_entry = FakeButton()
        app.fragment_length_entry = FakeButton()
        app.runner_fragment_scan_result_var = FakeVar()
        app.runner_log = FakeLog()
        profile = Mock(name="demo.config")
        profile.name = "demo.config"
        app._selected_profile = Mock(return_value=profile)
        app._runner_is_active = Mock(return_value=True)
        app.stop_xray_runner = Mock()
        app.start_xray_runner = Mock()
        saved = {
            "fragment": {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
            "speed_mbps": 10,
            "latency_ms": 90,
        }

        with patch.object(gui_runner, "get_best_fragment", return_value=saved):
            app.apply_saved_best_fragment()

        app.stop_xray_runner.assert_called_once()
        app.start_xray_runner.assert_called_once_with("104.16.1.1")
        self.assertTrue(app.fragment_enabled_var.value)
        self.assertEqual(app.fragment_packets_var.value, "tlshello")


if __name__ == "__main__":
    unittest.main()
