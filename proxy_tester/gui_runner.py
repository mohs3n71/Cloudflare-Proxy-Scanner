import json
import os
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .paths import XRAY_EXE
from .settings import (
    DEFAULT_FRAGMENT_ENABLED,
    RunnerSettings,
    SYSTEM_PROXY_CLEAR,
    SYSTEM_PROXY_DO_NOT_TOUCH,
    SYSTEM_PROXY_OPTIONS,
    SYSTEM_PROXY_SET,
    save_runner_settings,
)
from .storage import get_best_fragment, save_best_fragment, save_fragment_scan_results
from . import system_proxy
from .xray import make_xray_runner_config, test_ip


FRAGMENT_SCAN_VARIATIONS = [
    {"packets": "1-1", "interval": "1-1", "length": "1-3"},
    {"packets": "1-1", "interval": "1-1", "length": "1-7"},
    {"packets": "1-1", "interval": "1-2", "length": "1-10"},
    {"packets": "1-1", "interval": "2-5", "length": "5-15"},
    {"packets": "1-2", "interval": "1-1", "length": "1-5"},
    {"packets": "1-2", "interval": "1-2", "length": "1-7"},
    {"packets": "1-2", "interval": "2-5", "length": "5-10"},
    {"packets": "1-2", "interval": "5-10", "length": "10-20"},
    {"packets": "1-3", "interval": "1-1", "length": "1-7"},
    {"packets": "1-3", "interval": "1-2", "length": "1-10"},
    {"packets": "1-3", "interval": "2-5", "length": "5-15"},
    {"packets": "1-3", "interval": "5-10", "length": "10-30"},
    {"packets": "1-5", "interval": "1-1", "length": "1-7"},
    {"packets": "1-5", "interval": "1-2", "length": "1-10"},
    {"packets": "1-5", "interval": "2-5", "length": "1-10"},
    {"packets": "1-5", "interval": "5-10", "length": "10-40"},
    {"packets": "3-5", "interval": "1-3", "length": "1-15"},
    {"packets": "3-7", "interval": "2-5", "length": "5-30"},
    {"packets": "5-10", "interval": "5-10", "length": "10-50"},
    {"packets": "tlshello", "interval": "1-1", "length": "1-7"},
    {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
    {"packets": "tlshello", "interval": "2-5", "length": "5-15"},
    {"packets": "tlshello", "interval": "5-10", "length": "10-20"},
    {"packets": "tlshello", "interval": "10-20", "length": "100-200"},
]

# Upload tests favor larger slices and shorter delays so fragmentation is less
# likely to become the throughput bottleneck after the connection is established.
UPLOAD_FRAGMENT_SCAN_VARIATIONS = [
    {"packets": "tlshello", "interval": "0-1", "length": "1-3"},
    {"packets": "tlshello", "interval": "0-1", "length": "1-7"},
    {"packets": "tlshello", "interval": "1-2", "length": "5-10"},
    {"packets": "tlshello", "interval": "1-2", "length": "10-20"},
    {"packets": "tlshello", "interval": "2-5", "length": "20-40"},
    {"packets": "tlshello", "interval": "2-5", "length": "50-100"},
    {"packets": "tlshello", "interval": "5-10", "length": "100-200"},
    {"packets": "tlshello", "interval": "1-3", "length": "200-500"},
    {"packets": "1-1", "interval": "0-1", "length": "10-20"},
    {"packets": "1-1", "interval": "0-1", "length": "50-100"},
    {"packets": "1-1", "interval": "1-1", "length": "100-200"},
    {"packets": "1-1", "interval": "1-2", "length": "200-500"},
    {"packets": "1-2", "interval": "0-1", "length": "10-30"},
    {"packets": "1-2", "interval": "0-1", "length": "50-150"},
    {"packets": "1-2", "interval": "1-1", "length": "100-300"},
    {"packets": "1-2", "interval": "1-2", "length": "200-600"},
    {"packets": "1-3", "interval": "0-1", "length": "20-50"},
    {"packets": "1-3", "interval": "0-1", "length": "50-150"},
    {"packets": "1-3", "interval": "1-1", "length": "100-300"},
    {"packets": "1-3", "interval": "1-2", "length": "300-800"},
    {"packets": "1-5", "interval": "0-1", "length": "50-100"},
    {"packets": "1-5", "interval": "1-1", "length": "100-300"},
    {"packets": "1-5", "interval": "1-2", "length": "200-500"},
    {"packets": "1-5", "interval": "2-5", "length": "500-1000"},
]

CUSTOM_FRAGMENT_PLACEHOLDER = """Examples:
1-3,1-1,1-7
tlshello,1-2,5-10
packets=1-5, interval=2-5, length=1-10

JSON is also supported:
[
  {"packets": "1-3", "interval": "1-1", "length": "1-7"}
]"""

def parse_fragment_variations(text):
    text = text.strip()
    if not text:
        return []
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, list):
        return [_normalize_fragment(item) for item in loaded]

    variations = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            parts = {}
            for item in line.replace(";", ",").split(","):
                if not item.strip():
                    continue
                key, value = item.split("=", 1)
                parts[key.strip()] = value.strip()
            variations.append(_normalize_fragment(parts))
        else:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 3:
                raise ValueError("Use one variation per line: packets,interval,length")
            packets, interval, length = parts
            variations.append(_normalize_fragment({"packets": packets, "interval": interval, "length": length}))
    return variations


def _normalize_fragment(fragment):
    normalized = {
        "packets": str(fragment.get("packets", "")).strip(),
        "interval": str(fragment.get("interval", "")).strip(),
        "length": str(fragment.get("length", "")).strip(),
    }
    if any(not value for value in normalized.values()):
        raise ValueError("Each fragment variation needs packets, interval, and length.")
    return normalized


class RunnerMixin:
    def _custom_fragment_text_to_save(self, value):
        value = value.strip()
        if value == CUSTOM_FRAGMENT_PLACEHOLDER.strip():
            return ""
        return value

    def _build_runner_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        runner_box = ttk.LabelFrame(parent, text="Xray Connection", padding=12)
        runner_box.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        runner_box.columnconfigure(1, weight=1)

        settings = self.runner_settings
        self.runner_ip_var = tk.StringVar(value=settings.ip)
        self.runner_port_var = tk.StringVar(value=settings.port)
        self.runner_share_var = tk.BooleanVar(value=settings.share)
        self.runner_system_proxy_mode_var = tk.StringVar(value=settings.system_proxy_mode)
        self.fragment_enabled_var = tk.BooleanVar(value=DEFAULT_FRAGMENT_ENABLED)
        self.fragment_packets_var = tk.StringVar(value=settings.fragment_packets)
        self.fragment_interval_var = tk.StringVar(value=settings.fragment_interval)
        self.fragment_length_var = tk.StringVar(value=settings.fragment_length)
        self.runner_status_var = tk.StringVar(value="Stopped")

        self.runner_download_result_var = tk.StringVar(value="Not tested")
        self.runner_upload_result_var = tk.StringVar(value="Not tested")
        self.runner_speed_size_var = tk.StringVar(value=settings.speed_size_mb)
        self.runner_speed_timeout_var = tk.StringVar(value=settings.speed_timeout_ms)
        self.runner_fragment_scan_mode_var = tk.StringVar(value=settings.fragment_scan_mode)
        self.runner_fragment_scan_result_var = tk.StringVar(value="Not scanned")
        self.runner_custom_fragments_text = settings.custom_fragments_text

        ttk.Label(runner_box, text="Target IP").grid(row=0, column=0, sticky="w")
        self.runner_ip_entry = ttk.Entry(runner_box, textvariable=self.runner_ip_var, width=28)
        self.runner_ip_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 16),
        )
        ttk.Label(runner_box, text="SOCKS port").grid(row=0, column=2, sticky="w")
        self.runner_port_entry = ttk.Entry(runner_box, textvariable=self.runner_port_var, width=10)
        self.runner_port_entry.grid(
            row=0,
            column=3,
            sticky="w",
            padx=(8, 0),
        )
        self.runner_share_check = ttk.Checkbutton(
            runner_box,
            text="Allow LAN access (listen on 0.0.0.0)",
            variable=self.runner_share_var,
        )
        self.runner_share_check.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Label(runner_box, text="System proxy action").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.runner_system_proxy_combo = ttk.Combobox(
            runner_box,
            textvariable=self.runner_system_proxy_mode_var,
            values=SYSTEM_PROXY_OPTIONS,
            state="readonly",
            width=28,
        )
        self.runner_system_proxy_combo.grid(row=2, column=1, sticky="w", pady=(10, 0))

        fragment_box = ttk.LabelFrame(runner_box, text="Fragmentation", padding=10)
        fragment_box.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        for index in range(6):
            fragment_box.columnconfigure(index, weight=1 if index % 2 else 0)
        self.fragment_enabled_check = ttk.Checkbutton(
            fragment_box,
            text="Enable fragmentation",
            variable=self.fragment_enabled_var,
            command=self._sync_fragment_state,
        )
        self.fragment_enabled_check.grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(fragment_box, text="Packets").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.fragment_packets_entry = ttk.Entry(fragment_box, textvariable=self.fragment_packets_var, width=12)
        self.fragment_packets_entry.grid(
            row=1,
            column=1,
            sticky="w",
            padx=(8, 16),
            pady=(8, 0),
        )
        ttk.Label(fragment_box, text="Interval (ms)").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.fragment_interval_entry = ttk.Entry(fragment_box, textvariable=self.fragment_interval_var, width=12)
        self.fragment_interval_entry.grid(
            row=1,
            column=3,
            sticky="w",
            padx=(8, 16),
            pady=(8, 0),
        )
        ttk.Label(fragment_box, text="Length (bytes)").grid(row=1, column=4, sticky="w", pady=(8, 0))
        self.fragment_length_entry = ttk.Entry(fragment_box, textvariable=self.fragment_length_var, width=12)
        self.fragment_length_entry.grid(
            row=1,
            column=5,
            sticky="w",
            padx=(8, 0),
            pady=(8, 0),
        )
        self._sync_fragment_state()

        buttons = ttk.Frame(runner_box)
        buttons.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.runner_start_button = ttk.Button(buttons, text="Start Xray", command=self.start_xray_runner)
        self.runner_start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.runner_stop_button = ttk.Button(
            buttons,
            text="Stop Xray",
            command=self.stop_xray_runner,
            state="disabled",
        )
        self.runner_stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(runner_box, textvariable=self.runner_status_var).grid(
            row=5,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(10, 0),
        )

        speed_box = ttk.LabelFrame(runner_box, text="Selected IP Speed Test", padding=10)
        speed_box.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        speed_box.columnconfigure(0, weight=1)
        speed_box.columnconfigure(1, weight=1)

        speed_settings = ttk.Frame(speed_box)
        speed_settings.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(speed_settings, text="Test size (MB)").grid(row=0, column=0, sticky="w")
        self.runner_speed_size_entry = ttk.Entry(speed_settings, textvariable=self.runner_speed_size_var, width=8)
        self.runner_speed_size_entry.grid(row=0, column=1, sticky="w", padx=(8, 14))
        ttk.Label(speed_settings, text="Timeout (ms)").grid(row=0, column=2, sticky="w")
        self.runner_speed_timeout_entry = ttk.Entry(
            speed_settings,
            textvariable=self.runner_speed_timeout_var,
            width=10,
        )
        self.runner_speed_timeout_entry.grid(row=0, column=3, sticky="w", padx=(8, 0))

        self.runner_download_button = ttk.Button(
            speed_box,
            text="Test Download",
            command=lambda: self.start_runner_speed_test("download"),
        )
        self.runner_download_button.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.runner_upload_button = ttk.Button(
            speed_box,
            text="Test Upload",
            command=lambda: self.start_runner_speed_test("upload"),
        )
        self.runner_upload_button.grid(row=1, column=1, sticky="ew", padx=(6, 0))

        download_result = ttk.LabelFrame(speed_box, text="Download Speed", padding=8)
        download_result.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        ttk.Label(download_result, textvariable=self.runner_download_result_var).pack(anchor="w")
        upload_result = ttk.LabelFrame(speed_box, text="Upload Speed", padding=8)
        upload_result.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))
        ttk.Label(upload_result, textvariable=self.runner_upload_result_var).pack(anchor="w")

        fragment_scan_box = ttk.LabelFrame(speed_box, text="Fragment Scan", padding=8)
        fragment_scan_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        fragment_scan_box.columnconfigure(2, weight=1)
        ttk.Radiobutton(
            fragment_scan_box,
            text="Optimize download",
            variable=self.runner_fragment_scan_mode_var,
            value="download",
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            fragment_scan_box,
            text="Optimize upload",
            variable=self.runner_fragment_scan_mode_var,
            value="upload",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.runner_fragment_scan_button = ttk.Button(
            fragment_scan_box,
            text="Start Fragment Scan",
            command=self.start_runner_fragment_scan,
        )
        self.runner_fragment_scan_button.grid(row=0, column=2, sticky="e")
        self.runner_fragment_scan_stop_button = ttk.Button(
            fragment_scan_box,
            text="Stop Fragment Scan",
            command=self.stop_runner_fragment_scan,
            state="disabled",
        )
        self.runner_fragment_scan_stop_button.grid(row=0, column=3, sticky="e", padx=(8, 0))
        ttk.Button(
            fragment_scan_box,
            text="Edit Variations",
            command=self.open_custom_fragment_variations_modal,
        ).grid(row=0, column=4, sticky="e", padx=(8, 0))
        ttk.Button(
            fragment_scan_box,
            text="Apply Best Saved Result",
            command=self.apply_saved_best_fragment,
        ).grid(row=0, column=5, sticky="e", padx=(8, 0))
        ttk.Label(fragment_scan_box, textvariable=self.runner_fragment_scan_result_var).grid(
            row=1,
            column=0,
            columnspan=6,
            sticky="w",
            pady=(8, 0),
        )
        self.runner_fragment_results = ttk.Treeview(
            fragment_scan_box,
            columns=("rank", "latency", "speed", "packets", "interval", "length"),
            show="headings",
            height=5,
        )
        for column, label, width in (
            ("rank", "#", 40),
            ("latency", "Latency (ms)", 90),
            ("speed", "Speed (Mbps)", 95),
            ("packets", "Packets", 90),
            ("interval", "Interval", 90),
            ("length", "Length", 90),
        ):
            self.runner_fragment_results.heading(
                column,
                text=label,
                command=lambda col=column: self._sort_runner_fragment_results_by_column(col),
            )
            self.runner_fragment_results.column(column, width=width, anchor="w")
        self.runner_fragment_results.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))

        ttk.Label(parent, text="Xray Activity Log").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        log_frame = ttk.Frame(parent)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.runner_log = tk.Text(log_frame, height=18, wrap="word")
        self.runner_log.grid(row=0, column=0, sticky="nsew")
        runner_log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.runner_log.yview)
        self.runner_log.configure(yscrollcommand=runner_log_scroll.set)
        runner_log_scroll.grid(row=0, column=1, sticky="ns")

    def _sync_fragment_state(self):
        if self._runner_is_active():
            state = "disabled"
        else:
            state = "normal" if self.fragment_enabled_var.get() else "disabled"
        for entry in (self.fragment_packets_entry, self.fragment_interval_entry, self.fragment_length_entry):
            entry.configure(state=state)

    def _set_runner_config_state(self, running):
        state = "disabled" if running else "normal"
        for name in (
            "runner_ip_entry",
            "runner_port_entry",
            "runner_share_check",
            "runner_system_proxy_combo",
            "fragment_enabled_check",
        ):
            widget = self.__dict__.get(name)
            if widget is None:
                continue
            widget.configure(state=state)
        if running:
            for name in ("fragment_packets_entry", "fragment_interval_entry", "fragment_length_entry"):
                widget = self.__dict__.get(name)
                if widget is not None:
                    widget.configure(state="disabled")
        elif "fragment_packets_entry" in self.__dict__:
            self._sync_fragment_state()

    def _set_runner_speed_state(self, running):
        state = "disabled" if running or self.profile is None else "normal"
        if "runner_download_button" in self.__dict__:
            self.runner_download_button.configure(state=state)
        if "runner_upload_button" in self.__dict__:
            self.runner_upload_button.configure(state=state)
        if "runner_fragment_scan_button" in self.__dict__:
            self.runner_fragment_scan_button.configure(state=state)
        if "runner_fragment_scan_stop_button" in self.__dict__:
            self.runner_fragment_scan_stop_button.configure(state="normal" if running else "disabled")
        if "runner_speed_size_entry" in self.__dict__:
            self.runner_speed_size_entry.configure(state=state)
        if "runner_speed_timeout_entry" in self.__dict__:
            self.runner_speed_timeout_entry.configure(state=state)

    def run_selected_ip_with_xray(self):
        ip = self._selected_single_ip()
        if not ip:
            return
        self.runner_ip_var.set(ip)
        self.notebook.select(self.runner_tab)
        self.start_xray_runner(ip)

    def _runner_is_active(self):
        return self.runner_process is not None and self.runner_process.poll() is None

    def _runner_port(self):
        try:
            port = int(self.runner_port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid SOCKS Port", "Enter a SOCKS port between 1 and 65535.")
            return None
        return port

    def _runner_fragment_settings(self):
        if not self.fragment_enabled_var.get():
            return {}
        fragment = {
            "packets": self.fragment_packets_var.get().strip(),
            "interval": self.fragment_interval_var.get().strip(),
            "length": self.fragment_length_var.get().strip(),
        }
        if any(not value for value in fragment.values()):
            messagebox.showerror(
                "Fragmentation Settings",
                "Packets, interval, and length are required when fragmentation is enabled.",
            )
            return None
        return fragment

    def _runner_speed_settings(self):
        try:
            size_mb = float(self.runner_speed_size_var.get())
            timeout_ms = int(self.runner_speed_timeout_var.get())
            if size_mb <= 0 or timeout_ms <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Speed Test Settings",
                "Test size and timeout must both be greater than zero.",
            )
            return None
        return int(size_mb * 1024 * 1024), timeout_ms

    def start_xray_runner(self, ip=None):
        profile = self._selected_profile()
        if profile is None:
            return
        if ip:
            self.runner_ip_var.set(ip)
        ip = self.runner_ip_var.get().strip()
        if not ip:
            messagebox.showerror("Target IP Required", "Enter or select an IP address first.")
            return
        port = self._runner_port()
        fragment = self._runner_fragment_settings()
        if port is None or fragment is None:
            return
        if self._runner_is_active():
            self.stop_xray_runner()

        listen = "0.0.0.0" if self.runner_share_var.get() else "127.0.0.1"
        config = make_xray_runner_config(ip, port, listen, profile, fragment)
        temp_dir = tempfile.TemporaryDirectory(prefix="xray-runner-")
        config_path = os.path.join(temp_dir.name, "config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.runner_process = subprocess.Popen(
                [XRAY_EXE, "run", "-config", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=flags,
                bufsize=1,
                text=True,
            )
            self.runner_temp_dir = temp_dir
        except Exception as exc:
            temp_dir.cleanup()
            self.runner_process = None
            self.runner_temp_dir = None
            messagebox.showerror("Xray Startup Error", str(exc))
            return

        self.runner_start_button.configure(state="disabled")
        self.runner_stop_button.configure(state="normal")
        self._set_runner_config_state(True)
        self.runner_status_var.set(f"Running {ip} on {listen}:{port}")
        self._clear_runner_log()
        self._append_runner_log(f"Starting Xray runner for {ip} on {listen}:{port}")
        self._append_runner_log(f"Fragmentation: {'enabled' if fragment else 'disabled'}")
        self._apply_runner_system_proxy_mode(port)
        self._start_runner_log_threads(self.runner_process)
        self._log(f"Xray runner started for {ip} on {listen}:{port}")

    def _apply_runner_system_proxy_mode(self, port):
        mode = self.runner_system_proxy_mode_var.get()
        self.runner_system_proxy_applied = False
        if mode == SYSTEM_PROXY_DO_NOT_TOUCH:
            self._append_runner_log("System proxy unchanged.")
            return
        if mode == SYSTEM_PROXY_CLEAR:
            self._append_runner_log(system_proxy.clear_proxy())
            return
        if mode == SYSTEM_PROXY_SET:
            self._append_runner_log(system_proxy.set_socks_proxy(port))
            self.runner_system_proxy_applied = True
            return
        self._append_runner_log(f"Unknown system proxy mode ignored: {mode}")

    def _clear_runner_system_proxy_if_needed(self):
        if not self.__dict__.get("runner_system_proxy_applied", False):
            return
        self._append_runner_log(system_proxy.clear_proxy())
        self.runner_system_proxy_applied = False

    def start_runner_speed_test(self, speed_mode):
        profile = self._selected_profile()
        speed_settings = self._runner_speed_settings()
        if profile is None or speed_settings is None:
            return
        ip = self.runner_ip_var.get().strip()
        if not ip:
            messagebox.showwarning("Target IP Required", "Enter or select an IP address first.")
            return
        fragment = self._runner_fragment_settings()
        if fragment is None:
            return
        self._set_runner_speed_state(True)
        if speed_mode == "download":
            self.runner_download_result_var.set("Testing...")
        else:
            self.runner_upload_result_var.set("Testing...")
        self._append_runner_log(f"Starting {speed_mode} speed test for {ip}")
        self.runner_speed_thread = threading.Thread(
            target=self._runner_speed_worker,
            args=(ip, profile, speed_mode, speed_settings[0], speed_settings[1], fragment),
            daemon=True,
        )
        self.runner_speed_thread.start()

    def _runner_speed_worker(self, ip, profile, speed_mode, speed_test_bytes, speed_timeout_ms, fragment):
        try:
            result = test_ip(
                ip,
                1,
                1,
                profile,
                speed_mode=speed_mode,
                timeout_ms=speed_timeout_ms,
                speed_test_bytes=speed_test_bytes,
                speed_timeout_ms=speed_timeout_ms,
                fragment=fragment,
                process_started=self._track_process,
                process_finished=self._untrack_process,
            )
        except Exception as exc:
            result = {"ip": ip, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        self.events.put(("runner_speed_result", speed_mode, result))

    def start_runner_fragment_scan(self):
        profile = self._selected_profile()
        speed_settings = self._runner_speed_settings()
        if profile is None or speed_settings is None:
            return
        ip = self.runner_ip_var.get().strip()
        if not ip:
            messagebox.showwarning("Target IP Required", "Enter or select an IP address first.")
            return
        speed_mode = self.runner_fragment_scan_mode_var.get()
        if speed_mode not in ("download", "upload"):
            messagebox.showwarning("Test Direction Required", "Choose download or upload optimization first.")
            return
        variations = self._runner_fragment_scan_variations()
        if not variations:
            return

        self.runner_fragment_scan_stop_event.clear()
        self._set_runner_speed_state(True)
        self._clear_runner_fragment_results()
        self.runner_fragment_scan_rows = []
        self.runner_fragment_sort_column = "rank"
        self.runner_fragment_sort_reverse = False
        self.runner_fragment_scan_result_var.set(f"Scanning {len(variations)} variations...")
        self._append_runner_log(
            f"Starting fragment scan for {ip}: direction={speed_mode}, variations={len(variations)}"
        )
        self.runner_fragment_scan_thread = threading.Thread(
            target=self._runner_fragment_scan_worker,
            args=(ip, profile, speed_mode, speed_settings[0], speed_settings[1], variations),
            daemon=True,
        )
        self.runner_fragment_scan_thread.start()

    def stop_runner_fragment_scan(self):
        self.runner_fragment_scan_stop_event.set()
        self._kill_active_processes()
        self.runner_fragment_scan_result_var.set("Stopping fragment scan...")
        self._append_runner_log("Fragment scan stop requested. The active Xray test process was terminated.")
        if "runner_fragment_scan_stop_button" in self.__dict__:
            self.runner_fragment_scan_stop_button.configure(state="disabled")

    def _runner_fragment_scan_variations(self):
        if not self.runner_custom_fragments_text.strip():
            speed_mode = self.runner_fragment_scan_mode_var.get()
            defaults = UPLOAD_FRAGMENT_SCAN_VARIATIONS if speed_mode == "upload" else FRAGMENT_SCAN_VARIATIONS
            return list(defaults)
        try:
            return parse_fragment_variations(self.runner_custom_fragments_text)
        except ValueError as exc:
            messagebox.showerror("Invalid Fragment Variations", str(exc))
            return None

    def _runner_fragment_scan_worker(self, ip, profile, speed_mode, speed_test_bytes, speed_timeout_ms, variations):
        results = []
        key = "download_mbps" if speed_mode == "download" else "upload_mbps"
        total = len(variations)
        stopped = False
        for index, fragment in enumerate(variations, 1):
            if self.runner_fragment_scan_stop_event.is_set():
                stopped = True
                break
            try:
                result = test_ip(
                    ip,
                    index,
                    total,
                    profile,
                    speed_mode=speed_mode,
                    timeout_ms=speed_timeout_ms,
                    speed_test_bytes=speed_test_bytes,
                    speed_timeout_ms=speed_timeout_ms,
                    fragment=fragment,
                    process_started=self._track_process,
                    process_finished=self._untrack_process,
                )
            except Exception as exc:
                result = {"ip": ip, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            value = result.get(key, -1) if result.get("ok") else -1
            results.append({"fragment": fragment, "value": value, "result": result})
            self.events.put(("runner_fragment_scan_progress", index, total, speed_mode, fragment, value))
            if self.runner_fragment_scan_stop_event.is_set():
                stopped = True
                break

        best = self._best_fragment_scan_result(results)
        if best:
            self.events.put(
                (
                    "runner_fragment_scan_result",
                    speed_mode,
                    ip,
                    profile.name,
                    best["fragment"],
                    best["value"],
                    results,
                    stopped,
                )
            )
        else:
            self.events.put(("runner_fragment_scan_result", speed_mode, ip, profile.name, None, -1, results, stopped))

    def _best_fragment_scan_result(self, results):
        working = [item for item in results if item["value"] >= 0]
        if not working:
            return None
        return max(working, key=lambda item: (item["value"], -int(item["result"].get("ms", 999999))))

    def _start_runner_log_threads(self, proc):
        self.runner_output_threads = []
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._read_runner_stream,
                args=(proc, name, stream),
                daemon=True,
            )
            thread.start()
            self.runner_output_threads.append(thread)
        waiter = threading.Thread(target=self._watch_runner_process, args=(proc,), daemon=True)
        waiter.start()
        self.runner_output_threads.append(waiter)

    def _read_runner_stream(self, proc, name, stream):
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip()
                if line:
                    self.events.put(("runner_log", f"[{name}] {line}"))
        except Exception as exc:
            self.events.put(("runner_log", f"[{name}] log read failed: {type(exc).__name__}: {exc}"))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _watch_runner_process(self, proc):
        try:
            code = proc.wait()
        except Exception as exc:
            self.events.put(("runner_log", f"Xray process wait failed: {type(exc).__name__}: {exc}"))
            return
        self.events.put(("runner_exit", proc, code))

    def _clear_runner_log(self):
        if "runner_log" in self.__dict__:
            self.runner_log.delete("1.0", "end")

    def _append_runner_log(self, message):
        if "runner_log" not in self.__dict__:
            return
        self.runner_log.insert("end", message + "\n")
        self.runner_log.see("end")

    def _cleanup_runner_temp_dir(self):
        if self.runner_temp_dir is not None:
            self.runner_temp_dir.cleanup()
            self.runner_temp_dir = None

    def stop_xray_runner(self):
        proc = self.runner_process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.runner_process = None
        self._cleanup_runner_temp_dir()
        self._clear_runner_system_proxy_if_needed()
        if "runner_start_button" in self.__dict__:
            self.runner_start_button.configure(state="normal" if self.profile is not None else "disabled")
            self.runner_stop_button.configure(state="disabled")
            self._set_runner_config_state(False)
            self._set_runner_speed_state(False)
            self.runner_status_var.set("Stopped")
            self._append_runner_log("Xray runner stopped.")
        if "log" in self.__dict__:
            self._log("Xray runner stopped.")

    def _handle_runner_exit(self, proc, code):
        if proc is not self.runner_process:
            return
        self.runner_process = None
        self._cleanup_runner_temp_dir()
        self.runner_start_button.configure(state="normal" if self.profile is not None else "disabled")
        self.runner_stop_button.configure(state="disabled")
        self._set_runner_config_state(False)
        self._set_runner_speed_state(False)
        self.runner_status_var.set(f"Stopped. Xray exited with code {code}.")
        self._append_runner_log(f"Xray exited with code {code}.")

    def _handle_runner_speed_result(self, speed_mode, result):
        key = "download_mbps" if speed_mode == "download" else "upload_mbps"
        value = result.get(key, -1)
        target_var = self.runner_download_result_var if speed_mode == "download" else self.runner_upload_result_var
        target_var.set(f"{value} Mbps" if value != -1 else "-1")
        if result.get("ok"):
            self._append_runner_log(f"{speed_mode.title()} speed test passed: {value} Mbps")
            for warning in result.get("speed_warnings", []):
                self._append_runner_log(f"WARNING {warning}")
        else:
            self._append_runner_log(f"{speed_mode.title()} speed test failed: {result.get('error', '')}")
            if result.get("speed_debug"):
                self._append_runner_log(f"DEBUG {result['speed_debug']}")
        self._set_runner_speed_state(False)

    def _handle_runner_fragment_scan_progress(self, index, total, speed_mode, fragment, value):
        summary = self._fragment_summary(fragment)
        self.runner_fragment_scan_result_var.set(f"{index}/{total}: {summary} -> {value} Mbps")
        self._append_runner_log(f"Fragment scan {index}/{total} {speed_mode}: {summary} -> {value} Mbps")
        if "runner_fragment_results" in self.__dict__:
            self.runner_fragment_scan_rows.append(
                {"fragment": fragment, "value": value, "result": {}, "scan_index": index}
            )
            self._render_runner_fragment_results(self.runner_fragment_scan_rows)

    def _handle_runner_fragment_scan_result(self, speed_mode, ip, config_name, fragment, value, results, stopped=False):
        out_path = save_fragment_scan_results(ip, config_name, speed_mode, results)
        self.runner_fragment_scan_rows = list(results)
        self._render_runner_fragment_results(results)
        if fragment is None:
            label = (
                "Fragment scan stopped. No successful variation was found."
                if stopped
                else "No successful fragment variation was found."
            )
            self.runner_fragment_scan_result_var.set(label)
            self._append_runner_log(f"{label} Saved results to {out_path}")
            self._set_runner_speed_state(False)
            return

        best_result = next((item["result"] for item in results if item["fragment"] == fragment), {})
        latency = best_result.get("ms", -1)
        save_best_fragment(ip, config_name, speed_mode, fragment, value, latency)
        self.fragment_enabled_var.set(True)
        self.fragment_packets_var.set(fragment["packets"])
        self.fragment_interval_var.set(fragment["interval"])
        self.fragment_length_var.set(fragment["length"])
        self._sync_fragment_state()
        summary = self._fragment_summary(fragment)
        prefix = "Stopped. Best" if stopped else "Best"
        self.runner_fragment_scan_result_var.set(
            f"{prefix} {speed_mode}: {value} Mbps, latency={latency} ms | {summary}"
        )
        self._append_runner_log(
            f"Fragment scan {prefix.lower()} {speed_mode}: {value} Mbps, latency={latency} ms | {summary}"
        )
        self._append_runner_log(f"Saved fragment scan results to {out_path}")
        self._set_runner_speed_state(False)

    def _clear_runner_fragment_results(self):
        if "runner_fragment_results" not in self.__dict__:
            return
        for item in self.runner_fragment_results.get_children():
            self.runner_fragment_results.delete(item)

    def _render_runner_fragment_results(self, results):
        self._clear_runner_fragment_results()
        sorted_results = self._sorted_runner_fragment_results(results)
        for index, item in enumerate(sorted_results, 1):
            fragment = item["fragment"]
            result = item.get("result", {})
            self.runner_fragment_results.insert(
                "",
                "end",
                values=(
                    index,
                    result.get("ms", -1),
                    item.get("value", -1),
                    fragment["packets"],
                    fragment["interval"],
                    fragment["length"],
                ),
            )

    def _sort_runner_fragment_results_by_column(self, column):
        current_column = self.__dict__.get("runner_fragment_sort_column", "rank")
        current_reverse = self.__dict__.get("runner_fragment_sort_reverse", False)
        if current_column == column:
            self.runner_fragment_sort_reverse = not current_reverse
        else:
            self.runner_fragment_sort_column = column
            self.runner_fragment_sort_reverse = column in ("speed",)
        self._render_runner_fragment_results(self.runner_fragment_scan_rows)

    def _sorted_runner_fragment_results(self, results):
        return sorted(
            results,
            key=lambda item: self._runner_fragment_sort_value(
                item,
                self.__dict__.get("runner_fragment_sort_column", "rank"),
            ),
            reverse=self.__dict__.get("runner_fragment_sort_reverse", False),
        )

    def _runner_fragment_sort_value(self, item, column):
        fragment = item["fragment"]
        if column == "rank":
            return item.get("scan_index", 0)
        if column == "latency":
            return int(item.get("result", {}).get("ms", 999999))
        if column == "speed":
            return float(item.get("value", -1))
        return fragment.get(column, "")

    def apply_saved_best_fragment(self):
        profile = self._selected_profile()
        if profile is None:
            return
        ip = self.runner_ip_var.get().strip()
        if not ip:
            messagebox.showwarning("Target IP Required", "Enter or select an IP address first.")
            return
        speed_mode = self.runner_fragment_scan_mode_var.get()
        saved = get_best_fragment(ip, profile.name, speed_mode)
        if not saved:
            messagebox.showinfo(
                "No Saved Result",
                "No saved fragment result exists for this IP, configuration, and test direction.",
            )
            return
        fragment = saved["fragment"]
        should_restart = self._runner_is_active()
        if should_restart:
            self.stop_xray_runner()
        self.fragment_enabled_var.set(True)
        self.fragment_packets_var.set(fragment["packets"])
        self.fragment_interval_var.set(fragment["interval"])
        self.fragment_length_var.set(fragment["length"])
        self._sync_fragment_state()
        self.runner_fragment_scan_result_var.set(
            f"Applied saved {speed_mode}: {saved.get('speed_mbps', -1)} Mbps, "
            f"latency={saved.get('latency_ms', -1)} ms"
        )
        self._append_runner_log(f"Applied saved fragment: {self._fragment_summary(fragment)}")
        if should_restart:
            self._append_runner_log("Restarting Xray with saved fragment.")
            self.start_xray_runner(ip)

    def open_custom_fragment_variations_modal(self):
        modal = tk.Toplevel(self)
        modal.title("Fragment Scan Variations")
        modal.geometry("640x420")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        frame = ttk.Frame(modal, padding=12)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, height=16, wrap="word")
        text.pack(fill="both", expand=True)
        placeholder_active = {"active": False}

        def show_placeholder():
            placeholder_active["active"] = True
            text.configure(foreground="#777777")
            text.delete("1.0", "end")
            text.insert("1.0", CUSTOM_FRAGMENT_PLACEHOLDER)

        def hide_placeholder(_event=None):
            if placeholder_active["active"]:
                placeholder_active["active"] = False
                text.configure(foreground="black")
                text.delete("1.0", "end")

        def restore_placeholder(_event=None):
            if not text.get("1.0", "end").strip():
                show_placeholder()

        if self.runner_custom_fragments_text.strip():
            text.insert("1.0", self.runner_custom_fragments_text)
        else:
            show_placeholder()
        text.bind("<FocusIn>", hide_placeholder)
        text.bind("<FocusOut>", restore_placeholder)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))

        def load_file():
            path = filedialog.askopenfilename(
                title="Load Fragment Variations",
                filetypes=(("Text/JSON", "*.txt *.json *.config"), ("All files", "*.*")),
            )
            if not path:
                return
            with open(path, "r", encoding="utf-8") as f:
                placeholder_active["active"] = False
                text.configure(foreground="black")
                text.delete("1.0", "end")
                text.insert("1.0", f.read())

        def save():
            value = self._custom_fragment_text_to_save(text.get("1.0", "end"))
            if value:
                try:
                    parse_fragment_variations(value)
                except ValueError as exc:
                    messagebox.showerror("Invalid Fragment Variations", str(exc))
                    return
            self.runner_custom_fragments_text = value
            modal.destroy()

        ttk.Button(buttons, text="Load from File", command=load_file).pack(side="left")
        ttk.Button(buttons, text="Save Variations", command=save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=modal.destroy).pack(side="right", padx=(0, 8))

    def _fragment_summary(self, fragment):
        return (
            f"packets={fragment['packets']}, "
            f"interval={fragment['interval']}, "
            f"length={fragment['length']}"
        )

    def _current_runner_settings(self):
        return RunnerSettings(
            ip=self.runner_ip_var.get().strip(),
            port=str(self.runner_port_var.get()).strip(),
            share=bool(self.runner_share_var.get()),
            system_proxy_mode=self.runner_system_proxy_mode_var.get(),
            fragment_enabled=DEFAULT_FRAGMENT_ENABLED,
            fragment_packets=self.fragment_packets_var.get().strip(),
            fragment_interval=self.fragment_interval_var.get().strip(),
            fragment_length=self.fragment_length_var.get().strip(),
            speed_size_mb=str(self.runner_speed_size_var.get()).strip(),
            speed_timeout_ms=str(self.runner_speed_timeout_var.get()).strip(),
            fragment_scan_mode=self.runner_fragment_scan_mode_var.get(),
            custom_fragments_text=self.runner_custom_fragments_text,
        )

    def _save_runner_settings(self):
        save_runner_settings(self._current_runner_settings())

    def on_close(self):
        try:
            self._save_runner_settings()
        except OSError as exc:
            self._append_runner_log(f"Could not save runner settings: {exc}")
        self.stop_current()
        self.stop_xray_runner()
        self.destroy()

