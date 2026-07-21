import tkinter as tk
from tkinter import messagebox, ttk

from . import cloudflare
from .custom_ranges import custom_ranges_text, parse_custom_ranges
from .settings import save_custom_range_values


CUSTOM_RANGES_PLACEHOLDER = """One IPv4 range per line. Examples:
104.16.0.0/13
172.64.0.0/13
198.51.100.25

Bare IP addresses are saved as /32 ranges."""


class CustomRangeMixin:
    def open_custom_ranges_modal(self):
        modal = tk.Toplevel(self)
        modal.title("Custom IP Ranges")
        modal.geometry("600x420")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        frame = ttk.Frame(modal, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="IPv4 ranges (CIDR notation)").pack(anchor="w")
        text = tk.Text(frame, height=16, wrap="none")
        text.pack(fill="both", expand=True, pady=(6, 10))
        current = custom_ranges_text(self.custom_networks)
        text.insert("1.0", current or CUSTOM_RANGES_PLACEHOLDER)
        if not current:
            text.configure(foreground=self.theme_palette["muted"])

            def clear_placeholder(_event=None):
                if text.get("1.0", "end").strip() == CUSTOM_RANGES_PLACEHOLDER.strip():
                    text.delete("1.0", "end")
                    text.configure(foreground=self.theme_palette["text"])

            text.bind("<FocusIn>", clear_placeholder)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def save_ranges():
            value = text.get("1.0", "end").strip()
            if value == CUSTOM_RANGES_PLACEHOLDER.strip():
                value = ""
            try:
                networks = parse_custom_ranges(value)
                save_custom_range_values([str(network) for network in networks])
            except (OSError, ValueError) as exc:
                messagebox.showerror("Invalid Custom Ranges", str(exc), parent=modal)
                return
            self.custom_networks = networks
            self._refresh_custom_range_summary()
            self._refresh_range_options()
            modal.destroy()

        ttk.Button(buttons, text="Save Ranges", command=save_ranges).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=modal.destroy).pack(side="right", padx=(0, 8))

    def _refresh_custom_range_summary(self):
        count = len(self.custom_networks)
        label = "range" if count == 1 else "ranges"
        self.custom_range_summary_var.set(f"{count} custom {label}")

    def _refresh_range_options(self):
        selected = self.range_var.get()
        ranges = {
            f"{network} ({cloudflare.usable_hosts(network)} usable IPs)": network
            for network in self.cloudflare_networks
        }
        ranges.update(
            {
                f"Custom: {network} ({cloudflare.usable_hosts(network)} usable IPs)": network
                for network in self.custom_networks
            }
        )
        self.ranges_by_label = ranges
        self.range_combo["values"] = list(ranges)
        if selected in ranges:
            self.range_var.set(selected)
        elif ranges:
            self.range_combo.current(0)
