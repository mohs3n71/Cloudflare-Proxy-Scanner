import tkinter as tk
from tkinter import ttk


LIGHT_MODE = "light"
DARK_MODE = "dark"
APPEARANCE_MODES = (LIGHT_MODE, DARK_MODE)

PALETTES = {
    LIGHT_MODE: {
        "background": "#f3f4f5",
        "surface": "#ffffff",
        "surface_alt": "#e8ebee",
        "text": "#24272a",
        "muted": "#687078",
        "border": "#c9ced3",
        "accent": "#3978b5",
        "selection": "#cfe4f7",
        "selection_text": "#17212b",
        "active_row": "#fff0ad",
        "disabled_text": "#8b9298",
    },
    DARK_MODE: {
        "background": "#202326",
        "surface": "#292d31",
        "surface_alt": "#34393e",
        "text": "#e4e7ea",
        "muted": "#aeb5bc",
        "border": "#474d53",
        "accent": "#78a7d2",
        "selection": "#355f84",
        "selection_text": "#f4f7fa",
        "active_row": "#514a2f",
        "disabled_text": "#7f878e",
    },
}


def normalize_appearance_mode(value):
    return value if value in APPEARANCE_MODES else LIGHT_MODE


def palette_for(mode):
    return PALETTES[normalize_appearance_mode(mode)]


def apply_theme(root, mode):
    mode = normalize_appearance_mode(mode)
    palette = palette_for(mode)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette["background"])
    _configure_options(root, palette)
    _configure_ttk_styles(style, palette)
    _theme_classic_widgets(root, palette)
    return palette


def _configure_options(root, palette):
    options = {
        "*Text.background": palette["surface"],
        "*Text.foreground": palette["text"],
        "*Text.insertBackground": palette["text"],
        "*Text.selectBackground": palette["selection"],
        "*Text.selectForeground": palette["selection_text"],
        "*Menu.background": palette["surface"],
        "*Menu.foreground": palette["text"],
        "*Menu.activeBackground": palette["selection"],
        "*Menu.activeForeground": palette["selection_text"],
    }
    for pattern, value in options.items():
        root.option_add(pattern, value)


def _configure_ttk_styles(style, palette):
    background = palette["background"]
    surface = palette["surface"]
    surface_alt = palette["surface_alt"]
    text = palette["text"]
    disabled = palette["disabled_text"]
    border = palette["border"]
    selection = palette["selection"]
    selection_text = palette["selection_text"]

    style.configure(".", background=background, foreground=text, bordercolor=border, lightcolor=border, darkcolor=border)
    style.configure("TFrame", background=background)
    style.configure("TLabel", background=background, foreground=text)
    style.configure("TLabelframe", background=background, bordercolor=border, relief="solid")
    style.configure("TLabelframe.Label", background=background, foreground=text)
    style.configure("TButton", background=surface_alt, foreground=text, bordercolor=border, padding=(6, 2))
    style.map(
        "TButton",
        background=[("active", selection), ("pressed", palette["accent"]), ("disabled", background)],
        foreground=[("active", selection_text), ("pressed", selection_text), ("disabled", disabled)],
    )
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=background, foreground=text)
        style.map(name, background=[("active", background)], foreground=[("disabled", disabled)])

    for name in ("TEntry", "TCombobox"):
        style.configure(name, fieldbackground=surface, foreground=text, bordercolor=border, insertcolor=text)
        style.map(
            name,
            fieldbackground=[("readonly", surface), ("disabled", surface_alt)],
            foreground=[("readonly", text), ("disabled", disabled)],
            selectbackground=[("!disabled", selection)],
            selectforeground=[("!disabled", selection_text)],
        )

    style.configure("TNotebook", background=background, bordercolor=border)
    style.configure("TNotebook.Tab", background=surface_alt, foreground=text, padding=(12, 4))
    style.map(
        "TNotebook.Tab",
        background=[("selected", surface), ("active", selection)],
        foreground=[("selected", text), ("active", selection_text)],
    )
    style.configure(
        "Treeview",
        background=surface,
        fieldbackground=surface,
        foreground=text,
        bordercolor=border,
        rowheight=22,
    )
    style.map("Treeview", background=[("selected", selection)], foreground=[("selected", selection_text)])
    style.configure("Treeview.Heading", background=surface_alt, foreground=text, bordercolor=border, relief="flat")
    style.map("Treeview.Heading", background=[("active", selection)], foreground=[("active", selection_text)])
    style.configure("TScrollbar", background=surface_alt, troughcolor=background, bordercolor=border, arrowcolor=text)
    style.configure("TProgressbar", background=palette["accent"], troughcolor=surface_alt, bordercolor=border)


def _theme_classic_widgets(widget, palette):
    for child in widget.winfo_children():
        if isinstance(child, (tk.Tk, tk.Toplevel)):
            child.configure(background=palette["background"])
        elif isinstance(child, tk.Text):
            child.configure(
                background=palette["surface"],
                foreground=palette["text"],
                insertbackground=palette["text"],
                selectbackground=palette["selection"],
                selectforeground=palette["selection_text"],
                highlightbackground=palette["border"],
                highlightcolor=palette["accent"],
            )
        elif isinstance(child, tk.Menu):
            child.configure(
                background=palette["surface"],
                foreground=palette["text"],
                activebackground=palette["selection"],
                activeforeground=palette["selection_text"],
            )
        _theme_classic_widgets(child, palette)
