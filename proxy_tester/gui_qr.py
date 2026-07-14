import tkinter as tk
from tkinter import messagebox, ttk

from .qr_code import QrCodeUnavailableError, build_qr_matrix, qr_canvas_layout


QR_CANVAS_SIZE = 440


def draw_qr_matrix(canvas, matrix, canvas_size=QR_CANVAS_SIZE):
    module_size, offset = qr_canvas_layout(matrix, canvas_size)
    canvas.delete("all")
    canvas.create_rectangle(0, 0, canvas_size, canvas_size, fill="white", outline="")
    for row_index, row in enumerate(matrix):
        for column_index, is_dark in enumerate(row):
            if not is_dark:
                continue
            x1 = offset + column_index * module_size
            y1 = offset + row_index * module_size
            canvas.create_rectangle(
                x1,
                y1,
                x1 + module_size,
                y1 + module_size,
                fill="black",
                outline="black",
            )


def open_config_qr(parent, config_url, protocol, ip):
    try:
        matrix = build_qr_matrix(config_url)
    except QrCodeUnavailableError as exc:
        messagebox.showerror("QR Code Unavailable", str(exc), parent=parent)
        return None

    window = tk.Toplevel(parent)
    window.title("Proxy Configuration QR Code")
    window.resizable(False, False)
    window.transient(parent)

    content = ttk.Frame(window, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    ttk.Label(content, text=f"{protocol.upper()} configuration - {ip}").grid(row=0, column=0, sticky="w")

    canvas = tk.Canvas(
        content,
        width=QR_CANVAS_SIZE,
        height=QR_CANVAS_SIZE,
        background="white",
        highlightthickness=1,
        highlightbackground="#888888",
    )
    canvas.grid(row=1, column=0, pady=(8, 10))
    draw_qr_matrix(canvas, matrix)

    buttons = ttk.Frame(content)
    buttons.grid(row=2, column=0, sticky="e")

    def copy_config():
        parent.clipboard_clear()
        parent.clipboard_append(config_url)

    ttk.Button(buttons, text="Copy Configuration", command=copy_config).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Close", command=window.destroy).grid(row=0, column=1)
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    return window
