import os
import tkinter as tk
from tkinter import messagebox, ttk

from .paths import CONFIG_DIR
from .storage import config_files, output_csv_files, read_working_ips, save_scan_results, save_proxy_configs
from .proxy_config import parse_proxy_config
from .gui_utils import numeric_sort_value


class ConfigMixin:
    def _load_configs(self):
        self.config_paths_by_name = {os.path.basename(path): path for path in config_files()}
        names = list(self.config_paths_by_name)
        self.config_combo["values"] = names
        if names:
            self.config_combo.current(0)
            self._select_config()
        else:
            self.profile = None
            self.config_var.set("")
            self.status_var.set("No proxy configuration found. Add one to enable scanning and speed tests.")
            self._sync_config_action_state()

    def _sync_range_state(self):
        if self.mode_var.get() == "range":
            self.range_combo.configure(state="readonly")
        else:
            self.range_combo.configure(state="disabled")
        self.count_entry.configure(state="disabled" if self.mode_var.get() == "all_full" else "normal")

    def _sync_speed_fragment_state(self):
        state = "normal" if self.speed_fragment_enabled_var.get() else "disabled"
        for entry in (
            self.speed_fragment_packets_entry,
            self.speed_fragment_interval_entry,
            self.speed_fragment_length_entry,
        ):
            entry.configure(state=state)

    def _select_config(self):
        name = self.config_var.get()
        if not name:
            self.profile = None
            self._sync_config_action_state()
            return
        try:
            self.profile = parse_proxy_config(self.config_paths_by_name[name])
            self._log(f"Selected configuration: {name}")
            self.status_var.set(f"Configuration: {name}")
        except Exception as exc:
            self.profile = None
            messagebox.showerror("Configuration Error", str(exc))
        self._sync_config_action_state()

    def _sync_config_action_state(self):
        state = "normal" if self.profile is not None else "disabled"
        for button in (self.start_button, self.speed_button, self.proxy_config_button):
            button.configure(state=state)
        if "runner_start_button" in self.__dict__:
            runner_state = state if not self._runner_is_active() else "disabled"
            self.runner_start_button.configure(state=runner_state)
            if "runner_export_button" in self.__dict__:
                self.runner_export_button.configure(state=state)
            self._set_runner_speed_state(False)

    def open_add_config_modal(self):
        modal = tk.Toplevel(self)
        modal.title("Add Proxy Configuration")
        modal.geometry("640x320")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        frame = ttk.Frame(modal, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Configuration name (unique)").pack(anchor="w")
        name_var = tk.StringVar(value=self._next_available_config_filename("new-config.config"))
        ttk.Entry(frame, textvariable=name_var).pack(fill="x", pady=(4, 10))
        ttk.Label(frame, text="Proxy URL").pack(anchor="w")
        text = tk.Text(frame, height=8, wrap="word")
        text.pack(fill="both", expand=True, pady=(4, 10))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def save_config():
            name = self._safe_config_filename(name_var.get())
            value = text.get("1.0", "end").strip()
            if not value.startswith(("vless://", "vmess://", "trojan://")):
                messagebox.showerror(
                    "Invalid Configuration",
                    "Enter one VLESS, VMess, or Trojan proxy URL.",
                )
                return
            try:
                path = self._create_config_file(name, value)
            except FileExistsError:
                messagebox.showerror(
                    "Configuration Already Exists",
                    f'A configuration named "{name}" already exists. Choose a different name.',
                )
                return
            except Exception as exc:
                messagebox.showerror("Invalid Configuration", str(exc))
                return
            self._load_configs()
            self.config_var.set(os.path.basename(path))
            self._select_config()
            modal.destroy()

        ttk.Button(buttons, text="Save Configuration", command=save_config).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=modal.destroy).pack(side="right", padx=(0, 8))

    def _safe_config_filename(self, value):
        name = "".join(char if char.isalnum() or char in ("-", "_", ".") else "-" for char in value.strip())
        if not name:
            name = "config.config"
        root, ext = os.path.splitext(name)
        if ext.lower() != ".config":
            name = (root or name) + ".config"
        return name

    def _next_available_config_filename(self, preferred_name):
        name = self._safe_config_filename(preferred_name)
        root, ext = os.path.splitext(name)
        candidate = name
        suffix = 2
        while os.path.exists(os.path.join(CONFIG_DIR, candidate)):
            candidate = f"{root}-{suffix}{ext}"
            suffix += 1
        return candidate

    def _create_config_file(self, name, value):
        path = os.path.join(CONFIG_DIR, name)
        created = False
        try:
            with open(path, "x", encoding="utf-8") as config_file:
                config_file.write(value + "\n")
            created = True
            parse_proxy_config(path)
        except Exception:
            if created and os.path.exists(path):
                os.remove(path)
            raise
        return path

    def _load_outputs(self):
        self.output_paths_by_name = {os.path.basename(path): path for path in output_csv_files()}
        names = list(self.output_paths_by_name)
        self.output_combo["values"] = names
        if names and self.output_var.get() not in self.output_paths_by_name:
            self.output_combo.current(0)
            self.load_selected_output_into_table()

    def _select_output_path(self, path):
        self._load_outputs()
        name = os.path.basename(path)
        if name in self.output_paths_by_name:
            self.output_var.set(name)
            self.load_selected_output_into_table()

    def load_selected_output_into_table(self):
        path = self._selected_output_path(show_warning=False)
        if not path:
            return
        self.loaded_output_path = path
        rows = read_working_ips(path)
        self.passed_results = [self._result_from_csv_row(row) for row in rows]
        self.progress["value"] = 0
        self._refresh_passed_table()
        self.status_var.set(f"Loaded {len(self.passed_results)} IPs from {os.path.basename(path)}.")

    def _result_from_csv_row(self, row):
        return {
            "ip": (row.get("ip") or "").strip(),
            "ok": True,
            "ms": self._number_or_default(row.get("latency_ms"), -1, int),
            "download_mbps": self._number_or_default(row.get("download_mbps"), "", float),
            "upload_mbps": self._number_or_default(row.get("upload_mbps"), "", float),
        }

    def _number_or_default(self, value, default, caster):
        if value in (None, ""):
            return default
        try:
            return caster(float(value)) if caster is int else caster(value)
        except ValueError:
            return default

    def _validate_settings(self):
        try:
            self.settings.concurrency = int(self.concurrency_var.get())
            self.settings.timeout_ms = int(self.timeout_var.get())
            if self.settings.timeout_ms <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Scan Settings", "Enter a timeout greater than zero milliseconds.")
            return False
        return True

    def _speed_settings(self):
        try:
            size_mb = float(self.speed_size_var.get())
            timeout_ms = int(self.speed_timeout_var.get())
            if size_mb <= 0 or timeout_ms <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Speed Test Settings",
                "Test size and timeout must both be greater than zero.",
            )
            return None
        return int(size_mb * 1024 * 1024), timeout_ms

    def _speed_fragment_settings(self):
        if not self.speed_fragment_enabled_var.get():
            return {}
        fragment = {
            "packets": self.speed_fragment_packets_var.get().strip(),
            "interval": self.speed_fragment_interval_var.get().strip(),
            "length": self.speed_fragment_length_var.get().strip(),
        }
        if any(not value for value in fragment.values()):
            messagebox.showerror(
                "Fragmentation Settings",
                "Packets, interval, and length are required when fragmentation is enabled.",
            )
            return None
        return fragment

    def _selected_output_path(self, show_warning=True):
        name = self.output_var.get()
        if not name:
            if show_warning:
                messagebox.showwarning("Results File Required", "Select a results file first.")
            return None
        return self.output_paths_by_name.get(name)

    def _selected_profile(self):
        if self.profile is None:
            messagebox.showwarning("Configuration Required", "Select a valid proxy configuration first.")
            return None
        return self.profile

    def create_proxy_configs(self):
        profile = self._selected_profile()
        if profile is None:
            return
        path = self._selected_output_path()
        if not path:
            return
        rows = read_working_ips(path)
        if not rows:
            messagebox.showwarning("No IP Addresses", "The selected results file contains no IP addresses.")
            return
        out_path = save_proxy_configs(path, rows, profile)
        self._load_outputs()
        messagebox.showinfo(
            "Configurations Created",
            f"Created {len(rows)} proxy configurations:\n{out_path}",
        )

    def remove_failed_rows(self):
        before = len(self.passed_results)
        self.passed_results = [row for row in self.passed_results if not self._has_failed_metric(row)]
        removed = before - len(self.passed_results)
        self.active_test_ips = {row["ip"] for row in self.passed_results if row.get("active")}
        out_path, latest_path = save_scan_results(self.passed_results, prefix="filtered-cloudflare-proxy-ips")
        self._select_output_path(out_path)
        self.status_var.set(
            f"Removed {removed} failed results. Saved {len(self.passed_results)} remaining results."
        )
        self._log(f"Removed {removed} results containing a -1 latency, download, or upload value.")
        self._log(f"Saved filtered results to: {out_path}")
        self._log(f"Updated latest filtered results: {latest_path}")

    def _has_failed_metric(self, row):
        return any(numeric_sort_value(row.get(key), None) == -1 for key in ("ms", "download_mbps", "upload_mbps"))

