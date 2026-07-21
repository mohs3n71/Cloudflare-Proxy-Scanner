import os
import queue
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from tkinter import messagebox

from . import cloudflare
from .gui_utils import merge_rows_by_ip, numeric_sort_value
from .metrics import normalize_failed_metric
from .settings import AppSettings
from .storage import append_log_line, create_log_file, read_working_ips, save_scan_results
from .xray import DEFAULT_SPEED_TEST_BYTES, DEFAULT_SPEED_TEST_TIMEOUT_MS, test_ip


class WorkerMixin:
    def _set_running(self, running, operation=None):
        state = "disabled" if running or self.profile is None else "normal"
        for button in (self.start_button, self.speed_button, self.proxy_config_button):
            button.configure(state=state)
        self.remove_failed_button.configure(state="disabled" if running else "normal")
        self.output_combo.configure(state="disabled" if running else "readonly")
        self.refresh_outputs_button.configure(state="disabled" if running else "normal")
        self._set_speed_fragment_state("disabled" if running else "normal")
        self.stop_scan_button.configure(state="normal" if running and operation == "scan" else "disabled")
        self.stop_speed_button.configure(state="normal" if running and operation == "speed" else "disabled")

    def _set_speed_fragment_state(self, state):
        if "speed_fragment_enabled_check" not in self.__dict__:
            return
        self.speed_fragment_enabled_check.configure(state=state)
        if state == "disabled":
            for entry in (
                self.speed_fragment_packets_entry,
                self.speed_fragment_interval_entry,
                self.speed_fragment_length_entry,
            ):
                entry.configure(state="disabled")
        else:
            self._sync_speed_fragment_state()

    def stop_current(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_event.set()
            self._kill_active_processes()
            self.status_var.set("Stopping tests...")
            self._log("Stop requested. Pending tests were cancelled and active Xray processes were terminated.")
            self.stop_scan_button.configure(state="disabled")
            self.stop_speed_button.configure(state="disabled")

    def _track_process(self, proc):
        with self.active_processes_lock:
            self.active_processes.add(proc)

    def _untrack_process(self, proc):
        with self.active_processes_lock:
            self.active_processes.discard(proc)

    def _kill_active_processes(self):
        with self.active_processes_lock:
            processes = list(self.active_processes)
        for proc in processes:
            try:
                proc.kill()
            except Exception:
                pass

    def _clear_results(self, initial_results=None, reset_sort=True):
        self.passed_results = list(initial_results or [])
        self.table_items_by_ip = {}
        self.active_test_ips = set()
        if reset_sort:
            self.sort_column = "ping"
            self.sort_reverse = False
        for item in self.table.get_children():
            self.table.delete(item)
        self.progress["value"] = 0
        self.log.delete("1.0", "end")
        self._refresh_passed_table()

    def _log(self, message):
        self.log.insert("end", message + "\n")
        self.log.see("end")
        append_log_line(self.current_log_path, message)

    def _make_scan_ips(self):
        if self.mode_var.get() == "all_full":
            return list(cloudflare.all_candidates()), "all Cloudflare IPs"

        if self.mode_var.get() == "range_full":
            net = self.ranges_by_label.get(self.range_var.get())
            if net is None:
                messagebox.showerror("IP Range Required", "Select an IP range.")
                return None, None
            return list(cloudflare.usable_ips_from_network(net)), f"every IP in {net}"

        try:
            count = int(self.count_var.get())
            if count <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid IP Count", "Enter an IP count greater than zero.")
            return None, None

        if self.mode_var.get() == "all":
            return list(cloudflare.random_candidates(count)), "all Cloudflare ranges"

        if self.mode_var.get() == "custom":
            if not self.custom_networks:
                messagebox.showerror("Custom Ranges Required", "Add at least one custom IPv4 range first.")
                return None, None
            return (
                list(
                    cloudflare.random_candidates_from_networks(
                        self.custom_networks,
                        count,
                        "custom IPv4 addresses",
                    )
                ),
                f"{len(self.custom_networks)} custom ranges",
            )

        net = self.ranges_by_label.get(self.range_var.get())
        if net is None:
            messagebox.showerror("IP Range Required", "Select an IP range.")
            return None, None
        return list(cloudflare.random_candidates_from_network(net, count)), str(net)

    def start_scan(self):
        profile = self._selected_profile()
        if profile is None or not self._validate_settings():
            return
        try:
            ips, source = self._make_scan_ips()
        except ValueError as exc:
            messagebox.showerror("Scan Error", str(exc))
            return
        if not ips:
            return
        self._start_worker(ips, source, profile, speed_mode=None)

    def start_speed_test(self):
        profile = self._selected_profile()
        speed_settings = self._speed_settings()
        speed_fragment = self._speed_fragment_settings()
        if profile is None or speed_settings is None or speed_fragment is None:
            return
        path = self._selected_output_path()
        if not path:
            return
        rows = read_working_ips(path)
        ips = [row["ip"].strip() for row in rows if (row.get("ip") or "").strip()]
        if not ips:
            messagebox.showwarning("No IP Addresses", "The selected results file contains no IP addresses.")
            return
        initial_results = [self._result_from_csv_row(row) for row in rows]
        self._start_worker(
            ips,
            os.path.basename(path),
            profile,
            speed_mode=self.speed_mode_var.get(),
            initial_results=initial_results,
            speed_test_bytes=speed_settings[0],
            speed_timeout_ms=speed_settings[1],
            speed_fragment=speed_fragment,
        )

    def start_speed_test_for_selected(self, speed_mode=None):
        profile = self._selected_profile()
        speed_settings = self._speed_settings()
        speed_fragment = self._speed_fragment_settings()
        if profile is None or speed_settings is None or speed_fragment is None:
            return
        ips = self._selected_table_ips()
        if not ips:
            messagebox.showwarning("No IP Addresses Selected", "Select one or more IP addresses in the table.")
            return
        self._start_worker(
            ips,
            "selected table IPs",
            profile,
            speed_mode=speed_mode or self.speed_mode_var.get(),
            initial_results=list(self.passed_results),
            speed_test_bytes=speed_settings[0],
            speed_timeout_ms=speed_settings[1],
            speed_fragment=speed_fragment,
            restore_selection_ips=ips,
            reset_sort=False,
        )

    def _start_worker(
        self,
        ips,
        source,
        profile,
        speed_mode,
        initial_results=None,
        speed_test_bytes=DEFAULT_SPEED_TEST_BYTES,
        speed_timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS,
        speed_fragment=None,
        restore_selection_ips=None,
        reset_sort=True,
    ):
        self._clear_results(initial_results=initial_results, reset_sort=reset_sort)
        self.stop_event.clear()
        operation = "speed" if speed_mode else "scan"
        self.current_log_path = create_log_file(f"{operation}-{source}")
        self._set_running(True, operation=operation)
        action = "Testing" if speed_mode else "Scanning"
        self.status_var.set(f"{action} {len(ips)} IPs from {source}...")
        self._log(f"Log file: {self.current_log_path}")
        self._log(f"Starting {operation}: {len(ips)} IPs from {source}.")
        if speed_mode:
            self._log("Speed tests run sequentially.")
            self._log(f"Test size: {round(speed_test_bytes / 1024 / 1024, 2)} MB")
            self._log(f"Speed test timeout: {speed_timeout_ms} ms")
            self._log(f"Speed test fragmentation: {'enabled' if speed_fragment else 'disabled'}")
        else:
            self._log(f"Concurrent tests: {self.settings.concurrency}")
            self._log(f"Scan timeout: {self.settings.timeout_ms} ms")
        self.worker_thread = threading.Thread(
            target=self._scan_worker,
            args=(
                ips,
                source,
                profile,
                speed_mode,
                AppSettings(self.settings.concurrency, speed_timeout_ms if speed_mode else self.settings.timeout_ms),
                speed_test_bytes,
                speed_timeout_ms,
                speed_fragment,
                list(restore_selection_ips or []),
                list(initial_results or []),
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def _scan_worker(
        self,
        ips,
        source,
        profile,
        speed_mode,
        settings,
        speed_test_bytes,
        speed_timeout_ms,
        speed_fragment=None,
        restore_selection_ips=None,
        initial_results=None,
    ):
        results = []
        prefix = "speed-test-cloudflare-proxy-ips" if speed_mode else "working-cloudflare-proxy-ips"
        worker_count = 1 if speed_mode else settings.concurrency
        stopped = self.stop_event.is_set()
        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {}
                next_index = 0
                completed = 0

                def submit_next():
                    nonlocal next_index
                    ip = ips[next_index]
                    index = next_index + 1
                    self.events.put(("active_start", ip))
                    future = executor.submit(
                        test_ip,
                        ip,
                        index,
                        len(ips),
                        profile,
                        speed_mode=speed_mode,
                        timeout_ms=settings.timeout_ms,
                        speed_test_bytes=speed_test_bytes,
                        speed_timeout_ms=speed_timeout_ms,
                        fragment=speed_fragment if speed_mode else None,
                        process_started=self._track_process,
                        process_finished=self._untrack_process,
                    )
                    futures[future] = ip
                    next_index += 1

                while next_index < len(ips) and len(futures) < worker_count and not self.stop_event.is_set():
                    submit_next()

                while futures:
                    if self.stop_event.is_set() and not stopped:
                        stopped = True
                        for future in futures:
                            future.cancel()

                    done, _pending = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
                    if not done:
                        continue

                    for future in done:
                        ip = futures.pop(future)
                        completed += 1
                        self.events.put(("active_done", ip))
                        if future.cancelled():
                            continue
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {"ip": ip, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
                        if speed_mode:
                            result = self._normalize_speed_result(result, speed_mode)
                        results.append(result)
                        self.events.put(("result", completed, len(ips), result, bool(speed_mode)))

                    while next_index < len(ips) and len(futures) < worker_count and not stopped:
                        submit_next()

            completed = len(results)
            passed = [result for result in results if result["ok"]]
            save_rows = merge_rows_by_ip(initial_results or [], results) if speed_mode else passed
            save_rows.sort(key=lambda result: result["ms"])
            out_path, latest_path = save_scan_results(save_rows, prefix=prefix)
            self.events.put(
                (
                    "done",
                    len(passed),
                    out_path,
                    latest_path,
                    stopped,
                    completed,
                    len(ips),
                    bool(speed_mode),
                    list(restore_selection_ips or []),
                )
            )
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _normalize_speed_result(self, result, speed_mode):
        normalized = dict(result)
        normalized["ms"] = normalized.get("ms", -1)
        if speed_mode in ("download", "both") and "download_mbps" not in normalized:
            normalized["download_mbps"] = -1
        if speed_mode in ("upload", "both") and "upload_mbps" not in normalized:
            normalized["upload_mbps"] = -1
        for key in ("ms", "download_mbps", "upload_mbps"):
            if key in normalized:
                normalized[key] = normalize_failed_metric(normalized[key])
        return normalized

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "result":
                    _, completed, total, result, show_all = event
                    self.progress["value"] = (completed / total) * 100 if total else 0
                    if show_all:
                        self._upsert_table_result(result)
                    elif result["ok"]:
                        self._upsert_table_result(result)

                    if result["ok"]:
                        self._log(f"PASS {result['ip']} {result['ms']}ms")
                        for warning in result.get("speed_warnings", []):
                            self._log(f"WARN {result['ip']} {warning}")
                    else:
                        self._log(f"FAIL {result['ip']} {result.get('error', '')}")
                        if result.get("speed_debug"):
                            self._log(f"DEBUG {result['ip']} {result['speed_debug']}")
                    self.status_var.set(f"Progress: {completed}/{total} ({(completed / total) * 100:.1f}%)")
                elif kind == "active_start":
                    _, ip = event
                    self._set_ip_active(ip, True)
                elif kind == "active_done":
                    _, ip = event
                    self._set_ip_active(ip, False)
                elif kind == "runner_log":
                    _, message = event
                    self._append_runner_log(message)
                elif kind == "runner_exit":
                    _, proc, code = event
                    self._handle_runner_exit(proc, code)
                elif kind == "runner_speed_result":
                    _, speed_mode, result = event
                    self._handle_runner_speed_result(speed_mode, result)
                elif kind == "runner_fragment_scan_progress":
                    _, index, total, speed_mode, fragment, value = event
                    self._handle_runner_fragment_scan_progress(index, total, speed_mode, fragment, value)
                elif kind == "runner_fragment_scan_result":
                    _, speed_mode, ip, config_name, fragment, value, results, stopped = event
                    self._handle_runner_fragment_scan_result(
                        speed_mode,
                        ip,
                        config_name,
                        fragment,
                        value,
                        results,
                        stopped,
                    )
                elif kind == "update_check_result":
                    _, result = event
                    self._handle_update_check_result(result)
                elif kind == "update_check_error":
                    _, message = event
                    self._handle_update_check_error(message)
                elif kind == "done":
                    self._handle_done_event(*event[1:])
                elif kind == "error":
                    _, message = event
                    self._set_running(False)
                    self.status_var.set("Error")
                    messagebox.showerror("Scan Error", message)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _handle_done_event(
        self,
        count,
        out_path,
        latest_path,
        stopped,
        completed,
        total,
        was_speed_mode=False,
        restore_selection_ips=None,
    ):
        self._set_running(False)
        self._select_output_path(out_path)
        if restore_selection_ips:
            self._restore_table_selection_by_ips(restore_selection_ips)
        operation_label = "Speed test" if was_speed_mode else "Scan"
        if stopped:
            self.status_var.set(f"Stopped: {completed}/{total} tested, {count} successful.")
            self._log(
                f"{operation_label} stopped. Saved {count} successful IPs from completed tests to: {out_path}"
            )
        else:
            self.status_var.set(f"Complete: {count} successful IPs.")
            self._log(f"Saved {count} successful IPs to: {out_path}")
        self._log(f"Updated latest results: {latest_path}")
        if self._should_auto_speed_after_scan(was_speed_mode, stopped, count):
            self._log("Automatic speed testing is enabled. Starting now.")
            self.start_speed_test()

    def _should_auto_speed_after_scan(self, was_speed_mode, stopped, count):
        return (
            not was_speed_mode
            and not stopped
            and count > 0
            and bool(self.auto_speed_after_scan_var.get())
        )

