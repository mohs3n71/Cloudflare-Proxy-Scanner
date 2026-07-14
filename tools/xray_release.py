import argparse
import json
import os
import platform
import stat
import struct
import sys
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO


XRAY_RELEASE_API = "https://api.github.com/repos/XTLS/Xray-core/releases"
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
        return f"{XRAY_RELEASE_API}/latest"
    tag = version if version.startswith("v") else f"v{version}"
    return f"{XRAY_RELEASE_API}/tags/{urllib.parse.quote(tag)}"


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


def _read_json(url):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Cloudflare-Proxy-Scanner"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _read_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Cloudflare-Proxy-Scanner"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def download_xray(target_os, target_arch, output_dir, version="latest", if_missing=False):
    target_os = normalize_os(target_os)
    target_arch = normalize_arch(target_arch)
    binary_name = archive_binary_name(target_os)
    binary_path = os.path.join(output_dir, binary_name)
    if if_missing and os.path.isfile(binary_path):
        return binary_path, None

    asset_name = xray_asset_name(target_os, target_arch)
    release = _read_json(release_api_url(version))
    download_url = select_release_asset(release, asset_name)
    archive_bytes = _read_bytes(download_url)

    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        member = find_archive_member(archive.namelist(), binary_name)
        binary = archive.read(member)

    os.makedirs(output_dir, exist_ok=True)
    temporary_path = binary_path + ".tmp"
    with open(temporary_path, "wb") as output:
        output.write(binary)
    os.replace(temporary_path, binary_path)
    if target_os != "windows":
        os.chmod(binary_path, os.stat(binary_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return binary_path, release.get("tag_name")


def build_parser():
    parser = argparse.ArgumentParser(description="Download an official Xray binary for a release target.")
    parser.add_argument("--os", dest="target_os", default=detect_os())
    parser.add_argument("--arch", dest="target_arch", default=detect_arch())
    parser.add_argument("--version", default=os.environ.get("XRAY_VERSION", "latest"))
    parser.add_argument("--output-dir", default=os.path.join("bin", "xray"))
    parser.add_argument("--if-missing", action="store_true")
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
        raise SystemExit(f"Xray download failed: {exc}") from exc
    suffix = f" ({version})" if version else " (already present)"
    print(f"Xray ready: {path}{suffix}")


if __name__ == "__main__":
    main()
