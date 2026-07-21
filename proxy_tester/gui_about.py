import json
import os
import re
import subprocess
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .paths import XRAY_EXE
from .gui_theme import DARK_MODE, LIGHT_MODE, apply_theme
from .settings import save_appearance_mode
from .update_checker import check_for_update
from .version import APP_TITLE, APP_VERSION, GITHUB_URL


XRAY_METADATA_FILE = "xray.metadata.json"
UNAVAILABLE_VERSION = "Unavailable"


def _display_version(version):
    value = str(version or "").strip()
    if not value:
        return UNAVAILABLE_VERSION
    return value if value.lower().startswith("v") else f"v{value}"


def _metadata_version(executable):
    metadata_path = os.path.join(os.path.dirname(executable), XRAY_METADATA_FILE)
    try:
        with open(metadata_path, "r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
    except (OSError, ValueError):
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata.get("version")


def _xray_version_command(executable):
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [executable, "version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\bXray\s+([^\s]+)", completed.stdout or "", re.IGNORECASE)
    return match.group(1) if match else None


def get_xray_version(executable=XRAY_EXE):
    version = _metadata_version(executable)
    if not version:
        version = _xray_version_command(executable)
    return _display_version(version)


class AboutMixin:
    def _build_about_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        content = ttk.Frame(parent, padding=40)
        content.grid(row=0, column=0)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text=APP_TITLE, font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 24)
        )
        ttk.Label(content, text="Application version").grid(row=1, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=_display_version(APP_VERSION)).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(content, text="Xray version").grid(row=2, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=get_xray_version()).grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(content, text="GitHub repository").grid(row=3, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=GITHUB_URL).grid(row=3, column=1, sticky="w", pady=6)
        ttk.Label(content, text="Appearance").grid(row=4, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Checkbutton(
            content,
            text="Dark mode",
            variable=self.appearance_var,
            command=self._set_appearance_from_control,
        ).grid(row=4, column=1, sticky="w", pady=6)
        ttk.Button(content, text="Open GitHub Repository", command=self._open_github_repository).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(24, 0)
        )
        self.update_status_var = tk.StringVar(value="")
        self.update_button = ttk.Button(content, text="Check for Updates", command=self.check_for_updates)
        self.update_button.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(content, textvariable=self.update_status_var).grid(
            row=7, column=0, columnspan=2, pady=(8, 0)
        )

    def _set_appearance_from_control(self):
        mode = DARK_MODE if self.appearance_var.get() else LIGHT_MODE
        self.appearance_mode = mode
        self.theme_palette = apply_theme(self, mode)
        if hasattr(self, "table"):
            self.table.tag_configure("active", background=self.theme_palette["active_row"])
        try:
            save_appearance_mode(mode)
        except OSError as exc:
            messagebox.showerror("Appearance Settings", f"Could not save appearance preference:\n{exc}", parent=self)

    def _open_web_page(self, url, title):
        try:
            opened = webbrowser.open_new_tab(url)
        except (OSError, webbrowser.Error) as exc:
            messagebox.showerror(title, str(exc), parent=self)
            return False
        if not opened:
            messagebox.showerror(title, f"Open this address in your browser:\n{url}", parent=self)
            return False
        return True

    def _open_github_repository(self):
        self._open_web_page(GITHUB_URL, "Unable to Open GitHub")

    def check_for_updates(self):
        self.update_button.configure(state="disabled")
        self.update_status_var.set("Checking for updates...")
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _update_check_worker(self):
        try:
            result = check_for_update(APP_VERSION)
        except Exception as exc:
            self.events.put(("update_check_error", str(exc)))
            return
        self.events.put(("update_check_result", result))

    def _handle_update_check_error(self, message):
        self.update_button.configure(state="normal")
        self.update_status_var.set("Unable to check for updates.")
        messagebox.showerror("Update Check Failed", message, parent=self)

    def _handle_update_check_result(self, result):
        self.update_button.configure(state="normal")
        if result["available"]:
            self.update_status_var.set(f'{result["version"]} is available. Opening download page...')
            self._open_web_page(result["url"], "Unable to Open Download Page")
            return
        self.update_status_var.set(f'You are using the latest version ({_display_version(APP_VERSION)}).')
        messagebox.showinfo(
            "No Update Available",
            f"You are using the latest version ({_display_version(APP_VERSION)}).",
            parent=self,
        )
