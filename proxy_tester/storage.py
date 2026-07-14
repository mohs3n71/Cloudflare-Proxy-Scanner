import csv
import json
import os
import time

from .paths import CONFIG_DIR, LOG_DIR, OUTPUT_DIR
from .proxy_config import make_proxy_url


BEST_FRAGMENTS_FILENAME = "best-fragments.json"


def ensure_project_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def config_files():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    files = []
    for name in os.listdir(CONFIG_DIR):
        path = os.path.join(CONFIG_DIR, name)
        if os.path.isfile(path) and name.lower().endswith(".config"):
            files.append(path)
    files.sort(key=lambda path: os.path.basename(path).lower())
    return files


def output_csv_files():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = []
    for name in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, name)
        lowered = name.lower()
        if os.path.isfile(path) and lowered.endswith(".csv") and not lowered.startswith("fragment-scan-"):
            files.append(path)
    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return files


def safe_filename_part(value):
    keep = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            keep.append(char)
        else:
            keep.append("-")
    return "".join(keep).strip("-") or "cloudflare"


def read_working_ips(csv_path):
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip = (row.get("ip") or "").strip()
            if ip:
                rows.append(row)
    return rows


def save_scan_results(passed, prefix="working-cloudflare-proxy-ips"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(OUTPUT_DIR, f"{prefix}-{timestamp}.csv")
    latest_path = os.path.join(OUTPUT_DIR, f"{prefix}-latest.csv")
    headers = ["ip", "latency_ms", "colo", "warp"]
    if any("download_mbps" in result for result in passed):
        headers.append("download_mbps")
    if any("upload_mbps" in result for result in passed):
        headers.append("upload_mbps")

    for path in (out_path, latest_path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in passed:
                row = [r["ip"], r["ms"], r.get("colo", ""), r.get("warp", "")]
                if "download_mbps" in headers:
                    row.append(r.get("download_mbps", ""))
                if "upload_mbps" in headers:
                    row.append(r.get("upload_mbps", ""))
                writer.writerow(row)

    return out_path, latest_path


def save_proxy_configs(csv_path, rows, profile):
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    source_name = safe_filename_part(os.path.splitext(os.path.basename(csv_path))[0])
    out_path = os.path.join(OUTPUT_DIR, f"{profile.protocol}-configs-{source_name}-{timestamp}.txt")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for index, row in enumerate(rows, 1):
            ip = row["ip"].strip()
            latency = (row.get("latency_ms") or "").strip()
            colo = (row.get("colo") or "").strip()
            label_parts = [f"cf-{index:03d}", ip]
            if latency:
                label_parts.append(f"{latency}ms")
            if colo:
                label_parts.append(colo)
            f.write(make_proxy_url(ip, "-".join(label_parts), profile) + "\n")

    return out_path


def fragment_key(ip, config_name, speed_mode):
    return f"{config_name}|{ip}|{speed_mode}"


def load_best_fragments():
    path = os.path.join(OUTPUT_DIR, BEST_FRAGMENTS_FILENAME)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_best_fragment(ip, config_name, speed_mode, fragment, speed_mbps, latency_ms):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = load_best_fragments()
    data[fragment_key(ip, config_name, speed_mode)] = {
        "ip": ip,
        "config": config_name,
        "mode": speed_mode,
        "fragment": fragment,
        "speed_mbps": speed_mbps,
        "latency_ms": latency_ms,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(OUTPUT_DIR, BEST_FRAGMENTS_FILENAME), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_best_fragment(ip, config_name, speed_mode):
    return load_best_fragments().get(fragment_key(ip, config_name, speed_mode))


def save_fragment_scan_results(ip, config_name, speed_mode, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    name = safe_filename_part(f"fragment-scan-{config_name}-{ip}-{speed_mode}")
    out_path = os.path.join(OUTPUT_DIR, f"{name}-{timestamp}.csv")
    headers = [
        "ip",
        "config",
        "mode",
        "packets",
        "interval",
        "length",
        "latency_ms",
        "speed_mbps",
        "ok",
        "error",
    ]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            fragment = row["fragment"]
            result = row.get("result", {})
            writer.writerow(
                {
                    "ip": ip,
                    "config": config_name,
                    "mode": speed_mode,
                    "packets": fragment.get("packets", ""),
                    "interval": fragment.get("interval", ""),
                    "length": fragment.get("length", ""),
                    "latency_ms": result.get("ms", -1),
                    "speed_mbps": row.get("value", -1),
                    "ok": bool(result.get("ok")),
                    "error": result.get("error", ""),
                }
            )
    return out_path


def create_log_file(prefix):
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(LOG_DIR, f"{safe_filename_part(prefix)}-{timestamp}.log")


def append_log_line(log_path, message):
    if not log_path:
        return
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"[{timestamp}] {message}\n")
