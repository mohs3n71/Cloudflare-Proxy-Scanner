import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from proxy_tester import app, cli
from proxy_tester.settings import AppSettings
from tests.helpers import sample_profile


class CliTests(unittest.TestCase):
    def test_ask_int_retries_until_valid_value(self):
        with patch("builtins.input", side_effect=["bad", "9", "2"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.ask_int("Number: ", 1, 3), 2)

    def test_ask_int_allows_back_when_enabled(self):
        with patch("builtins.input", return_value="b"):
            self.assertIsNone(cli.ask_int("Number: ", 1, 3, allow_back=True))

    def test_ask_speed_mode_maps_choices(self):
        for choice, expected in (("1", "download"), ("2", "upload"), ("3", "both")):
            with patch("builtins.input", return_value=choice):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.ask_speed_mode(), expected)

    def test_ask_action_returns_selected_number(self):
        with patch("builtins.input", return_value="6"):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.ask_action(AppSettings()), 6)

    def test_ask_concurrency_returns_selected_option(self):
        with patch("builtins.input", return_value="2"):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.ask_concurrency(10), 20)

    def test_ask_concurrency_can_go_back(self):
        with patch("builtins.input", return_value="0"):
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(cli.ask_concurrency(10))

    def test_ask_timeout_ms_returns_custom_value(self):
        with patch("builtins.input", return_value="3500"):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.ask_timeout_ms(2000), 3500)

    def test_ask_settings_updates_concurrency_and_timeout(self):
        settings = AppSettings()
        with patch("builtins.input", side_effect=["1", "2", "2", "3500", "0"]):
            with redirect_stdout(io.StringIO()):
                cli.ask_settings(settings)

        self.assertEqual(settings.concurrency, 20)
        self.assertEqual(settings.timeout_ms, 3500)

    def test_ask_output_file_returns_none_when_no_files(self):
        with patch.object(cli, "output_csv_files", return_value=[]):
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(cli.ask_output_file())

    def test_ask_output_file_returns_selected_file(self):
        files = ["one.csv", "two.csv"]
        with patch.object(cli, "output_csv_files", return_value=files):
            with patch("builtins.input", return_value="2"):
                with patch.object(cli.os.path, "getmtime", return_value=100):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(cli.ask_output_file(), "two.csv")

    def test_ask_output_file_can_go_back(self):
        with patch.object(cli, "output_csv_files", return_value=["one.csv"]):
            with patch("builtins.input", return_value="0"):
                with patch.object(cli.os.path, "getmtime", return_value=100):
                    with redirect_stdout(io.StringIO()):
                        self.assertIsNone(cli.ask_output_file())


class AppTests(unittest.TestCase):
    def test_ips_from_rows_strips_and_skips_empty_values(self):
        rows = [{"ip": " 104.16.1.1 "}, {"ip": ""}, {"missing": "x"}]

        self.assertEqual(app.ips_from_rows(rows), ["104.16.1.1"])

    def test_worker_count_for_speed_tests_is_always_one(self):
        settings = AppSettings(concurrency=100)

        self.assertEqual(app.worker_count_for(settings), 100)
        self.assertEqual(app.worker_count_for(settings, speed_mode="download"), 1)

    def test_create_proxy_configs_from_output_handles_no_selection(self):
        with patch.object(app.cli, "ask_output_file", return_value=None):
            self.assertIsNone(app.create_proxy_configs_from_output(sample_profile()))

    def test_create_proxy_configs_from_output_saves_rows(self):
        with patch.object(app.cli, "ask_output_file", return_value="scan.csv"):
            with patch.object(app, "read_working_ips", return_value=[{"ip": "104.16.1.1"}]):
                with patch.object(app, "save_proxy_configs", return_value="configs.txt") as save:
                    with redirect_stdout(io.StringIO()):
                        app.create_proxy_configs_from_output(sample_profile())

        save.assert_called_once()

    def test_run_speed_test_from_output_uses_selected_ips_and_mode(self):
        with patch.object(app.cli, "ask_output_file", return_value="C:\\output\\scan.csv"):
            with patch.object(app, "read_working_ips", return_value=[{"ip": "104.16.1.1"}]):
                with patch.object(app.cli, "ask_speed_mode", return_value="both"):
                    with patch.object(app, "run_scan") as run_scan:
                        app.run_speed_test_from_output(sample_profile(), AppSettings())

        run_scan.assert_called_once_with(["104.16.1.1"], "scan.csv", sample_profile(), AppSettings(), speed_mode="both")

    def test_run_scan_saves_only_passed_results_sorted(self):
        fake_results = [
            {"ip": "104.16.1.1", "ok": True, "ms": 200},
            {"ip": "104.16.1.2", "ok": False, "error": "bad"},
            {"ip": "104.16.1.3", "ok": True, "ms": 50},
        ]
        with patch.object(app, "test_ip", side_effect=fake_results):
            with patch.object(app, "print_passed_table"):
                with patch.object(app, "save_scan_results", return_value=("out.csv", "latest.csv")) as save:
                    with redirect_stdout(io.StringIO()):
                        app.run_scan(["a", "b", "c"], "source", sample_profile(), AppSettings(concurrency=1))

        passed = save.call_args.args[0]
        self.assertEqual([row["ip"] for row in passed], ["104.16.1.3", "104.16.1.1"])
        self.assertEqual(save.call_args.kwargs["prefix"], "working-cloudflare-proxy-ips")

    def test_run_scan_passes_timeout_to_ip_tests(self):
        with patch.object(app, "test_ip", return_value={"ip": "104.16.1.1", "ok": True, "ms": 10}) as test_ip:
            with patch.object(app, "print_passed_table"):
                with patch.object(app, "save_scan_results", return_value=("out.csv", "latest.csv")):
                    with redirect_stdout(io.StringIO()):
                        app.run_scan(
                            ["104.16.1.1"],
                            "source",
                            sample_profile(),
                            AppSettings(concurrency=1, timeout_ms=3500),
                        )

        self.assertEqual(test_ip.call_args.kwargs["timeout_ms"], 3500)

    def test_run_scan_uses_speed_prefix(self):
        with patch.object(app, "test_ip", return_value={"ip": "104.16.1.1", "ok": True, "ms": 10}):
            with patch.object(app, "print_passed_table"):
                with patch.object(app, "save_scan_results", return_value=("out.csv", "latest.csv")) as save:
                    with redirect_stdout(io.StringIO()):
                        app.run_scan(
                            ["104.16.1.1"],
                            "source",
                            sample_profile(),
                            AppSettings(concurrency=1),
                            speed_mode="download",
                        )

        self.assertEqual(save.call_args.kwargs["prefix"], "speed-test-cloudflare-proxy-ips")

    def test_main_routes_action_to_vless_config_creator(self):
        with patch.object(app, "ensure_project_dirs"):
            with patch.object(app.cli, "ask_config", return_value=sample_profile()):
                with patch.object(app.cli, "ask_action", side_effect=[4, 6]):
                    with patch.object(app, "create_proxy_configs_from_output") as creator:
                        with redirect_stdout(io.StringIO()):
                            app.main([])

        creator.assert_called_once_with(sample_profile())

    def test_main_exits_on_exit_action(self):
        with patch.object(app, "ensure_project_dirs"):
            with patch.object(app.cli, "ask_config", return_value=sample_profile()):
                with patch.object(app.cli, "ask_action", return_value=6):
                    with redirect_stdout(io.StringIO()) as out:
                        app.main([])

        self.assertIn("Goodbye", out.getvalue())

    def test_main_routes_settings_action(self):
        with patch.object(app, "ensure_project_dirs"):
            with patch.object(app.cli, "ask_config", return_value=sample_profile()):
                with patch.object(app.cli, "ask_action", side_effect=[5, 6]):
                    with patch.object(app.cli, "ask_settings") as ask_settings:
                        with redirect_stdout(io.StringIO()):
                            app.main([])

        ask_settings.assert_called_once()

    def test_main_with_arg_runs_all_range_scan(self):
        with patch.object(app, "ensure_project_dirs"):
            with patch.object(app.cli, "ask_config", return_value=sample_profile()):
                with patch.object(app.cloudflare, "random_candidates", return_value=iter(["104.16.1.1"])):
                    with patch.object(app, "run_scan") as run_scan:
                        app.main(["1"])

        run_scan.assert_called_once_with(["104.16.1.1"], "all Cloudflare ranges", sample_profile(), AppSettings())


if __name__ == "__main__":
    unittest.main()
