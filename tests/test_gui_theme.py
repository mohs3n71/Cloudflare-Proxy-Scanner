import unittest

from proxy_tester.gui_theme import DARK_MODE, LIGHT_MODE, normalize_appearance_mode, palette_for


class GuiThemeTests(unittest.TestCase):
    def test_invalid_appearance_mode_falls_back_to_light(self):
        self.assertEqual(normalize_appearance_mode("unknown"), LIGHT_MODE)
        self.assertEqual(palette_for("unknown"), palette_for(LIGHT_MODE))

    def test_dark_palette_is_soft_charcoal_and_complete(self):
        dark = palette_for(DARK_MODE)
        light = palette_for(LIGHT_MODE)

        self.assertNotEqual(dark, light)
        self.assertEqual(set(dark), set(light))
        self.assertEqual(dark["background"], "#202326")
        self.assertNotEqual(dark["surface"], dark["background"])
        self.assertNotEqual(dark["text"], dark["surface"])


if __name__ == "__main__":
    unittest.main()
