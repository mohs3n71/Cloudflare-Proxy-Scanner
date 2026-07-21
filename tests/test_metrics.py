import unittest

from proxy_tester.metrics import normalize_failed_metric


class MetricTests(unittest.TestCase):
    def test_failed_metric_variants_become_integer_minus_one(self):
        for value in (-1, -1.0, "-1", "-1.0", "-1.00"):
            with self.subTest(value=value):
                self.assertEqual(normalize_failed_metric(value), -1)
                self.assertIsInstance(normalize_failed_metric(value), int)

    def test_non_failure_values_are_unchanged(self):
        for value in (None, "", 0, 1.5, "12.5", "invalid"):
            with self.subTest(value=value):
                self.assertEqual(normalize_failed_metric(value), value)


if __name__ == "__main__":
    unittest.main()
