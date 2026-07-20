import json
import os
import re
import subprocess
import webbrowser
from tkinter import messagebox, ttk

from .paths import XRAY_EXE
from .version import APP_VERSION, GITHUB_URL


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

        ttk.Label(content, text="Cloudflare Proxy Scanner", font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 24)
        )
        ttk.Label(content, text="Application version").grid(row=1, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=_display_version(APP_VERSION)).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(content, text="Xray version").grid(row=2, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=get_xray_version()).grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(content, text="GitHub repository").grid(row=3, column=0, sticky="w", padx=(0, 28), pady=6)
        ttk.Label(content, text=GITHUB_URL).grid(row=3, column=1, sticky="w", pady=6)
        ttk.Button(content, text="Open GitHub Repository", command=self._open_github_repository).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(24, 0)
        )

    def _open_github_repository(self):
        try:
            opened = webbrowser.open_new_tab(GITHUB_URL)
        except (OSError, webbrowser.Error) as exc:
            messagebox.showerror("Unable to Open GitHub", str(exc), parent=self)
            return
        if not opened:
            messagebox.showerror(
                "Unable to Open GitHub",
                f"Open this address in your browser:\n{GITHUB_URL}",
                parent=self,
            )
