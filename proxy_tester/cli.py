import os
import time

from . import cloudflare
from . import colors
from .paths import CONFIG_DIR, OUTPUT_DIR
from .settings import CONCURRENCY_OPTIONS
from .storage import config_files, output_csv_files
from .proxy_config import parse_proxy_config


def ask_int(prompt, minimum, maximum, allow_back=False):
    while True:
        raw = input(prompt).strip()
        if allow_back and raw.lower() in ("0", "b", "back"):
            return None
        try:
            value = int(raw)
        except ValueError:
            back_text = " or 0 to go back" if allow_back else ""
            print(colors.warning(f"Please enter a whole number{back_text}."))
            continue

        if minimum <= value <= maximum:
            return value
        back_text = ", or 0 to go back" if allow_back else ""
        print(colors.warning(f"Please enter a number between {minimum} and {maximum}{back_text}."))


def ask_config():
    files = config_files()
    if not files:
        raise RuntimeError(f"No config files found in {CONFIG_DIR}. Add a text file containing one vless://, vmess://, or trojan:// config.")

    print(colors.title("\nProxy config files:"))
    for index, path in enumerate(files, 1):
        print(f"{colors.info(f'{index:2}.')} {os.path.basename(path)}")

    while True:
        index = ask_int(f"Select config [1-{len(files)}]: ", 1, len(files))
        path = files[index - 1]
        try:
            profile = parse_proxy_config(path)
        except ValueError as exc:
            print(colors.error(f"\n{exc}"))
            print(colors.warning("Select another config file."))
            continue
        print(colors.success(f"Using config: {profile.name}"))
        return profile


def ask_action(settings):
    print(colors.title("\nMain menu:"))
    print(f"{colors.info('1.')} Random IPs from all Cloudflare ranges")
    print(f"{colors.info('2.')} Random IPs from one selected Cloudflare range")
    print(f"{colors.info('3.')} Speed test IPs from a saved output file")
    print(f"{colors.info('4.')} Create configs from a saved output file")
    settings_text = f"(parallel: {settings.concurrency}, timeout: {settings.timeout_ms}ms)"
    print(f"{colors.info('5.')} Settings {colors.muted(settings_text)}")
    print(f"{colors.info('6.')} Exit")
    return ask_int("Action [1-6]: ", 1, 6)


def ask_concurrency(current):
    print(colors.title("\nSettings: parallel testing"))
    for index, value in enumerate(CONCURRENCY_OPTIONS, 1):
        marker = colors.success(" current") if value == current else ""
        print(f"{colors.info(f'{index}.')} {value} parallel tests{marker}")
    print(colors.muted("0. Back"))

    choice = ask_int(
        f"Select parallel test count [1-{len(CONCURRENCY_OPTIONS)}, 0=Back]: ",
        1,
        len(CONCURRENCY_OPTIONS),
        allow_back=True,
    )
    if choice is None:
        return None
    return CONCURRENCY_OPTIONS[choice - 1]


def ask_timeout_ms(current):
    print(colors.title("\nSettings: timeout"))
    print(colors.muted(f"Current timeout: {current}ms"))
    value = ask_int("Enter timeout in milliseconds [0=Back]: ", 1, 999999, allow_back=True)
    return value


def ask_settings(settings):
    while True:
        print(colors.title("\nSettings:"))
        print(f"{colors.info('1.')} Parallel tests {colors.muted(f'(current: {settings.concurrency})')}")
        print(f"{colors.info('2.')} Timeout in milliseconds {colors.muted(f'(current: {settings.timeout_ms}ms)')}")
        print(colors.muted("0. Back"))
        choice = ask_int("Setting [1-2, 0=Back]: ", 1, 2, allow_back=True)
        if choice is None:
            return
        if choice == 1:
            concurrency = ask_concurrency(settings.concurrency)
            if concurrency is not None:
                settings.concurrency = concurrency
                print(colors.success(f"Parallel testing set to {settings.concurrency}."))
        elif choice == 2:
            timeout_ms = ask_timeout_ms(settings.timeout_ms)
            if timeout_ms is not None:
                settings.timeout_ms = timeout_ms
                print(colors.success(f"Timeout set to {settings.timeout_ms}ms."))


def ask_speed_mode():
    print(colors.title("\nSelect speed test type:"))
    print(f"{colors.info('1.')} Download speed")
    print(f"{colors.info('2.')} Upload speed")
    print(f"{colors.info('3.')} Download and upload speed")
    print(colors.muted("0. Back"))
    choice = ask_int("Speed test [1-3, 0=Back]: ", 1, 3, allow_back=True)
    if choice is None:
        return None
    return {
        1: "download",
        2: "upload",
        3: "both",
    }[choice]


def show_cf_ranges(items):
    print(colors.title("\nCloudflare IPv4 ranges:"))
    for index, net in enumerate(items, 1):
        count = colors.muted(f"({cloudflare.usable_hosts(net)} usable IPs)")
        print(f"{colors.info(f'{index:2}.')} {net} {count}")
    print(colors.muted(" 0. Back"))


def ask_candidates(action):
    items = cloudflare.networks()
    if action == 1:
        max_candidates = cloudflare.total_usable_hosts(items)
        limit = ask_int(
            f"How many random Cloudflare IPs should be tested? [1-{max_candidates}, 0=Back]: ",
            1,
            max_candidates,
            allow_back=True,
        )
        if limit is None:
            return None, None
        return list(cloudflare.random_candidates(limit)), "all Cloudflare ranges"

    show_cf_ranges(items)
    range_index = ask_int(f"Select range [1-{len(items)}, 0=Back]: ", 1, len(items), allow_back=True)
    if range_index is None:
        return None, None
    net = items[range_index - 1]
    max_candidates = cloudflare.usable_hosts(net)
    limit = ask_int(
        f"How many random IPs from {net} should be tested? [1-{max_candidates}, 0=Back]: ",
        1,
        max_candidates,
        allow_back=True,
    )
    if limit is None:
        return None, None
    return list(cloudflare.random_candidates_from_network(net, limit)), str(net)


def ask_output_file():
    files = output_csv_files()
    if not files:
        print(colors.warning(f"\nNo CSV output files found in {OUTPUT_DIR}. Run a scan first."))
        return None

    print(colors.title("\nSaved output files:"))
    for index, path in enumerate(files, 1):
        modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))
        print(f"{colors.info(f'{index:2}.')} {os.path.basename(path)} {colors.muted(f'({modified})')}")
    print(colors.muted(" 0. Back"))

    index = ask_int(f"Select output file [1-{len(files)}, 0=Back]: ", 1, len(files), allow_back=True)
    if index is None:
        return None
    return files[index - 1]
