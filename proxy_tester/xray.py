import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

from . import colors
from .paths import XRAY_EXE


TEST_URL = "https://www.cloudflare.com/cdn-cgi/trace"
SPEED_TEST_BASE_URL = "https://speed.cloudflare.com"
DOWNLOAD_TEST_URL = f"{SPEED_TEST_BASE_URL}/__down"
UPLOAD_TEST_URL = "https://speed.cloudflare.com/__up"
DEFAULT_SPEED_TEST_BYTES = 1 * 1024 * 1024
DEFAULT_SPEED_TEST_TIMEOUT_MS = 7000
UPLOAD_CONFIRMATION_PROBE_BYTES = 256 * 1024


def speed_url(base_url, byte_count):
    return f"{base_url}?{urlencode({'bytes': byte_count})}"


def speed_request_debug(speed_mode, byte_count, timeout_ms):
    details = [
        f"mode={speed_mode}",
        f"bytes={byte_count}",
        f"timeout_ms={timeout_ms}",
    ]
    if speed_mode in ("download", "both"):
        details.append(f"download_url={speed_url(DOWNLOAD_TEST_URL, byte_count)}")
    if speed_mode in ("upload", "both"):
        details.append(f"upload_url={speed_url(UPLOAD_TEST_URL, byte_count)}")
        details.append("upload_method=POST")
    return " | ".join(details)


def describe_network_error(exc):
    details = [f"{type(exc).__name__}: {exc}"]
    if isinstance(exc, urllib.error.HTTPError):
        details.extend(
            [
                f"status={exc.code}",
                f"reason={exc.reason}",
                f"url={exc.url}",
            ]
        )
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        cf_ray = exc.headers.get("CF-RAY") if exc.headers else None
        if retry_after:
            details.append(f"retry_after={retry_after}")
        if cf_ray:
            details.append(f"cf_ray={cf_ray}")
        try:
            body = exc.read(300).decode("utf-8", "replace").strip()
        except Exception:
            body = ""
        if body:
            details.append(f"body={body[:300]}")
    elif isinstance(exc, urllib.error.URLError):
        details.append(f"reason={exc.reason}")
    return " | ".join(details)


def is_timeout_error(exc):
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        return is_timeout_error(exc.reason)
    return False


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_xray_config(ip, inbound_port, profile, fragment=None):
    outbound = make_outbound(ip, profile)
    outbound["tag"] = "proxy"
    outbound["streamSettings"] = make_stream_settings(profile)
    route_tag = "proxy"
    outbounds = [outbound]
    if fragment:
        route_tag = "fragment"
        outbounds.append(
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {"fragment": fragment},
                "proxySettings": {"tag": "proxy"},
            }
        )
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "tester",
                "listen": "127.0.0.1",
                "port": inbound_port,
                "protocol": "http",
                "settings": {"timeout": 12},
            }
        ],
        "outbounds": outbounds,
    }
    if fragment:
        config["routing"] = {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["tester"],
                    "outboundTag": route_tag,
                }
            ]
        }
    return config


def make_xray_runner_config(ip, inbound_port, listen, profile, fragment):
    proxy = make_outbound(ip, profile)
    proxy["tag"] = "proxy"
    proxy["streamSettings"] = make_stream_settings(profile)
    route_tag = "proxy"
    outbounds = [proxy]
    if fragment:
        route_tag = "fragment"
        outbounds.append(
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {"fragment": fragment},
                "proxySettings": {"tag": "proxy"},
            }
        )
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "runner",
                "listen": listen,
                "port": inbound_port,
                "protocol": "socks",
                "settings": {"udp": True, "auth": "noauth"},
            }
        ],
        "outbounds": outbounds,
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["runner"],
                    "outboundTag": route_tag,
                }
            ]
        },
    }


def make_outbound(ip, profile):
    if profile.protocol == "vless":
        return {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": ip,
                        "port": profile.port,
                        "users": [
                            {
                                "id": profile.uuid,
                                "encryption": profile.encryption,
                            }
                        ],
                    }
                ]
            },
        }
    if profile.protocol == "vmess":
        return {
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": ip,
                        "port": profile.port,
                        "users": [
                            {
                                "id": profile.uuid,
                                "alterId": profile.alter_id,
                                "security": profile.vmess_security,
                            }
                        ],
                    }
                ]
            },
        }
    if profile.protocol == "trojan":
        return {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": ip,
                        "port": profile.port,
                        "password": profile.password,
                    }
                ]
            },
        }
    raise ValueError(f"Unsupported protocol: {profile.protocol}")


def make_stream_settings(profile):
    return {
        "network": "ws",
        "security": profile.security,
        "tlsSettings": {
            "serverName": profile.sni,
            "fingerprint": profile.fingerprint,
            "allowInsecure": profile.allow_insecure,
            "alpn": tls_alpn_for_xray(profile),
        },
        "wsSettings": {
            "path": profile.ws_path,
            "headers": {"Host": profile.ws_host},
        },
    }


def mbps(byte_count, elapsed_seconds):
    if elapsed_seconds <= 0:
        return 0.0
    return round((byte_count * 8) / elapsed_seconds / 1_000_000, 2)


class PartialTransferError(Exception):
    def __init__(self, direction, transferred_bytes, requested_bytes, elapsed_seconds, cause):
        self.direction = direction
        self.transferred_bytes = transferred_bytes
        self.requested_bytes = requested_bytes
        self.elapsed_seconds = elapsed_seconds
        self.speed_mbps = mbps(transferred_bytes, elapsed_seconds)
        self.cause = cause
        super().__init__(
            f"confirmed {transferred_bytes}/{requested_bytes} bytes in {elapsed_seconds:.2f}s "
            f"({self.speed_mbps} Mbps); {describe_network_error(cause)}"
        )


class PartialUploadError(PartialTransferError):
    def __init__(self, uploaded_bytes, requested_bytes, elapsed_seconds, cause):
        self.uploaded_bytes = uploaded_bytes
        super().__init__("upload", uploaded_bytes, requested_bytes, elapsed_seconds, cause)


class PartialDownloadError(PartialTransferError):
    def __init__(self, downloaded_bytes, requested_bytes, elapsed_seconds, cause):
        self.downloaded_bytes = downloaded_bytes
        super().__init__("download", downloaded_bytes, requested_bytes, elapsed_seconds, cause)


def tls_alpn_for_xray(profile):
    values = [item.strip() for item in profile.alpn.split(",") if item.strip()]
    if profile.network == "ws" and "http/1.1" in values:
        return ["http/1.1"]
    return values


def measure_download(opener, ip=None, byte_count=DEFAULT_SPEED_TEST_BYTES, timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS):
    if ip:
        print(colors.info(f"Speed test: downloading through {ip}..."), flush=True)
    req = urllib.request.Request(
        speed_url(DOWNLOAD_TEST_URL, byte_count),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    total_bytes = 0
    start = time.monotonic()
    try:
        with opener.open(req, timeout=timeout_ms / 1000) as resp:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
    except Exception as exc:
        elapsed_seconds = time.monotonic() - start
        if total_bytes > 0 and is_timeout_error(exc):
            raise PartialDownloadError(total_bytes, byte_count, elapsed_seconds, exc) from exc
        raise
    return mbps(total_bytes, time.monotonic() - start)


def measure_upload(opener, ip=None, byte_count=DEFAULT_SPEED_TEST_BYTES, timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS):
    if ip:
        print(colors.info(f"Speed test: uploading through {ip}..."), flush=True)
    start = time.monotonic()
    deadline = start + (timeout_ms / 1000)
    uploaded_bytes = 0
    probe_bytes = min(byte_count, UPLOAD_CONFIRMATION_PROBE_BYTES)
    request_sizes = [probe_bytes]
    if probe_bytes < byte_count:
        request_sizes.append(byte_count - probe_bytes)

    try:
        for request_bytes in request_sizes:
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                raise TimeoutError("upload deadline reached")
            req = urllib.request.Request(
                speed_url(UPLOAD_TEST_URL, request_bytes),
                data=b"0" * request_bytes,
                headers={
                    "Content-Type": "text/plain;charset=UTF-8",
                    "User-Agent": "Mozilla/5.0",
                },
                method="POST",
            )
            with opener.open(req, timeout=remaining_seconds) as resp:
                resp.read(1024)
            uploaded_bytes += request_bytes
    except Exception as exc:
        elapsed_seconds = time.monotonic() - start
        if uploaded_bytes > 0 and is_timeout_error(exc):
            raise PartialUploadError(uploaded_bytes, byte_count, elapsed_seconds, exc) from exc
        raise

    return mbps(uploaded_bytes, time.monotonic() - start)


def run_speed_tests(
    opener,
    speed_mode,
    ip,
    speed_test_bytes=DEFAULT_SPEED_TEST_BYTES,
    speed_timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS,
):
    speeds = {}
    if speed_mode in ("download", "both"):
        speeds["download_mbps"] = measure_download(
            opener,
            ip=ip,
            byte_count=speed_test_bytes,
            timeout_ms=speed_timeout_ms,
        )
    if speed_mode in ("upload", "both"):
        speeds["upload_mbps"] = measure_upload(
            opener,
            ip=ip,
            byte_count=speed_test_bytes,
            timeout_ms=speed_timeout_ms,
        )
    return speeds


def run_speed_tests_with_diagnostics(
    opener,
    speed_mode,
    ip,
    speed_test_bytes=DEFAULT_SPEED_TEST_BYTES,
    speed_timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS,
):
    speeds = {}
    errors = []
    checks = []
    if speed_mode in ("download", "both"):
        checks.append(("download", "download_mbps", measure_download))
    if speed_mode in ("upload", "both"):
        checks.append(("upload", "upload_mbps", measure_upload))

    for label, key, measure in checks:
        try:
            speeds[key] = measure(
                opener,
                ip=ip,
                byte_count=speed_test_bytes,
                timeout_ms=speed_timeout_ms,
            )
        except PartialTransferError as exc:
            speeds[key] = exc.speed_mbps
            speeds.setdefault("speed_warnings", []).append(f"{label} partial: {exc}")
        except Exception as exc:
            speeds[key] = -1
            errors.append(f"{label} failed: {describe_network_error(exc)}")

    return speeds, errors


def speed_failure_values(speed_mode):
    values = {}
    if speed_mode in ("download", "both"):
        values["download_mbps"] = -1
    if speed_mode in ("upload", "both"):
        values["upload_mbps"] = -1
    return values


def format_speed_summary(result):
    parts = []
    if "download_mbps" in result:
        parts.append(f"down={result['download_mbps']}Mbps")
    if "upload_mbps" in result:
        parts.append(f"up={result['upload_mbps']}Mbps")
    return " " + " ".join(parts) if parts else ""


def test_ip(
    ip,
    index,
    total,
    profile,
    speed_mode=None,
    timeout_ms=2000,
    speed_test_bytes=DEFAULT_SPEED_TEST_BYTES,
    speed_timeout_ms=DEFAULT_SPEED_TEST_TIMEOUT_MS,
    fragment=None,
    process_started=None,
    process_finished=None,
):
    inbound_port = free_port()
    with tempfile.TemporaryDirectory(prefix="xray-iptest-") as td:
        config_path = os.path.join(td, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(make_xray_config(ip, inbound_port, profile, fragment=fragment), f, indent=2)

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(
            [XRAY_EXE, "run", "-config", config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
            text=True,
        )
        if process_started:
            process_started(proc)
        try:
            time.sleep(0.7)
            proxy = f"http://127.0.0.1:{inbound_port}"
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
            req = urllib.request.Request(TEST_URL, headers={"User-Agent": "Mozilla/5.0"})
            start = time.time()
            with opener.open(req, timeout=timeout_ms / 1000) as resp:
                body = resp.read(4096).decode("utf-8", "replace")
            ms = int((time.time() - start) * 1000)
            colo = ""
            warp = ""
            for line in body.splitlines():
                if line.startswith("colo="):
                    colo = line.split("=", 1)[1]
                elif line.startswith("warp="):
                    warp = line.split("=", 1)[1]
            result = {"ip": ip, "ok": True, "ms": ms, "colo": colo, "warp": warp}
            if speed_mode:
                print(colors.info(f"Speed test: currently testing {ip}"), flush=True)
                speed_results, speed_errors = run_speed_tests_with_diagnostics(
                    opener,
                    speed_mode,
                    ip,
                    speed_test_bytes,
                    speed_timeout_ms,
                )
                result.update(speed_results)
                for warning in result.get("speed_warnings", []):
                    print(colors.warning(f"Speed test warning: {warning}"), flush=True)
                if speed_errors:
                    speed_debug = speed_request_debug(speed_mode, speed_test_bytes, speed_timeout_ms)
                    result["ok"] = False
                    result["error"] = "Speed test failed: " + " ; ".join(speed_errors)
                    result["speed_debug"] = speed_debug
                    print(
                        colors.error(
                            f"Speed test failure details: {speed_debug} | {' ; '.join(speed_errors)}"
                        ),
                        flush=True,
                    )
            print(
                (
                    colors.success
                    if result["ok"]
                    else colors.error
                )(
                    f"[{index}/{total}] {'PASS' if result['ok'] else 'FAIL'} "
                    f"{ip} {ms}ms colo={colo} warp={warp}{format_speed_summary(result)}"
                ),
                flush=True,
            )
            return result
        except Exception as exc:
            print(
                colors.error(f"[{index}/{total}] FAIL {ip} {type(exc).__name__}: {str(exc)[:140]}"),
                flush=True,
            )
            return {"ip": ip, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            if process_finished:
                process_finished(proc)
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
