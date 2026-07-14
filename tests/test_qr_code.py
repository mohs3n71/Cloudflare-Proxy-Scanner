import unittest

from proxy_tester.qr_code import build_qr_matrix, qr_canvas_layout


class QrCodeTests(unittest.TestCase):
    def test_build_qr_matrix_returns_square_boolean_grid(self):
        matrix = build_qr_matrix("vless://example-config")

        self.assertGreaterEqual(len(matrix), 21)
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(all(isinstance(cell, bool) for row in matrix for cell in row))

    def test_qr_canvas_layout_centers_whole_modules(self):
        matrix = [[False] * 21 for _ in range(21)]

        module_size, offset = qr_canvas_layout(matrix, 440)

        self.assertEqual(module_size, 20)
        self.assertEqual(offset, 10)

    def test_qr_canvas_layout_rejects_non_square_matrix(self):
        with self.assertRaisesRegex(ValueError, "square"):
            qr_canvas_layout([[True, False], [True]], 100)


if __name__ == "__main__":
    unittest.main()
