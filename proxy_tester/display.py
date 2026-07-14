from . import colors


def progress_text(index, total):
    percent = (index / total) * 100 if total else 0
    return f"{index}/{total} ({percent:.1f}%)"


def speed_summary(result):
    parts = []
    if "download_mbps" in result:
        parts.append(f"down={result['download_mbps']} Mbps")
    if "upload_mbps" in result:
        parts.append(f"up={result['upload_mbps']} Mbps")
    return " | ".join(parts)


def print_passed_table(passed):
    if not passed:
        print(colors.warning("\nPASSED SO FAR: none"))
        return

    print(colors.title("\nPASSED SO FAR sorted by ping:"))
    print(colors.muted("PING(ms)  IP               COLO  WARP  SPEED"))
    for result in sorted(passed, key=lambda item: item["ms"]):
        speed = speed_summary(result)
        ping = colors.success(f"{result['ms']:>7}")
        ip = colors.info(f"{result['ip']:<15}")
        speed_text = colors.warning(speed)
        print(
            f"{ping}  {ip}  "
            f"{result.get('colo', ''):<4}  {result.get('warp', ''):<4}  {speed_text}"
        )
