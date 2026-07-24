import json
import os
from dataclasses import asdict, dataclass

from .paths import BASE_DIR


CONCURRENCY_OPTIONS = [10, 20, 50, 100, 200]
DEFAULT_CONCURRENCY = 50
DEFAULT_TIMEOUT_MS = 2000
DEFAULT_FRAGMENT_ENABLED = False
DEFAULT_FRAGMENT_PACKETS = "tlshello"
DEFAULT_FRAGMENT_INTERVAL = "1-2"
DEFAULT_FRAGMENT_LENGTH = "5-10"
RUNNER_SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
DEFAULT_APPEARANCE_MODE = "light"
APPEARANCE_MODES = ("light", "dark")

SYSTEM_PROXY_DO_NOT_TOUCH = "Leave system proxy unchanged"
SYSTEM_PROXY_SET = "Use Xray as system proxy"
SYSTEM_PROXY_CLEAR = "Clear system proxy settings"
SYSTEM_PROXY_OPTIONS = (SYSTEM_PROXY_DO_NOT_TOUCH, SYSTEM_PROXY_SET, SYSTEM_PROXY_CLEAR)
LEGACY_SYSTEM_PROXY_MODES = {
    "Do not touch system proxy": SYSTEM_PROXY_DO_NOT_TOUCH,
    "Set system proxy": SYSTEM_PROXY_SET,
    "Clear system proxy": SYSTEM_PROXY_CLEAR,
}


@dataclass
class AppSettings:
    concurrency: int = DEFAULT_CONCURRENCY
    timeout_ms: int = DEFAULT_TIMEOUT_MS


@dataclass
class RunnerSettings:
    ip: str = ""
    port: str = "1080"
    share: bool = False
    system_proxy_mode: str = SYSTEM_PROXY_DO_NOT_TOUCH
    fragment_enabled: bool = DEFAULT_FRAGMENT_ENABLED
    fragment_packets: str = DEFAULT_FRAGMENT_PACKETS
    fragment_interval: str = DEFAULT_FRAGMENT_INTERVAL
    fragment_length: str = DEFAULT_FRAGMENT_LENGTH
    speed_size_mb: str = "1"
    speed_timeout_ms: str = "7000"
    fragment_scan_mode: str = "download"
    custom_fragments_text: str = ""

    @classmethod
    def from_dict(cls, values):
        defaults = cls()
        if not isinstance(values, dict):
            return defaults

        settings = cls(
            ip=_string_value(values.get("ip"), defaults.ip, allow_empty=True),
            port=_valid_port(values.get("port"), defaults.port),
            share=_bool_value(values.get("share"), defaults.share),
            system_proxy_mode=_system_proxy_mode(values.get("system_proxy_mode"), defaults.system_proxy_mode),
            fragment_enabled=_bool_value(values.get("fragment_enabled"), defaults.fragment_enabled),
            fragment_packets=_string_value(values.get("fragment_packets"), defaults.fragment_packets),
            fragment_interval=_string_value(values.get("fragment_interval"), defaults.fragment_interval),
            fragment_length=_string_value(values.get("fragment_length"), defaults.fragment_length),
            speed_size_mb=_positive_number_string(values.get("speed_size_mb"), defaults.speed_size_mb),
            speed_timeout_ms=_positive_integer_string(
                values.get("speed_timeout_ms"), defaults.speed_timeout_ms
            ),
            fragment_scan_mode=_choice_value(
                values.get("fragment_scan_mode"), ("download", "upload"), defaults.fragment_scan_mode
            ),
            custom_fragments_text=_string_value(
                values.get("custom_fragments_text"), defaults.custom_fragments_text, allow_empty=True
            ),
        )
        return settings


def load_runner_settings(path=RUNNER_SETTINGS_PATH):
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, ValueError, TypeError):
        return RunnerSettings()
    return RunnerSettings.from_dict(data.get("xray_runner") if isinstance(data, dict) else None)


def save_runner_settings(settings, path=RUNNER_SETTINGS_PATH):
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        pass

    data["xray_runner"] = asdict(settings)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as settings_file:
        json.dump(data, settings_file, indent=2)
        settings_file.write("\n")
    os.replace(temporary_path, path)


def load_custom_range_values(path=RUNNER_SETTINGS_PATH):
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, ValueError, TypeError):
        return []
    values = data.get("custom_ranges") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def save_custom_range_values(values, path=RUNNER_SETTINGS_PATH):
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        pass
    data["custom_ranges"] = list(values)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as settings_file:
        json.dump(data, settings_file, indent=2)
        settings_file.write("\n")
    os.replace(temporary_path, path)


def load_appearance_mode(path=RUNNER_SETTINGS_PATH):
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, ValueError, TypeError):
        return DEFAULT_APPEARANCE_MODE
    value = data.get("appearance") if isinstance(data, dict) else None
    return value if value in APPEARANCE_MODES else DEFAULT_APPEARANCE_MODE


def save_appearance_mode(mode, path=RUNNER_SETTINGS_PATH):
    if mode not in APPEARANCE_MODES:
        raise ValueError(f"Unsupported appearance mode: {mode}")
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        pass
    data["appearance"] = mode
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as settings_file:
        json.dump(data, settings_file, indent=2)
        settings_file.write("\n")
    os.replace(temporary_path, path)


def _string_value(value, default, allow_empty=False):
    if not isinstance(value, str):
        return default
    value = value.strip()
    return value if value or allow_empty else default


def _bool_value(value, default):
    return value if isinstance(value, bool) else default


def _choice_value(value, choices, default):
    return value if value in choices else default


def _system_proxy_mode(value, default):
    value = LEGACY_SYSTEM_PROXY_MODES.get(value, value)
    return _choice_value(value, SYSTEM_PROXY_OPTIONS, default)


def _valid_port(value, default):
    value = _string_value(value, default)
    try:
        return value if 1 <= int(value) <= 65535 else default
    except ValueError:
        return default


def _positive_number_string(value, default):
    value = _string_value(value, default)
    try:
        return value if float(value) > 0 else default
    except ValueError:
        return default


def _positive_integer_string(value, default):
    value = _string_value(value, default)
    try:
        return value if int(value) > 0 else default
    except ValueError:
        return default
