import hashlib
import json
import os
import re
import tempfile

from .paths import PROXY_LIBRARY_PATH
from .proxy_config import parse_proxy_url


LIBRARY_SCHEMA_VERSION = 1
PROXY_URL_PATTERN = re.compile(r"(?i)(?:vless|vmess|trojan|ss)://[^\s]+")


def extract_proxy_urls(text):
    urls = []
    seen = set()
    for match in PROXY_URL_PATTERN.finditer(text or ""):
        value = match.group(0).strip().rstrip(",;")
        if value and value not in seen:
            seen.add(value)
            urls.append(value)
    return urls


def entry_id_for(config_url):
    return hashlib.sha256(config_url.encode("utf-8")).hexdigest()[:20]


def make_library_entry(config_url):
    profile = parse_proxy_url(config_url)
    return {
        "id": entry_id_for(config_url),
        "config": config_url,
        "name": profile.name,
        "protocol": profile.protocol,
        "address": profile.address,
        "port": profile.port,
        "latency_ms": "",
        "download_mbps": "",
        "upload_mbps": "",
        "status": "Not tested",
        "error": "",
    }


def import_library_text(entries, text):
    merged = [normalize_library_entry(entry) for entry in entries]
    existing_ids = {entry["id"] for entry in merged}
    added = []
    errors = []
    for config_url in extract_proxy_urls(text):
        try:
            entry = make_library_entry(config_url)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if entry["id"] in existing_ids:
            continue
        existing_ids.add(entry["id"])
        merged.append(entry)
        added.append(entry)
    return merged, added, errors


def normalize_library_entry(entry):
    normalized = {
        "id": str(entry.get("id") or entry_id_for(str(entry.get("config") or ""))),
        "config": str(entry.get("config") or ""),
        "name": str(entry.get("name") or ""),
        "protocol": str(entry.get("protocol") or ""),
        "address": str(entry.get("address") or ""),
        "port": int(entry.get("port") or 0),
        "latency_ms": entry.get("latency_ms", ""),
        "download_mbps": entry.get("download_mbps", ""),
        "upload_mbps": entry.get("upload_mbps", ""),
        "status": str(entry.get("status") or "Not tested"),
        "error": str(entry.get("error") or ""),
    }
    if normalized["config"]:
        try:
            profile = parse_proxy_url(normalized["config"])
        except ValueError:
            pass
        else:
            normalized.update(
                name=profile.name,
                protocol=profile.protocol,
                address=profile.address,
                port=profile.port,
            )
    return normalized


def load_proxy_library(path=PROXY_LIBRARY_PATH):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    raw_entries = data.get("entries", []) if isinstance(data, dict) else []
    return [normalize_library_entry(entry) for entry in raw_entries if isinstance(entry, dict)]


def save_proxy_library(entries, path=PROXY_LIBRARY_PATH):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    payload = {
        "version": LIBRARY_SCHEMA_VERSION,
        "entries": [normalize_library_entry(entry) for entry in entries],
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".proxy-library-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            temporary_path = handle.name
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
    return path


def update_library_result(entry, result, speed_mode):
    updated = dict(entry)
    updated["latency_ms"] = result.get("ms", -1)
    if speed_mode in ("download", "both"):
        updated["download_mbps"] = result.get("download_mbps", -1)
    if speed_mode in ("upload", "both"):
        updated["upload_mbps"] = result.get("upload_mbps", -1)
    updated["error"] = str(result.get("error") or "")
    updated["status"] = "Passed" if result.get("ok") else "Failed"
    return updated
