import json
import unittest

from proxy_tester import update_checker


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class UpdateCheckerTests(unittest.TestCase):
    def test_version_tuple_compares_semantic_versions_numerically(self):
        self.assertGreater(update_checker.version_tuple("v1.10.0"), update_checker.version_tuple("1.9.9"))
        self.assertEqual(update_checker.version_tuple("1.0.3.0"), update_checker.version_tuple("1.0.3"))

    def test_version_tuple_rejects_invalid_release(self):
        with self.assertRaises(ValueError):
            update_checker.version_tuple("latest")

    def test_check_for_update_returns_new_release_page(self):
        payload = {"tag_name": "v1.0.4", "html_url": "https://example.test/v1.0.4"}
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(payload)

        result = update_checker.check_for_update("1.0.3", opener=opener)

        self.assertTrue(result["available"])
        self.assertEqual(result["url"], payload["html_url"])
        self.assertEqual(calls[0][1], 10)
        self.assertEqual(calls[0][0].get_header("User-agent"), "Cloudflare-Proxy-Scanner")

    def test_check_for_update_reports_current_release(self):
        payload = {"tag_name": "v1.0.3", "html_url": "https://example.test/v1.0.3"}
        result = update_checker.check_for_update("1.0.3", opener=lambda *_args, **_kwargs: FakeResponse(payload))
        self.assertFalse(result["available"])

    def test_check_for_update_rejects_incomplete_response(self):
        with self.assertRaises(ValueError):
            update_checker.check_for_update(
                "1.0.3",
                opener=lambda *_args, **_kwargs: FakeResponse({"tag_name": "v1.0.4"}),
            )


if __name__ == "__main__":
    unittest.main()
