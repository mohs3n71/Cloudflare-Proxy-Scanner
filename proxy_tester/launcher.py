import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from tools.xray_release import detect_arch, detect_os, download_xray, xray_unavailable_message

from .paths import BIN_DIR
from .version import APP_TITLE


class XrayBootstrap(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("480x145")
        self.resizable(False, False)
        self.events = queue.Queue()
        self.succeeded = False

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Preparing Xray", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Checking for Xray updates...")
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w", pady=(8, 10))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x")
        self.progress.start(12)

        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.after(50, self._drain_events)
        threading.Thread(target=self._prepare_xray, daemon=True).start()

    def _prepare_xray(self):
        output_dir = os.path.join(BIN_DIR, "xray")
        try:
            download_xray(
                detect_os(),
                detect_arch(),
                output_dir,
                if_missing=True,
                progress=lambda downloaded, total: self.events.put(("progress", downloaded, total)),
            )
        except Exception as exc:
            self.events.put(("error", output_dir, detect_os(), str(exc)))
            return
        self.events.put(("done",))

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    self._show_download_progress(event[1], event[2])
                elif event[0] == "error":
                    self._show_error(event[1], event[2], event[3])
                    return
                elif event[0] == "done":
                    self.succeeded = True
                    self.progress.stop()
                    self.destroy()
                    return
        except queue.Empty:
            pass
        self.after(50, self._drain_events)

    def _show_download_progress(self, downloaded, total):
        self.progress.stop()
        if total > 0:
            percent = min(100, (downloaded / total) * 100)
            self.progress.configure(mode="determinate", maximum=100, value=percent)
            self.status_var.set(f"Downloading Xray update... {percent:.0f}%")
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.status_var.set(f"Downloading Xray update... {downloaded / (1024 * 1024):.1f} MB")

    def _show_error(self, output_dir, target_os, error):
        message = f"{xray_unavailable_message(output_dir, target_os)}\n\nError: {error}"
        self.progress.stop()
        messagebox.showerror("Xray Is Required", message, parent=self)
        self.destroy()


def prepare_xray():
    bootstrap = XrayBootstrap()
    bootstrap.mainloop()
    return bootstrap.succeeded


def main():
    if not prepare_xray():
        return
    from .gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
