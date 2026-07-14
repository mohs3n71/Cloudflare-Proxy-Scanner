import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import cli, cloudflare
from . import colors
from .display import print_passed_table, progress_text
from .settings import AppSettings
from .storage import ensure_project_dirs, read_working_ips, save_scan_results, save_proxy_configs
from .xray import test_ip


def create_proxy_configs_from_output(profile):
    csv_path = cli.ask_output_file()
    if not csv_path:
        return

    rows = read_working_ips(csv_path)
    if not rows:
        print(colors.warning(f"\nNo working IPs found in {csv_path}."))
        return

    out_path = save_proxy_configs(csv_path, rows, profile)
    print(colors.success(f"\nCreated {len(rows)} {profile.protocol.upper()} configs:"))
    print(colors.info(out_path))


def ips_from_rows(rows):
    return [row["ip"].strip() for row in rows if (row.get("ip") or "").strip()]


def run_speed_test_from_output(profile, settings):
    csv_path = cli.ask_output_file()
    if not csv_path:
        return

    rows = read_working_ips(csv_path)
    ips = ips_from_rows(rows)
    if not ips:
        print(colors.warning(f"\nNo IPs found in {csv_path}."))
        return

    speed_mode = cli.ask_speed_mode()
    if speed_mode is None:
        return
    source = os.path.basename(csv_path)
    run_scan(ips, source, profile, settings, speed_mode=speed_mode)


def worker_count_for(settings, speed_mode=None):
    return 1 if speed_mode else settings.concurrency


def run_scan(ips, source, profile, settings, speed_mode=None):
    scan_type = "Speed testing" if speed_mode else "Testing"
    worker_count = worker_count_for(settings, speed_mode)
    print(
        colors.title(f"{scan_type} {len(ips)} Cloudflare IPs from {source} with {profile.name}..."),
        flush=True,
    )
    print(colors.info(f"Parallel tests: {worker_count}"), flush=True)
    print(colors.info(f"Timeout: {settings.timeout_ms}ms"), flush=True)

    results = []
    passed_so_far = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                test_ip,
                ip,
                index,
                len(ips),
                profile,
                speed_mode=speed_mode,
                timeout_ms=settings.timeout_ms,
            ): ip
            for index, ip in enumerate(ips, 1)
        }
        for completed, future in enumerate(as_completed(futures), 1):
            ip = futures[future]
            result = future.result()
            results.append(result)
            if result["ok"]:
                passed_so_far.append(result)
            print(
                colors.info(f"\nProgress: {progress_text(completed, len(ips))} | finished IP: {ip}"),
                flush=True,
            )
            print_passed_table(passed_so_far)

    passed = [result for result in results if result["ok"]]
    passed.sort(key=lambda result: result["ms"])

    print(colors.title("\nWORKING_IPS"))
    for result in passed:
        print(f"{result['ip']},{result['ms']},{result.get('colo','')},{result.get('warp','')}")

    prefix = "speed-test-cloudflare-proxy-ips" if speed_mode else "working-cloudflare-proxy-ips"
    out_path, latest_path = save_scan_results(passed, prefix=prefix)
    print(colors.success(f"\nSaved {len(passed)} working IPs to {out_path}"))
    print(colors.info(f"Updated latest copy at {latest_path}"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ensure_project_dirs()
    profile = cli.ask_config()
    settings = AppSettings()

    if argv:
        limit = int(argv[0])
        ips = list(cloudflare.random_candidates(limit))
        run_scan(ips, "all Cloudflare ranges", profile, settings)
        return

    while True:
        action = cli.ask_action(settings)
        if action == 6:
            print(colors.success("Goodbye."))
            return
        if action == 3:
            run_speed_test_from_output(profile, settings)
            continue
        if action == 4:
            create_proxy_configs_from_output(profile)
            continue
        if action == 5:
            cli.ask_settings(settings)
            continue

        ips, source = cli.ask_candidates(action)
        if ips is None:
            continue
        run_scan(ips, source, profile, settings)
