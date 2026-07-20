import json
import urllib.request


LATEST_RELEASE_API = "https://api.github.com/repos/mohs3n71/Cloudflare-Proxy-Scanner/releases/latest"


def version_tuple(version):
    value = str(version or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]
    parts = value.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid release version: {version!r}")
    numbers = [int(part) for part in parts]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def check_for_update(current_version, opener=urllib.request.urlopen):
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Cloudflare-Proxy-Scanner"},
    )
    with opener(request, timeout=10) as response:
        release = json.loads(response.read().decode("utf-8"))

    if not isinstance(release, dict):
        raise ValueError("GitHub returned invalid release information.")
    latest_version = release.get("tag_name")
    download_url = release.get("html_url")
    if not latest_version or not download_url:
        raise ValueError("GitHub returned incomplete release information.")
    return {
        "available": version_tuple(latest_version) > version_tuple(current_version),
        "version": latest_version,
        "url": download_url,
    }
