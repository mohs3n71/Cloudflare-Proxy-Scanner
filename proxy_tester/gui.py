import queue
import threading
import tkinter as tk
from tkinter import ttk

from . import cloudflare
from .gui_about import AboutMixin
from .gui_config import ConfigMixin
from .gui_runner import RunnerMixin
from .gui_table import TableMixin
from .gui_utils import merge_rows_by_ip, numeric_sort_value, table_sort_value
from .gui_workers import WorkerMixin
from .settings import AppSettings, CONCURRENCY_OPTIONS, DEFAULT_FRAGMENT_ENABLED, load_runner_settings
from .storage import ensure_project_dirs
from .xray import DEFAULT_SPEED_TEST_BYTES, DEFAULT_SPEED_TEST_TIMEOUT_MS



WINDOW_WIDTH = 1220
WINDOW_HEIGHT = 1020
LEFT_PANEL_WIDTH = 460
LEFT_PANEL_MIN_WIDTH = 450
LEFT_PANEL_MIN_HEIGHT = 990


class ProxyTesterGui(AboutMixin, ConfigMixin, RunnerMixin, TableMixin, WorkerMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_project_dirs()
        self.title("Proxy Tester")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)

        self.settings = AppSettings()
        self.runner_settings = load_runner_settings()
        self.profile = None
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.active_processes = set()
        self.active_processes_lock = threading.Lock()
        self.events = queue.Queue()
        self.passed_results = []
        self.table_items_by_ip = {}
        self.active_test_ips = set()
        self.sort_column = "ping"
        self.sort_reverse = False
        self.loaded_output_path = None
        self.current_log_path = None
        self.runner_process = None
        self.runner_temp_dir = None
        self.runner_system_proxy_applied = False
        self.runner_output_threads = []
        self.runner_speed_thread = None
        self.runner_fragment_scan_thread = None
        self.runner_fragment_scan_stop_event = threading.Event()
        self.runner_fragment_scan_rows = []
        self.runner_fragment_sort_column = "rank"
        self.runner_fragment_sort_reverse = False

        self._build_ui()
        self._load_configs()
        self._load_outputs()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._drain_events)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        scanner_tab = ttk.Frame(self.notebook)
        self.runner_tab = ttk.Frame(self.notebook)
        self.about_tab = ttk.Frame(self.notebook)
        self.notebook.add(scanner_tab, text="IP Scanner")
        self.notebook.add(self.runner_tab, text="Xray Runner")
        self.notebook.add(self.about_tab, text="About")

        scanner_tab.columnconfigure(0, weight=0)
        scanner_tab.columnconfigure(1, weight=1)
        scanner_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(scanner_tab, padding=12, width=LEFT_PANEL_WIDTH)
        left.grid(row=0, column=0, sticky="ns")
        left.grid_propagate(False)

        right = ttk.Frame(scanner_tab, padding=(0, 12, 12, 12))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        config_box = ttk.LabelFrame(left, text="Proxy Configuration", padding=10)
        config_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        config_box.columnconfigure(0, weight=1)
        ttk.Label(config_box, text="Configuration file").grid(row=0, column=0, sticky="w")
        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(config_box, textvariable=self.config_var, state="readonly", width=42)
        self.config_combo.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.config_combo.bind("<<ComboboxSelected>>", lambda _event: self._select_config())
        ttk.Button(config_box, text="Add Configuration", command=self.open_add_config_modal).grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(6, 0),
        )

        scan_box = ttk.LabelFrame(left, text="Cloudflare IP Scan", padding=10)
        scan_box.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        scan_box.columnconfigure(0, weight=1)

        ttk.Label(scan_box, text="IP selection").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="all")
        ttk.Radiobutton(
            scan_box,
            text="Random IPs from all Cloudflare ranges",
            variable=self.mode_var,
            value="all",
            command=self._sync_range_state,
        ).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(
            scan_box,
            text="Every IP in all Cloudflare ranges",
            variable=self.mode_var,
            value="all_full",
            command=self._sync_range_state,
        ).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(
            scan_box,
            text="Random IPs from one Cloudflare range",
            variable=self.mode_var,
            value="range",
            command=self._sync_range_state,
        ).grid(row=3, column=0, sticky="w")

        ttk.Label(scan_box, text="Cloudflare range").grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.range_var = tk.StringVar()
        self.range_combo = ttk.Combobox(scan_box, textvariable=self.range_var, state="readonly", width=42)
        self.range_combo.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        ranges = cloudflare.networks()
        self.ranges_by_label = {
            f"{net} ({cloudflare.usable_hosts(net)} usable IPs)": net for net in ranges
        }
        self.range_combo["values"] = list(self.ranges_by_label)
        if self.range_combo["values"]:
            self.range_combo.current(0)

        ttk.Label(scan_box, text="Number of IPs").grid(row=6, column=0, sticky="w")
        self.count_var = tk.StringVar(value="100")
        self.count_entry = ttk.Entry(scan_box, textvariable=self.count_var, width=18)
        self.count_entry.grid(row=7, column=0, sticky="w", pady=(4, 6))
        self._sync_range_state()
        scan_settings = ttk.Frame(scan_box)
        scan_settings.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(scan_settings, text="Concurrent tests").grid(row=0, column=0, sticky="w")
        self.concurrency_var = tk.IntVar(value=self.settings.concurrency)
        ttk.Combobox(
            scan_settings,
            textvariable=self.concurrency_var,
            values=CONCURRENCY_OPTIONS,
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=(8, 14))
        ttk.Label(scan_settings, text="Timeout (ms)").grid(row=0, column=2, sticky="w")
        self.timeout_var = tk.StringVar(value=str(self.settings.timeout_ms))
        ttk.Entry(scan_settings, textvariable=self.timeout_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 0))
        self.auto_speed_after_scan_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            scan_box,
            text="Run speed test after scan",
            variable=self.auto_speed_after_scan_var,
        ).grid(row=9, column=0, sticky="w", pady=(0, 6))
        self.start_button = ttk.Button(scan_box, text="Start Scan", command=self.start_scan)
        self.start_button.grid(row=10, column=0, sticky="ew")
        self.stop_scan_button = ttk.Button(scan_box, text="Stop Scan", command=self.stop_current, state="disabled")
        self.stop_scan_button.grid(row=11, column=0, sticky="ew", pady=(6, 0))

        output_box = ttk.LabelFrame(left, text="Saved Results and Speed Test", padding=10)
        output_box.grid(row=2, column=0, sticky="ew")
        output_box.columnconfigure(0, weight=1)
        ttk.Label(output_box, text="Results file").grid(row=0, column=0, sticky="w")
        self.output_var = tk.StringVar()
        self.output_combo = ttk.Combobox(output_box, textvariable=self.output_var, state="readonly", width=38)
        self.output_combo.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.output_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_selected_output_into_table())
        self.refresh_outputs_button = ttk.Button(output_box, text="Refresh File List", command=self._load_outputs)
        self.refresh_outputs_button.grid(row=2, column=0, sticky="ew")

        self.speed_mode_var = tk.StringVar(value="download")
        ttk.Label(output_box, text="Test direction").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Radiobutton(output_box, text="Download", variable=self.speed_mode_var, value="download").grid(
            row=4, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Radiobutton(output_box, text="Upload", variable=self.speed_mode_var, value="upload").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Radiobutton(output_box, text="Download and upload", variable=self.speed_mode_var, value="both").grid(
            row=6, column=0, sticky="w"
        )
        speed_settings = ttk.Frame(output_box)
        speed_settings.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(speed_settings, text="Test size (MB)").grid(row=0, column=0, sticky="w")
        self.speed_size_var = tk.StringVar(value=str(DEFAULT_SPEED_TEST_BYTES // (1024 * 1024)))
        ttk.Entry(speed_settings, textvariable=self.speed_size_var, width=8).grid(row=0, column=1, sticky="w", padx=(8, 14))
        ttk.Label(speed_settings, text="Timeout (ms)").grid(row=0, column=2, sticky="w")
        self.speed_timeout_var = tk.StringVar(value=str(DEFAULT_SPEED_TEST_TIMEOUT_MS))
        ttk.Entry(speed_settings, textvariable=self.speed_timeout_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 0))

        speed_fragment_box = ttk.LabelFrame(output_box, text="Speed Test Fragmentation", padding=8)
        speed_fragment_box.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        for index in range(6):
            speed_fragment_box.columnconfigure(index, weight=1 if index % 2 else 0)
        self.speed_fragment_enabled_var = tk.BooleanVar(value=DEFAULT_FRAGMENT_ENABLED)
        self.speed_fragment_packets_var = tk.StringVar(value="1-3")
        self.speed_fragment_interval_var = tk.StringVar(value="1-1")
        self.speed_fragment_length_var = tk.StringVar(value="1-7")
        self.speed_fragment_enabled_check = ttk.Checkbutton(
            speed_fragment_box,
            text="Enable fragmentation",
            variable=self.speed_fragment_enabled_var,
            command=self._sync_speed_fragment_state,
        )
        self.speed_fragment_enabled_check.grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(speed_fragment_box, text="Packets").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.speed_fragment_packets_entry = ttk.Entry(
            speed_fragment_box,
            textvariable=self.speed_fragment_packets_var,
            width=8,
        )
        self.speed_fragment_packets_entry.grid(row=1, column=1, sticky="w", padx=(6, 10), pady=(6, 0))
        ttk.Label(speed_fragment_box, text="Interval (ms)").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.speed_fragment_interval_entry = ttk.Entry(
            speed_fragment_box,
            textvariable=self.speed_fragment_interval_var,
            width=8,
        )
        self.speed_fragment_interval_entry.grid(row=1, column=3, sticky="w", padx=(6, 10), pady=(6, 0))
        ttk.Label(speed_fragment_box, text="Length (bytes)").grid(row=1, column=4, sticky="w", pady=(6, 0))
        self.speed_fragment_length_entry = ttk.Entry(
            speed_fragment_box,
            textvariable=self.speed_fragment_length_var,
            width=8,
        )
        self.speed_fragment_length_entry.grid(row=1, column=5, sticky="w", padx=(6, 0), pady=(6, 0))
        self._sync_speed_fragment_state()

        self.speed_button = ttk.Button(
            output_box,
            text="Test Selected Results",
            command=self.start_speed_test,
        )
        self.speed_button.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        self.stop_speed_button = ttk.Button(
            output_box,
            text="Stop Speed Test",
            command=self.stop_current,
            state="disabled",
        )
        self.stop_speed_button.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        self.proxy_config_button = ttk.Button(
            output_box,
            text="Generate Proxy Configurations",
            command=self.create_proxy_configs,
        )
        self.proxy_config_button.grid(row=11, column=0, sticky="ew", pady=(6, 0))
        self.remove_failed_button = ttk.Button(
            output_box,
            text="Remove Failed Results (-1)",
            command=self.remove_failed_rows,
        )
        self.remove_failed_button.grid(row=12, column=0, sticky="ew", pady=(6, 0))

        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(top, maximum=100)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 10))

        self.table = ttk.Treeview(
            right,
            columns=("ping", "ip", "download", "upload"),
            show="headings",
            height=14,
            selectmode="extended",
        )
        for column, label, width in (
            ("ping", "Latency (ms)", 90),
            ("ip", "IP", 150),
            ("download", "Download (Mbps)", 115),
            ("upload", "Upload (Mbps)", 110),
        ):
            self.table.heading(column, text=label, command=lambda col=column: self._sort_by_column(col))
            self.table.column(column, width=width, anchor="w")
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tag_configure("active", background="#fff2a8")
        table_scroll = ttk.Scrollbar(right, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=table_scroll.set)
        table_scroll.grid(row=1, column=1, sticky="ns")
        self.table.bind("<Button-3>", self.open_table_context_menu)
        self.table.bind("<Button-2>", self.open_table_context_menu)
        self.table_menu = tk.Menu(self, tearoff=0)
        self.table_menu_speed_download_index = 0
        self.table_menu_speed_upload_index = 1
        self.table_menu_speed_both_index = 2
        self.table_menu_run_xray_index = 4
        self.table_menu_copy_ip_index = 5
        self.table_menu_copy_config_index = 6
        self.table_menu_qr_config_index = 7
        self.table_menu.add_command(
            label="Test Download Speed",
            command=lambda: self.start_speed_test_for_selected("download"),
        )
        self.table_menu.add_command(
            label="Test Upload Speed",
            command=lambda: self.start_speed_test_for_selected("upload"),
        )
        self.table_menu.add_command(
            label="Test Download and Upload",
            command=lambda: self.start_speed_test_for_selected("both"),
        )
        self.table_menu.add_separator()
        self.table_menu.add_command(label="Run Selected IP with Xray", command=self.run_selected_ip_with_xray)
        self.table_menu.add_command(label="Copy IP", command=self.copy_selected_ip)
        self.table_menu.add_command(label="Copy Proxy Configuration", command=self.copy_selected_config)
        self.table_menu.add_command(label="Show Configuration QR Code", command=self.show_selected_config_qr)

        ttk.Label(right, text="Activity Log").grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.log = tk.Text(right, height=12, wrap="word")
        self.log.grid(row=3, column=0, sticky="nsew")
        self._build_runner_tab(self.runner_tab)
        self._build_about_tab(self.about_tab)

def main():
    app = ProxyTesterGui()
    app.mainloop()


if __name__ == "__main__":
    main()
