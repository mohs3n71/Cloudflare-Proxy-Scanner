import builtins
import unittest
from unittest.mock import MagicMock, patch

from proxy_tester import gui_qr, qr_code


class FakeWidget:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.destroyed = False

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "destroy":
                self.destroyed = True
        return method


class FakeCanvas(FakeWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rectangles = []

    def delete(self, value):
        self.calls.append(("delete", (value,), {}))

    def create_rectangle(self, *coordinates, **kwargs):
        self.rectangles.append((coordinates, kwargs))


class GuiQrTests(unittest.TestCase):
    def test_draw_qr_matrix_renders_background_and_dark_modules(self):
        canvas = FakeCanvas()

        gui_qr.draw_qr_matrix(canvas, [[True, False], [False, True]], canvas_size=10)

        self.assertEqual(len(canvas.rectangles), 3)
        self.assertEqual(canvas.rectangles[0][1]["fill"], "white")
        self.assertEqual(canvas.rectangles[1][0], (0, 0, 5, 5))
        self.assertEqual(canvas.rectangles[2][0], (5, 5, 10, 10))

    def test_open_config_qr_reports_missing_dependency(self):
        parent = MagicMock()
        with patch.object(gui_qr, "build_qr_matrix", side_effect=qr_code.QrCodeUnavailableError("install it")):
            with patch.object(gui_qr.messagebox, "showerror") as showerror:
                window = gui_qr.open_config_qr(parent, "vless://config", "vless", "104.16.1.1")

        self.assertIsNone(window)
        showerror.assert_called_once_with("QR Code Unavailable", "install it", parent=parent)

    def test_open_config_qr_builds_window_and_copy_action(self):
        parent = MagicMock()
        window = FakeWidget()
        canvas = FakeCanvas()
        buttons = {}

        def make_button(_parent, text, command):
            button = FakeWidget(text=text, command=command)
            buttons[text] = button
            return button

        with patch.object(gui_qr, "build_qr_matrix", return_value=[[True]]):
            with patch.object(gui_qr.tk, "Toplevel", return_value=window):
                with patch.object(gui_qr.tk, "Canvas", return_value=canvas):
                    with patch.object(gui_qr.ttk, "Frame", side_effect=lambda *args, **kwargs: FakeWidget(**kwargs)):
                        with patch.object(gui_qr.ttk, "Label", side_effect=lambda *args, **kwargs: FakeWidget(**kwargs)):
                            with patch.object(gui_qr.ttk, "Button", side_effect=make_button):
                                result = gui_qr.open_config_qr(
                                    parent,
                                    "trojan://config",
                                    "trojan",
                                    "104.16.1.1",
                                )

        self.assertIs(result, window)
        buttons["Copy Configuration"].kwargs["command"]()
        parent.clipboard_clear.assert_called_once_with()
        parent.clipboard_append.assert_called_once_with("trojan://config")
        buttons["Close"].kwargs["command"]()
        self.assertTrue(window.destroyed)

    def test_build_qr_matrix_has_clear_error_without_package(self):
        original_import = builtins.__import__

        def import_without_qrcode(name, *args, **kwargs):
            if name == "qrcode":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_qrcode):
            with self.assertRaisesRegex(qr_code.QrCodeUnavailableError, "requirements.txt"):
                qr_code.build_qr_matrix("vless://config")

    def test_qr_canvas_layout_rejects_empty_matrix(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            qr_code.qr_canvas_layout([], 100)


if __name__ == "__main__":
    unittest.main()
