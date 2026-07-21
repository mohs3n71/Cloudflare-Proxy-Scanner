import io
import subprocess
import urllib.error
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from proxy_tester import xray
from proxy_tester.proxy_config import ProxyProfile
from tests.helpers import sample_profile


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk


class FakeOpener:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        if self.error:
            raise self.error
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeProc:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


class XrayTests(unittest.TestCase):
    def test_make_xray_config_uses_profile(self):
        config = xray.make_xray_config("104.16.1.1", 18080, sample_profile())
        outbound = config["outbounds"][0]

        self.assertEqual(config["inbounds"][0]["port"], 18080)
        self.assertEqual(outbound["protocol"], "vless")
        self.assertEqual(outbound["settings"]["vnext"][0]["address"], "104.16.1.1")
        self.assertEqual(outbound["settings"]["vnext"][0]["port"], 443)
        self.assertEqual(outbound["streamSettings"]["tlsSettings"]["serverName"], "example.com")
        self.assertEqual(outbound["streamSettings"]["tlsSettings"]["alpn"], ["http/1.1"])
        self.assertEqual(outbound["streamSettings"]["wsSettings"]["path"], "/ws")

    def test_make_xray_config_can_use_fragment_chain(self):
        fragment = {"packets": "1-3", "interval": "1-1", "length": "1-7"}

        config = xray.make_xray_config("104.16.1.1", 18080, sample_profile(), fragment=fragment)

        self.assertEqual(config["inbounds"][0]["tag"], "tester")
        self.assertEqual(config["outbounds"][0]["tag"], "proxy")
        self.assertEqual(config["outbounds"][1]["settings"]["fragment"], fragment)
        self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "fragment")

    def test_make_xray_runner_config_uses_socks_inbound_and_fragment_chain(self):
        fragment = {"packets": "1-3", "interval": "1-1", "length": "1-7"}

        config = xray.make_xray_runner_config(
            "104.16.1.1",
            1080,
            "0.0.0.0",
            sample_profile(),
            fragment,
        )

        self.assertEqual(config["inbounds"][0]["protocol"], "socks")
        self.assertEqual(config["inbounds"][0]["listen"], "0.0.0.0")
        self.assertEqual(config["inbounds"][0]["port"], 1080)
        self.assertEqual(config["outbounds"][0]["tag"], "proxy")
        self.assertEqual(config["outbounds"][0]["protocol"], "vless")
        self.assertEqual(config["outbounds"][0]["settings"]["vnext"][0]["address"], "104.16.1.1")
        self.assertEqual(config["outbounds"][1]["protocol"], "freedom")
        self.assertEqual(config["outbounds"][1]["settings"]["fragment"], fragment)
        self.assertEqual(config["outbounds"][1]["proxySettings"]["tag"], "proxy")
        self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "fragment")

    def test_make_xray_runner_config_routes_directly_when_fragment_is_disabled(self):
        config = xray.make_xray_runner_config(
            "104.16.1.1",
            1080,
            "127.0.0.1",
            sample_profile(),
            {},
        )

        self.assertEqual(len(config["outbounds"]), 1)
        self.assertEqual(config["outbounds"][0]["tag"], "proxy")
        self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "proxy")

    def test_make_xray_config_supports_vmess(self):
        profile = ProxyProfile(
            protocol="vmess",
            file="vmess.txt",
            name="vmess.txt",
            uuid="11111111-1111-1111-1111-111111111111",
            password="",
            port=443,
            security="tls",
            sni="example.com",
            fingerprint="chrome",
            alpn="http/1.1",
            allow_insecure=False,
            network="ws",
            ws_host="example.com",
            ws_path="/ws",
            encryption="none",
            alter_id=0,
            vmess_security="auto",
            header_type="none",
        )

        outbound = xray.make_xray_config("104.16.1.1", 18080, profile)["outbounds"][0]

        self.assertEqual(outbound["protocol"], "vmess")
        self.assertEqual(outbound["settings"]["vnext"][0]["users"][0]["security"], "auto")

    def test_make_xray_config_supports_trojan(self):
        profile = ProxyProfile(
            protocol="trojan",
            file="trojan.txt",
            name="trojan.txt",
            uuid="",
            password="secret",
            port=443,
            security="tls",
            sni="example.com",
            fingerprint="chrome",
            alpn="http/1.1",
            allow_insecure=False,
            network="ws",
            ws_host="example.com",
            ws_path="/ws",
            encryption="none",
            alter_id=0,
            vmess_security="auto",
            header_type="none",
        )

        outbound = xray.make_xray_config("104.16.1.1", 18080, profile)["outbounds"][0]

        self.assertEqual(outbound["protocol"], "trojan")
        self.assertEqual(outbound["settings"]["servers"][0]["password"], "secret")

    def test_tls_alpn_for_xray_forces_http11_for_websocket(self):
        profile = sample_profile()

        self.assertEqual(xray.tls_alpn_for_xray(profile), ["http/1.1"])

    def test_make_stream_settings_supports_xhttp(self):
        profile = ProxyProfile(
            **{
                **sample_profile().__dict__,
                "network": "xhttp",
                "alpn": "h2,http/1.1",
                "ws_host": "cdn.example.com",
                "ws_path": "/xhttp",
                "xhttp_mode": "packet-up",
                "xhttp_extra": {"xPaddingBytes": "100-1000"},
            }
        )

        settings = xray.make_stream_settings(profile)

        self.assertEqual(settings["network"], "xhttp")
        self.assertNotIn("wsSettings", settings)
        self.assertEqual(settings["tlsSettings"]["alpn"], ["h2", "http/1.1"])
        self.assertEqual(
            settings["xhttpSettings"],
            {
                "host": "cdn.example.com",
                "path": "/xhttp",
                "mode": "packet-up",
                "extra": {"xPaddingBytes": "100-1000"},
            },
        )

    def test_mbps_calculation(self):
        self.assertEqual(xray.mbps(1_000_000, 1), 8.0)
        self.assertEqual(xray.mbps(1_000_000, 0), 0.0)

    def test_speed_url_adds_byte_count(self):
        self.assertEqual(xray.speed_url("https://speed.cloudflare.com/__up", 1024), "https://speed.cloudflare.com/__up?bytes=1024")

    def test_speed_request_debug_includes_upload_details(self):
        detail = xray.speed_request_debug("upload", 1024, 7000)

        self.assertIn("mode=upload", detail)
        self.assertIn("bytes=1024", detail)
        self.assertIn("timeout_ms=7000", detail)
        self.assertIn("upload_url=https://speed.cloudflare.com/__up?bytes=1024", detail)
        self.assertIn("upload_method=POST", detail)

    def test_describe_network_error_includes_http_details(self):
        error = urllib.error.HTTPError(
            "https://speed.cloudflare.com/__up?bytes=1024",
            429,
            "Too Many Requests",
            {"Retry-After": "5", "CF-RAY": "abc"},
            io.BytesIO(b"slow down"),
        )

        detail = xray.describe_network_error(error)

        self.assertIn("HTTPError", detail)
        self.assertIn("status=429", detail)
        self.assertIn("reason=Too Many Requests", detail)
        self.assertIn("retry_after=5", detail)
        self.assertIn("cf_ray=abc", detail)
        self.assertIn("body=slow down", detail)

    def test_measure_download_reads_all_chunks(self):
        opener = FakeOpener([FakeResponse([b"a" * 100, b"b" * 100, b""])])

        with patch.object(xray.time, "monotonic", side_effect=[0, 2]):
            result = xray.measure_download(opener)

        req, _ = opener.requests[0]
        self.assertEqual(result, 0.0)
        self.assertEqual(req.full_url, "https://speed.cloudflare.com/__down?bytes=1048576")

    def test_measure_download_reports_received_bytes_after_timeout(self):
        received_bytes = 64 * 1024
        opener = FakeOpener([FakeResponse([b"a" * received_bytes, TimeoutError("slow download")])])

        with patch.object(xray.time, "monotonic", side_effect=[0, 5]):
            with self.assertRaises(xray.PartialDownloadError) as raised:
                xray.measure_download(opener, byte_count=1024 * 1024, timeout_ms=7000)

        error = raised.exception
        self.assertEqual(error.downloaded_bytes, received_bytes)
        self.assertEqual(error.requested_bytes, 1024 * 1024)
        self.assertEqual(error.speed_mbps, xray.mbps(received_bytes, 5))

    def test_download_diagnostics_keep_partial_speed_as_warning(self):
        partial = xray.PartialDownloadError(64 * 1024, 1024 * 1024, 5, TimeoutError("slow"))
        with patch.object(xray, "measure_download", side_effect=partial):
            speeds, errors = xray.run_speed_tests_with_diagnostics(Mock(), "download", "ip")

        self.assertEqual(speeds["download_mbps"], partial.speed_mbps)
        self.assertIn("download partial", speeds["speed_warnings"][0])
        self.assertEqual(errors, [])

    def test_measure_upload_posts_configured_bytes(self):
        opener = FakeOpener([FakeResponse([b"ok"])])
        byte_count = 128 * 1024

        with patch.object(xray.time, "monotonic", side_effect=[0, 0, 4]):
            result = xray.measure_upload(opener, byte_count=byte_count)

        req, _ = opener.requests[0]
        self.assertEqual(req.full_url, f"https://speed.cloudflare.com/__up?bytes={byte_count}")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(len(req.data), byte_count)
        self.assertEqual(result, round((byte_count * 8) / 4 / 1_000_000, 2))

    def test_measure_upload_reports_confirmed_bytes_after_remainder_timeout(self):
        opener = FakeOpener([FakeResponse([b"ok"]), TimeoutError("slow remainder")])
        byte_count = xray.UPLOAD_CONFIRMATION_PROBE_BYTES * 4

        with patch.object(xray.time, "monotonic", side_effect=[0, 0, 1, 5]):
            with self.assertRaises(xray.PartialUploadError) as raised:
                xray.measure_upload(opener, byte_count=byte_count, timeout_ms=7000)

        error = raised.exception
        self.assertEqual(error.uploaded_bytes, xray.UPLOAD_CONFIRMATION_PROBE_BYTES)
        self.assertEqual(error.requested_bytes, byte_count)
        self.assertEqual(error.speed_mbps, xray.mbps(xray.UPLOAD_CONFIRMATION_PROBE_BYTES, 5))
        self.assertEqual(len(opener.requests), 2)

    def test_measure_upload_does_not_hide_http_error_as_partial_speed(self):
        http_error = urllib.error.HTTPError(
            "https://speed.cloudflare.com/__up",
            429,
            "Too Many Requests",
            {},
            None,
        )
        opener = FakeOpener([FakeResponse([b"ok"]), http_error])
        with patch.object(xray.time, "monotonic", side_effect=[0, 0, 1, 2]):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                xray.measure_upload(
                    opener,
                    byte_count=xray.UPLOAD_CONFIRMATION_PROBE_BYTES * 2,
                    timeout_ms=7000,
                )

        self.assertEqual(raised.exception.code, 429)

    def test_upload_diagnostics_keep_partial_speed_as_warning(self):
        partial = xray.PartialUploadError(256 * 1024, 1024 * 1024, 5, TimeoutError("slow"))
        with patch.object(xray, "measure_upload", side_effect=partial):
            speeds, errors = xray.run_speed_tests_with_diagnostics(Mock(), "upload", "ip")

        self.assertEqual(speeds["upload_mbps"], partial.speed_mbps)
        self.assertIn("upload partial", speeds["speed_warnings"][0])
        self.assertEqual(errors, [])

    def test_run_speed_tests_respects_mode(self):
        with patch.object(xray, "measure_download", return_value=10) as download:
            with patch.object(xray, "measure_upload", return_value=5) as upload:
                self.assertEqual(xray.run_speed_tests(Mock(), "download", "ip"), {"download_mbps": 10})
                self.assertEqual(xray.run_speed_tests(Mock(), "upload", "ip"), {"upload_mbps": 5})
                self.assertEqual(
                    xray.run_speed_tests(Mock(), "both", "ip"),
                    {"download_mbps": 10, "upload_mbps": 5},
                )

        self.assertEqual(download.call_count, 2)
        self.assertEqual(upload.call_count, 2)

    def test_run_speed_tests_with_diagnostics_keeps_partial_results(self):
        with patch.object(xray, "measure_download", return_value=10):
            with patch.object(xray, "measure_upload", side_effect=TimeoutError("slow upload")):
                speeds, errors = xray.run_speed_tests_with_diagnostics(Mock(), "both", "ip")

        self.assertEqual(speeds["download_mbps"], 10)
        self.assertEqual(speeds["upload_mbps"], -1)
        self.assertEqual(len(errors), 1)
        self.assertIn("upload failed", errors[0])

    def test_speed_failure_values_matches_requested_mode(self):
        self.assertEqual(xray.speed_failure_values("download"), {"download_mbps": -1})
        self.assertEqual(xray.speed_failure_values("upload"), {"upload_mbps": -1})
        self.assertEqual(
            xray.speed_failure_values("both"),
            {"download_mbps": -1, "upload_mbps": -1},
        )

    def test_format_speed_summary(self):
        self.assertEqual(xray.format_speed_summary({}), "")
        self.assertEqual(xray.format_speed_summary({"download_mbps": 10, "upload_mbps": 5}), " down=10Mbps up=5Mbps")

    def test_test_ip_success_without_speed_test(self):
        proc = FakeProc()
        opener = FakeOpener([FakeResponse([b"colo=AMS\nwarp=off\n"])])
        started = []
        finished = []

        with patch.object(xray, "free_port", return_value=18080), patch.object(xray.time, "sleep"):
            with patch.object(xray.time, "time", side_effect=[10, 10.123]):
                with patch.object(xray.subprocess, "Popen", return_value=proc):
                    with patch.object(xray.urllib.request, "build_opener", return_value=opener):
                        with redirect_stdout(io.StringIO()):
                            result = xray.test_ip(
                                "104.16.1.1",
                                1,
                                1,
                                sample_profile(),
                                process_started=started.append,
                                process_finished=finished.append,
                            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["ip"], "104.16.1.1")
        self.assertEqual(result["ms"], 122)
        self.assertEqual(result["colo"], "AMS")
        self.assertEqual(result["warp"], "off")
        self.assertTrue(proc.terminated)
        self.assertEqual(started, [proc])
        self.assertEqual(finished, [proc])

    def test_test_ip_success_with_speed_test(self):
        proc = FakeProc()
        opener = FakeOpener([FakeResponse([b"colo=AMS\nwarp=off\n"])])

        with patch.object(xray, "free_port", return_value=18080), patch.object(xray.time, "sleep"):
            with patch.object(xray.time, "time", side_effect=[10, 10.1]):
                with patch.object(xray.subprocess, "Popen", return_value=proc):
                    with patch.object(xray.urllib.request, "build_opener", return_value=opener):
                        with patch.object(
                            xray,
                            "run_speed_tests_with_diagnostics",
                            return_value=({"download_mbps": 11}, []),
                        ):
                            with redirect_stdout(io.StringIO()):
                                result = xray.test_ip("104.16.1.1", 1, 1, sample_profile(), speed_mode="download")

        self.assertEqual(result["download_mbps"], 11)

    def test_test_ip_keeps_latency_and_partial_values_when_speed_test_fails(self):
        proc = FakeProc()
        opener = FakeOpener([FakeResponse([b"colo=AMS\nwarp=off\n"])])

        with patch.object(xray, "free_port", return_value=18080), patch.object(xray.time, "sleep"):
            with patch.object(xray.time, "time", side_effect=[10, 10.1]):
                with patch.object(xray.subprocess, "Popen", return_value=proc):
                    with patch.object(xray.urllib.request, "build_opener", return_value=opener):
                        with patch.object(
                            xray,
                            "run_speed_tests_with_diagnostics",
                            return_value=(
                                {"download_mbps": 10, "upload_mbps": -1},
                                ["upload failed: TimeoutError: slow"],
                            ),
                        ):
                            with redirect_stdout(io.StringIO()):
                                result = xray.test_ip("104.16.1.1", 1, 1, sample_profile(), speed_mode="both")

        self.assertFalse(result["ok"])
        self.assertEqual(result["ms"], 99)
        self.assertEqual(result["download_mbps"], 10)
        self.assertEqual(result["upload_mbps"], -1)
        self.assertIn("Speed test failed: upload failed", result["error"])
        self.assertIn("mode=both", result["speed_debug"])
        self.assertIn("upload_url=https://speed.cloudflare.com/__up?bytes=1048576", result["speed_debug"])

    def test_test_ip_failure_returns_error_and_terminates_process(self):
        proc = FakeProc()
        opener = FakeOpener(error=TimeoutError("nope"))

        with patch.object(xray, "free_port", return_value=18080), patch.object(xray.time, "sleep"):
            with patch.object(xray.subprocess, "Popen", return_value=proc):
                with patch.object(xray.urllib.request, "build_opener", return_value=opener):
                    with redirect_stdout(io.StringIO()):
                        result = xray.test_ip("104.16.1.1", 1, 1, sample_profile())

        self.assertFalse(result["ok"])
        self.assertIn("TimeoutError", result["error"])
        self.assertTrue(proc.terminated)

    def test_test_ip_kills_process_when_wait_times_out(self):
        class SlowProc(FakeProc):
            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("xray", timeout)

        proc = SlowProc()
        opener = FakeOpener(error=TimeoutError("nope"))

        with patch.object(xray, "free_port", return_value=18080), patch.object(xray.time, "sleep"):
            with patch.object(xray.subprocess, "Popen", return_value=proc):
                with patch.object(xray.urllib.request, "build_opener", return_value=opener):
                    with redirect_stdout(io.StringIO()):
                        xray.test_ip("104.16.1.1", 1, 1, sample_profile())

        self.assertTrue(proc.killed)


if __name__ == "__main__":
    unittest.main()
