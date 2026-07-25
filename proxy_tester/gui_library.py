import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .gui_utils import numeric_sort_value
from .metrics import normalize_failed_metric
from .proxy_config import parse_proxy_url
from .proxy_library import (
    import_library_text,
    load_proxy_library,
    save_proxy_library,
    update_library_result,
)
from .settings import (
    DEFAULT_FRAGMENT_ENABLED,
    DEFAULT_FRAGMENT_INTERVAL,
    DEFAULT_FRAGMENT_LENGTH,
    DEFAULT_FRAGMENT_PACKETS,
)
from .storage import append_log_line, create_log_file
from .xray import DEFAULT_SPEED_TEST_BYTES, DEFAULT_SPEED_TEST_TIMEOUT_MS, test_ip


LIBRARY_COLUMN_LABELS = {
    "name": "Name",
    "protocol": "Protocol",
    "server": "Server",
    "port": "Port",
    "ping": "Latency (ms)",
    "download": "Download (Mbps)",
    "upload": "Upload (Mbps)",
    "status": "Status",
}


class ProxyLibraryMixin:
    def _init_proxy_library(self):
        self.proxy_library_entries = []
        self.proxy_library_items = {}
        self.proxy_library_sort_column = "name"
        self.proxy_library_sort_reverse = False
        self.proxy_library_worker = None
        self.proxy_library_stop_event = threading.Event()
        self.proxy_library_active_id = None
        self.proxy_library_load_error = ""
        self.proxy_library_log_path = None
        try:
            self.proxy_library_entries = load_proxy_library()
        except (OSError, ValueError) as exc:
            self.proxy_library_load_error = str(exc)

    def _build_proxy_library_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        import_box = ttk.LabelFrame(parent, text="Import Proxy Configurations", padding=10)
        import_box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        import_box.columnconfigure(0, weight=1)
        ttk.Label(
            import_box,
            text="Paste one or more VLESS, VMess, Trojan, or Shadowsocks links.",
        ).grid(row=0, column=0, sticky="w")
        self.proxy_library_input = tk.Text(import_box, height=4, wrap="none")
        self.proxy_library_input.grid(row=1, column=0, sticky="ew", pady=(6, 8))

        import_actions = ttk.Frame(import_box)
        import_actions.grid(row=2, column=0, sticky="ew")
        self.proxy_library_import_button = ttk.Button(
            import_actions,
            text="Add Configurations",
            command=self.import_proxy_library_configs,
        )
        self.proxy_library_import_button.pack(side="left")
        self.proxy_library_remove_button = ttk.Button(
            import_actions,
            text="Remove Selected",
            command=self.remove_proxy_library_configs,
        )
        self.proxy_library_remove_button.pack(side="left", padx=(8, 0))
        self.proxy_library_clear_results_button = ttk.Button(
            import_actions,
            text="Clear Test Results",
            command=self.clear_proxy_library_results,
        )
        self.proxy_library_clear_results_button.pack(side="left", padx=(8, 0))
        self.proxy_library_run_button = ttk.Button(
            import_actions,
            text="Run Selected with Xray",
            command=self.run_library_config_with_xray,
        )
        self.proxy_library_run_button.pack(side="right")

        test_box = ttk.LabelFrame(parent, text="Connection Speed Test", padding=10)
        test_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.proxy_library_size_var = tk.StringVar(value=str(DEFAULT_SPEED_TEST_BYTES // (1024 * 1024)))
        self.proxy_library_timeout_var = tk.StringVar(value=str(DEFAULT_SPEED_TEST_TIMEOUT_MS))
        ttk.Label(test_box, text="Test size (MB)").pack(side="left")
        self.proxy_library_size_entry = ttk.Entry(test_box, textvariable=self.proxy_library_size_var, width=8)
        self.proxy_library_size_entry.pack(side="left", padx=(8, 18))
        ttk.Label(test_box, text="Timeout (ms)").pack(side="left")
        self.proxy_library_timeout_entry = ttk.Entry(
            test_box,
            textvariable=self.proxy_library_timeout_var,
            width=10,
        )
        self.proxy_library_timeout_entry.pack(side="left", padx=(8, 18))
        self.proxy_library_download_button = ttk.Button(
            test_box,
            text="Test Download",
            command=lambda: self.start_proxy_library_test("download"),
        )
        self.proxy_library_download_button.pack(side="left")
        self.proxy_library_upload_button = ttk.Button(
            test_box,
            text="Test Upload",
            command=lambda: self.start_proxy_library_test("upload"),
        )
        self.proxy_library_upload_button.pack(side="left", padx=(8, 0))
        self.proxy_library_both_button = ttk.Button(
            test_box,
            text="Test Both",
            command=lambda: self.start_proxy_library_test("both"),
        )
        self.proxy_library_both_button.pack(side="left", padx=(8, 0))
        self.proxy_library_stop_button = ttk.Button(
            test_box,
            text="Stop",
            command=self.stop_proxy_library_tests,
            state="disabled",
        )
        self.proxy_library_stop_button.pack(side="right")

        fragment_box = ttk.LabelFrame(parent, text="Test Fragmentation", padding=10)
        fragment_box.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.proxy_library_fragment_enabled_var = tk.BooleanVar(value=DEFAULT_FRAGMENT_ENABLED)
        self.proxy_library_fragment_packets_var = tk.StringVar(value=DEFAULT_FRAGMENT_PACKETS)
        self.proxy_library_fragment_interval_var = tk.StringVar(value=DEFAULT_FRAGMENT_INTERVAL)
        self.proxy_library_fragment_length_var = tk.StringVar(value=DEFAULT_FRAGMENT_LENGTH)
        self.proxy_library_fragment_enabled_check = ttk.Checkbutton(
            fragment_box,
            text="Enable fragmentation",
            variable=self.proxy_library_fragment_enabled_var,
            command=self._sync_proxy_library_fragment_state,
        )
        self.proxy_library_fragment_enabled_check.pack(side="left")
        ttk.Label(fragment_box, text="Packets").pack(side="left", padx=(20, 6))
        self.proxy_library_fragment_packets_entry = ttk.Entry(
            fragment_box,
            textvariable=self.proxy_library_fragment_packets_var,
            width=12,
        )
        self.proxy_library_fragment_packets_entry.pack(side="left")
        ttk.Label(fragment_box, text="Interval (ms)").pack(side="left", padx=(18, 6))
        self.proxy_library_fragment_interval_entry = ttk.Entry(
            fragment_box,
            textvariable=self.proxy_library_fragment_interval_var,
            width=12,
        )
        self.proxy_library_fragment_interval_entry.pack(side="left")
        ttk.Label(fragment_box, text="Length (bytes)").pack(side="left", padx=(18, 6))
        self.proxy_library_fragment_length_entry = ttk.Entry(
            fragment_box,
            textvariable=self.proxy_library_fragment_length_var,
            width=12,
        )
        self.proxy_library_fragment_length_entry.pack(side="left")
        self._sync_proxy_library_fragment_state()

        status = ttk.Frame(parent)
        status.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        status.columnconfigure(0, weight=1)
        self.proxy_library_status_var = tk.StringVar(
            value=self.proxy_library_load_error or f"{len(self.proxy_library_entries)} saved configurations"
        )
        ttk.Label(status, textvariable=self.proxy_library_status_var).grid(row=0, column=0, sticky="w")
        self.proxy_library_progress = ttk.Progressbar(status, maximum=100)
        self.proxy_library_progress.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        table_frame = ttk.Frame(parent)
        table_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 12))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = tuple(LIBRARY_COLUMN_LABELS)
        self.proxy_library_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        widths = {
            "name": 185,
            "protocol": 90,
            "server": 205,
            "port": 65,
            "ping": 105,
            "download": 135,
            "upload": 125,
            "status": 160,
        }
        for column in columns:
            self.proxy_library_table.heading(
                column,
                text=LIBRARY_COLUMN_LABELS[column],
                command=lambda selected=column: self.sort_proxy_library_by(selected),
            )
            self.proxy_library_table.column(column, width=widths[column], anchor="w")
        self.proxy_library_table.grid(row=0, column=0, sticky="nsew")
        self.proxy_library_table.tag_configure("active", background=self.theme_palette["active_row"])
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.proxy_library_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.proxy_library_table.configure(yscrollcommand=scrollbar.set)
        self.proxy_library_table.bind("<Button-3>", self.open_proxy_library_menu)
        self.proxy_library_table.bind("<Button-2>", self.open_proxy_library_menu)
        self.proxy_library_table.bind("<Double-1>", lambda _event: self.run_library_config_with_xray())
        self.proxy_library_table.bind("<Delete>", self.delete_selected_proxy_library_configs)

        self.proxy_library_menu = tk.Menu(self, tearoff=0)
        self.proxy_library_menu.add_command(
            label="Test Download",
            command=lambda: self.start_proxy_library_test("download"),
        )
        self.proxy_library_menu.add_command(
            label="Test Upload",
            command=lambda: self.start_proxy_library_test("upload"),
        )
        self.proxy_library_menu.add_command(
            label="Test Download and Upload",
            command=lambda: self.start_proxy_library_test("both"),
        )
        self.proxy_library_menu.add_separator()
        self.proxy_library_menu.add_command(label="Run with Xray", command=self.run_library_config_with_xray)
        self.proxy_library_menu.add_command(label="Remove", command=self.remove_proxy_library_configs)
        self._render_proxy_library()

    def import_proxy_library_configs(self):
        value = self.proxy_library_input.get("1.0", "end").strip()
        merged, added, errors = import_library_text(self.proxy_library_entries, value)
        if not added and not errors:
            messagebox.showwarning("No Configurations Found", "Paste at least one supported proxy link.")
            return
        self.proxy_library_entries = merged
        save_proxy_library(self.proxy_library_entries)
        self._render_proxy_library()
        self.proxy_library_input.delete("1.0", "end")
        message = f"Added {len(added)} configurations."
        if errors:
            message += f" Rejected {len(errors)} invalid configurations."
        self.proxy_library_status_var.set(message)
        if errors:
            messagebox.showwarning("Some Configurations Were Rejected", "\n".join(errors[:8]))

    def _selected_proxy_library_ids(self):
        return list(self.proxy_library_table.selection())

    def _selected_proxy_library_entries(self, use_all_when_empty=False):
        selected = set(self._selected_proxy_library_ids())
        if not selected and use_all_when_empty:
            return list(self.proxy_library_entries)
        return [entry for entry in self.proxy_library_entries if entry["id"] in selected]

    def remove_proxy_library_configs(self):
        selected = set(self._selected_proxy_library_ids())
        if not selected:
            messagebox.showwarning("Selection Required", "Select one or more configurations to remove.")
            return
        if not messagebox.askyesno(
            "Remove Configurations",
            f"Remove {len(selected)} selected configurations?",
        ):
            return
        self.proxy_library_entries = [
            entry for entry in self.proxy_library_entries if entry["id"] not in selected
        ]
        save_proxy_library(self.proxy_library_entries)
        self._render_proxy_library()
        self.proxy_library_status_var.set(f"{len(self.proxy_library_entries)} saved configurations")

    def delete_selected_proxy_library_configs(self, _event=None):
        if self.proxy_library_worker and self.proxy_library_worker.is_alive():
            return "break"
        self.remove_proxy_library_configs()
        return "break"

    def clear_proxy_library_results(self):
        selected = set(self._selected_proxy_library_ids())
        targets = selected or {entry["id"] for entry in self.proxy_library_entries}
        for entry in self.proxy_library_entries:
            if entry["id"] in targets:
                entry.update(
                    latency_ms="",
                    download_mbps="",
                    upload_mbps="",
                    status="Not tested",
                    error="",
                )
        save_proxy_library(self.proxy_library_entries)
        self._render_proxy_library()
        self.proxy_library_status_var.set(f"Cleared results for {len(targets)} configurations.")

    def _proxy_library_test_settings(self):
        try:
            size_mb = float(self.proxy_library_size_var.get())
            timeout_ms = int(self.proxy_library_timeout_var.get())
            if size_mb <= 0 or timeout_ms <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Test Settings", "Test size and timeout must be greater than zero.")
            return None
        return int(size_mb * 1024 * 1024), timeout_ms

    def _sync_proxy_library_fragment_state(self):
        state = "normal" if self.proxy_library_fragment_enabled_var.get() else "disabled"
        for entry in (
            self.proxy_library_fragment_packets_entry,
            self.proxy_library_fragment_interval_entry,
            self.proxy_library_fragment_length_entry,
        ):
            entry.configure(state=state)

    def _proxy_library_fragment_settings(self):
        if not self.proxy_library_fragment_enabled_var.get():
            return {}
        fragment = {
            "packets": self.proxy_library_fragment_packets_var.get().strip(),
            "interval": self.proxy_library_fragment_interval_var.get().strip(),
            "length": self.proxy_library_fragment_length_var.get().strip(),
        }
        if any(not value for value in fragment.values()):
            messagebox.showerror(
                "Fragmentation Settings",
                "Packets, interval, and length are required when fragmentation is enabled.",
            )
            return None
        return fragment

    def start_proxy_library_test(self, speed_mode):
        if self.proxy_library_worker and self.proxy_library_worker.is_alive():
            return
        settings = self._proxy_library_test_settings()
        fragment = self._proxy_library_fragment_settings()
        entries = self._selected_proxy_library_entries(use_all_when_empty=True)
        if settings is None or fragment is None:
            return
        if not entries:
            messagebox.showwarning("No Configurations", "Add at least one proxy configuration first.")
            return
        self.proxy_library_stop_event.clear()
        self.proxy_library_progress["value"] = 0
        self.proxy_library_log_path = create_log_file("proxy-library-speed-test")
        self._proxy_library_log(
            f"Starting {speed_mode} test: configurations={len(entries)}, "
            f"size_bytes={settings[0]}, timeout_ms={settings[1]}, "
            f"fragment={fragment or 'disabled'}"
        )
        self._set_proxy_library_running(True)
        self.proxy_library_status_var.set(f"Testing 0/{len(entries)} configurations...")
        self.proxy_library_worker = threading.Thread(
            target=self._proxy_library_test_worker,
            args=(entries, speed_mode, settings[0], settings[1], fragment),
            daemon=True,
        )
        self.proxy_library_worker.start()

    def _proxy_library_test_worker(self, entries, speed_mode, speed_test_bytes, timeout_ms, fragment):
        total = len(entries)
        completed = 0
        for entry in entries:
            if self.proxy_library_stop_event.is_set():
                break
            entry_id = entry["id"]
            self.events.put(("proxy_library_active", entry_id, True))
            try:
                profile = parse_proxy_url(entry["config"])
                result = test_ip(
                    profile.address,
                    completed + 1,
                    total,
                    profile,
                    speed_mode=speed_mode,
                    timeout_ms=timeout_ms,
                    speed_test_bytes=speed_test_bytes,
                    speed_timeout_ms=timeout_ms,
                    fragment=fragment,
                    process_started=self._track_process,
                    process_finished=self._untrack_process,
                )
            except Exception as exc:
                result = {
                    "ip": entry.get("address", ""),
                    "ok": False,
                    "ms": -1,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            finally:
                self.events.put(("proxy_library_active", entry_id, False))
            completed += 1
            self.events.put(("proxy_library_result", entry_id, speed_mode, result, completed, total))
        self.events.put(("proxy_library_done", completed, total, self.proxy_library_stop_event.is_set()))

    def stop_proxy_library_tests(self):
        self.proxy_library_stop_event.set()
        self._kill_active_processes()
        self._proxy_library_log("Stop requested. The active Xray test process was terminated.")
        if hasattr(self, "proxy_library_status_var"):
            self.proxy_library_status_var.set("Stopping proxy tests...")
        if hasattr(self, "proxy_library_stop_button"):
            self.proxy_library_stop_button.configure(state="disabled")

    def _set_proxy_library_running(self, running):
        state = "disabled" if running else "normal"
        for name in (
            "proxy_library_import_button",
            "proxy_library_remove_button",
            "proxy_library_clear_results_button",
            "proxy_library_run_button",
            "proxy_library_download_button",
            "proxy_library_upload_button",
            "proxy_library_both_button",
            "proxy_library_size_entry",
            "proxy_library_timeout_entry",
            "proxy_library_fragment_enabled_check",
        ):
            getattr(self, name).configure(state=state)
        for name in (
            "proxy_library_fragment_packets_entry",
            "proxy_library_fragment_interval_entry",
            "proxy_library_fragment_length_entry",
        ):
            getattr(self, name).configure(state="disabled" if running else "normal")
        if not running:
            self._sync_proxy_library_fragment_state()
        self.proxy_library_stop_button.configure(state="normal" if running else "disabled")

    def handle_proxy_library_event(self, event):
        kind = event[0]
        if kind == "proxy_library_active":
            _, entry_id, active = event
            self._set_proxy_library_active(entry_id, active)
        elif kind == "proxy_library_result":
            _, entry_id, speed_mode, result, completed, total = event
            self._apply_proxy_library_result(entry_id, speed_mode, result)
            self.proxy_library_progress["value"] = (completed / total) * 100 if total else 0
            if result.get("ok"):
                self._proxy_library_log(
                    f"PASS {result.get('ip', '')} latency={result.get('ms', -1)} "
                    f"download={result.get('download_mbps', '')} upload={result.get('upload_mbps', '')}"
                )
                self.proxy_library_status_var.set(f"Testing {completed}/{total} configurations...")
            else:
                message = str(result.get("error") or "Connection failed")
                self._proxy_library_log(
                    f"FAIL {result.get('ip', '')} latency={result.get('ms', -1)} error={message}"
                )
                self.proxy_library_status_var.set(
                    f"{completed}/{total} failed: {message[:120]}"
                )
        elif kind == "proxy_library_done":
            _, completed, total, stopped = event
            self._set_proxy_library_running(False)
            prefix = "Stopped" if stopped else "Complete"
            self.proxy_library_status_var.set(f"{prefix}: tested {completed}/{total} configurations.")
            self._proxy_library_log(f"{prefix}: tested {completed}/{total} configurations.")

    def _proxy_library_log(self, message):
        append_log_line(self.__dict__.get("proxy_library_log_path"), message)

    def _apply_proxy_library_result(self, entry_id, speed_mode, result):
        for index, entry in enumerate(self.proxy_library_entries):
            if entry["id"] == entry_id:
                updated = update_library_result(entry, result, speed_mode)
                self.proxy_library_entries[index] = updated
                save_proxy_library(self.proxy_library_entries)
                self._upsert_proxy_library_row(updated)
                return

    def _set_proxy_library_active(self, entry_id, active):
        self.proxy_library_active_id = entry_id if active else None
        item = self.proxy_library_items.get(entry_id)
        if item:
            self.proxy_library_table.item(item, tags=("active",) if active else ())
            if active:
                self.proxy_library_table.see(item)

    def run_library_config_with_xray(self):
        entries = self._selected_proxy_library_entries()
        if len(entries) != 1:
            messagebox.showwarning("Single Selection Required", "Select exactly one configuration to run.")
            return
        try:
            profile = parse_proxy_url(entries[0]["config"])
        except ValueError as exc:
            messagebox.showerror("Configuration Error", str(exc))
            return
        self._set_runner_profile(profile)
        self.runner_ip_var.set(profile.address)
        self.notebook.select(self.runner_tab)
        self.start_xray_runner(profile.address)

    def open_proxy_library_menu(self, event):
        item = self.proxy_library_table.identify_row(event.y)
        if item and item not in self.proxy_library_table.selection():
            self.proxy_library_table.selection_set(item)
        if not self.proxy_library_table.selection():
            return
        self.proxy_library_menu.entryconfigure(4, state="normal" if len(self.proxy_library_table.selection()) == 1 else "disabled")
        try:
            self.proxy_library_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.proxy_library_menu.grab_release()

    def sort_proxy_library_by(self, column):
        if self.proxy_library_sort_column == column:
            self.proxy_library_sort_reverse = not self.proxy_library_sort_reverse
        else:
            self.proxy_library_sort_column = column
            self.proxy_library_sort_reverse = column in ("download", "upload")
        self._render_proxy_library()

    def _sorted_proxy_library_entries(self):
        return sorted(
            self.proxy_library_entries,
            key=self._proxy_library_sort_value,
            reverse=self.proxy_library_sort_reverse,
        )

    def _proxy_library_sort_value(self, entry):
        column = self.proxy_library_sort_column
        if column == "server":
            return entry.get("address", "").lower()
        if column == "ping":
            return numeric_sort_value(entry.get("latency_ms"), float("inf"))
        if column in ("download", "upload"):
            return numeric_sort_value(entry.get(f"{column}_mbps"), -1)
        if column == "port":
            return int(entry.get("port") or 0)
        return str(entry.get(column, "")).lower()

    def _render_proxy_library(self):
        selected = set(self._selected_proxy_library_ids()) if self.proxy_library_items else set()
        for item in self.proxy_library_table.get_children():
            self.proxy_library_table.delete(item)
        self.proxy_library_items = {}
        self._update_proxy_library_headings()
        for entry in self._sorted_proxy_library_entries():
            self._insert_proxy_library_row(entry)
        restored = [entry_id for entry_id in selected if entry_id in self.proxy_library_items]
        if restored:
            self.proxy_library_table.selection_set(restored)

    def _insert_proxy_library_row(self, entry):
        entry_id = entry["id"]
        self.proxy_library_table.insert(
            "",
            "end",
            iid=entry_id,
            values=self._proxy_library_values(entry),
            tags=("active",) if entry_id == self.proxy_library_active_id else (),
        )
        self.proxy_library_items[entry_id] = entry_id

    def _upsert_proxy_library_row(self, entry):
        entry_id = entry["id"]
        if entry_id not in self.proxy_library_items:
            self._insert_proxy_library_row(entry)
            return
        self.proxy_library_table.item(
            entry_id,
            values=self._proxy_library_values(entry),
            tags=("active",) if entry_id == self.proxy_library_active_id else (),
        )
        ordered_ids = [item["id"] for item in self._sorted_proxy_library_entries()]
        self.proxy_library_table.move(entry_id, "", ordered_ids.index(entry_id))
        self.proxy_library_table.selection_set(entry_id)
        self.proxy_library_table.focus(entry_id)
        self.proxy_library_table.see(entry_id)

    def _proxy_library_values(self, entry):
        status = entry.get("status", "")
        if status == "Failed" and entry.get("error"):
            status = f"Failed: {entry['error'][:48]}"
        return (
            entry.get("name", ""),
            entry.get("protocol", "").upper(),
            entry.get("address", ""),
            entry.get("port", ""),
            normalize_failed_metric(entry.get("latency_ms", "")),
            normalize_failed_metric(entry.get("download_mbps", "")),
            normalize_failed_metric(entry.get("upload_mbps", "")),
            status,
        )

    def _update_proxy_library_headings(self):
        direction = "\u25bc" if self.proxy_library_sort_reverse else "\u25b2"
        for column, label in LIBRARY_COLUMN_LABELS.items():
            text = f"{label} {direction}" if column == self.proxy_library_sort_column else label
            self.proxy_library_table.heading(column, text=text)
