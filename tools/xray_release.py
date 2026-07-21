import argparse
import ctypes
import json
import os
import platform
import stat
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO


XRAY_RELEASE_API = "https://api.github.com/repos/XTLS/Xray-core/releases"
XRAY_METADATA_FILE = "xray.metadata.json"
XRAY_ASSETS = {
    ("windows", "x64"): "Xray-windows-64.zip",
    ("windows", "x86"): "Xray-windows-32.zip",
    ("windows", "arm64"): "Xray-windows-arm64-v8a.zip",
    ("linux", "x64"): "Xray-linux-64.zip",
    ("linux", "x86"): "Xray-linux-32.zip",
    ("linux", "arm64"): "Xray-linux-arm64-v8a.zip",
    ("macos", "x64"): "Xray-macos-64.zip",
    ("macos", "arm64"): "Xray-macos-arm64-v8a.zip",
}

OS_ALIASES = {"win32": "windows", "windows": "windows", "linux": "linux", "darwin": "macos", "macos": "macos"}
ARCH_ALIASES = {
    "amd64": "x64",
    "x86_64": "x64",
    "x64": "x64",
    "i386": "x86",
    "i686": "x86",
    "x86": "x86",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def normalize_os(value):
    normalized = OS_ALIASES.get(str(value).strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported operating system: {value}")
    return normalized


def normalize_arch(value):
    normalized = ARCH_ALIASES.get(str(value).strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported architecture: {value}")
    return normalized


def detect_os():
    return normalize_os(sys.platform)


def detect_arch():
    if struct.calcsize("P") == 4:
        return "x86"
    return normalize_arch(platform.machine())


def xray_asset_name(target_os, target_arch):
    key = (normalize_os(target_os), normalize_arch(target_arch))
    try:
        return XRAY_ASSETS[key]
    except KeyError as exc:
        raise ValueError(f"No official Xray release asset for {key[0]} {key[1]}.") from exc


def release_api_url(version):
    version = (version or "latest").strip()
    if version.lower() == "latest":
        return f"{XRAY_RELEASE_API}?per_page=100"
    tag = version if version.startswith("v") else f"v{version}"
    return f"{XRAY_RELEASE_API}/tags/{urllib.parse.quote(tag)}"


def select_latest_published_release(releases):
    published = [release for release in releases if not release.get("draft") and release.get("published_at")]
    if not published:
        raise RuntimeError("Xray does not have a published release.")
    return max(published, key=lambda release: release["published_at"])


def resolve_release(version, timeout=10, attempts=2):
    release_data = _read_json(release_api_url(version), timeout=timeout, attempts=attempts)
    if (version or "latest").strip().lower() == "latest":
        if not isinstance(release_data, list):
            raise RuntimeError("GitHub returned an invalid Xray release list.")
        return select_latest_published_release(release_data)
    return release_data


def select_release_asset(release, asset_name):
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset["browser_download_url"]
    tag = release.get("tag_name", "unknown")
    raise RuntimeError(f"Xray {tag} does not provide {asset_name}.")


def archive_binary_name(target_os):
    return "xray.exe" if normalize_os(target_os) == "windows" else "xray"


def find_archive_member(names, binary_name):
    matches = [name for name in names if os.path.basename(name).lower() == binary_name.lower()]
    if not matches:
        raise RuntimeError(f"Downloaded Xray archive does not contain {binary_name}.")
    return min(matches, key=lambda name: (name.count("/"), len(name)))


def _request_bytes(request, timeout, attempts=3):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt + 1 >= attempts:
                raise
            time.sleep(2**attempt)


def _request_bytes_with_progress(request, timeout, attempts, progress):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                chunks = []
                progress(downloaded, total)
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    progress(downloaded, total)
                return b"".join(chunks)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt + 1 >= attempts:
                raise
            time.sleep(2**attempt)


def _read_json(url, timeout=10, attempts=2):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Cloudflare-Proxy-Scanner"}
    github_token = os.environ.get("GH_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    return json.loads(_request_bytes(request, timeout=timeout, attempts=attempts).decode("utf-8"))


def _read_bytes(url, timeout=120, attempts=3, progress=None):
    request = urllib.request.Request(url, headers={"User-Agent": "Cloudflare-Proxy-Scanner"})
    if progress is not None:
        return _request_bytes_with_progress(request, timeout, attempts, progress)
    return _request_bytes(request, timeout=timeout, attempts=attempts)


def read_xray_metadata(output_dir):
    path = os.path.join(output_dir, XRAY_METADATA_FILE)
    try:
        with open(path, "r", encoding="utf-8") as metadata_file:
            data = json.load(metadata_file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_xray_metadata(output_dir, target_os, target_arch, version):
    path = os.path.join(output_dir, XRAY_METADATA_FILE)
    temporary_path = path + ".tmp"
    metadata = {"os": target_os, "arch": target_arch, "version": version}
    with open(temporary_path, "w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2, sort_keys=True)
        metadata_file.write("\n")
    os.replace(temporary_path, path)


def installed_xray_matches(output_dir, target_os, target_arch, version):
    metadata = read_xray_metadata(output_dir)
    return metadata == {"os": target_os, "arch": target_arch, "version": version}


def download_xray(target_os, target_arch, output_dir, version="latest", if_missing=False, progress=None):
    target_os = normalize_os(target_os)
    target_arch = normalize_arch(target_arch)
    binary_name = archive_binary_name(target_os)
    binary_path = os.path.join(output_dir, binary_name)
    existing_binary = if_missing and os.path.isfile(binary_path)
    temporary_path = binary_path + ".tmp"

    asset_name = xray_asset_name(target_os, target_arch)
    try:
        release = resolve_release(
            version,
            timeout=3 if existing_binary else 10,
            attempts=1 if existing_binary else 2,
        )
        resolved_version = release.get("tag_name")
        if not resolved_version:
            raise RuntimeError("GitHub returned an Xray release without a tag name.")
        if existing_binary and installed_xray_matches(output_dir, target_os, target_arch, resolved_version):
            return binary_path, None

        download_url = select_release_asset(release, asset_name)
        archive_bytes = _read_bytes(
            download_url,
            timeout=30 if existing_binary else 120,
            attempts=1 if existing_binary else 3,
            progress=progress,
        )
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            member = find_archive_member(archive.namelist(), binary_name)
            binary = archive.read(member)

        os.makedirs(output_dir, exist_ok=True)
        with open(temporary_path, "wb") as output:
            output.write(binary)
        os.replace(temporary_path, binary_path)
        if target_os != "windows":
            os.chmod(binary_path, os.stat(binary_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        write_xray_metadata(output_dir, target_os, target_arch, resolved_version)
        return binary_path, resolved_version
    except Exception:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass
        if existing_binary:
            return binary_path, None
        raise


def xray_unavailable_message(output_dir, target_os):
    binary_path = os.path.abspath(os.path.join(output_dir, archive_binary_name(target_os)))
    return (
        "Xray is not available and the automatic download failed.\n\n"
        "Download a compatible Xray binary and copy it to:\n"
        f"{binary_path}\n\n"
        "On Linux or macOS, also make the file executable with chmod +x."
    )


def show_error_dialog(title, message):
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def build_parser():
    parser = argparse.ArgumentParser(description="Download an official Xray binary for a release target.")
    parser.add_argument("--os", dest="target_os", default=detect_os())
    parser.add_argument("--arch", dest="target_arch", default=detect_arch())
    parser.add_argument("--version", default=os.environ.get("XRAY_VERSION", "latest"))
    parser.add_argument("--output-dir", default=os.path.join("bin", "xray"))
    parser.add_argument("--if-missing", action="store_true")
    parser.add_argument("--show-error-dialog", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        path, version = download_xray(
            args.target_os,
            args.target_arch,
            args.output_dir,
            version=args.version,
            if_missing=args.if_missing,
        )
    except Exception as exc:
        message = f"{xray_unavailable_message(args.output_dir, args.target_os)}\n\nError: {exc}"
        if args.show_error_dialog:
            show_error_dialog("Xray Is Required", message)
        raise SystemExit(message) from exc
    suffix = f" ({version})" if version else " (already present)"
    print(f"Xray ready: {path}{suffix}")


if __name__ == "__main__":
    main()
