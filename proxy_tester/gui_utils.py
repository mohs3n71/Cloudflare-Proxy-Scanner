from ipaddress import ip_address


def table_sort_value(result, column):
    if column == "ping":
        return numeric_sort_value(result.get("ms"), float("inf"))
    if column == "ip":
        try:
            return ip_address(result.get("ip", "0.0.0.0"))
        except ValueError:
            return ip_address("0.0.0.0")
    if column == "download":
        return numeric_sort_value(result.get("download_mbps"), -1)
    if column == "upload":
        return numeric_sort_value(result.get("upload_mbps"), -1)
    return ""


def numeric_sort_value(value, default):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def merge_rows_by_ip(base_rows, updates):
    merged = [dict(row) for row in base_rows]
    positions = {row.get("ip"): index for index, row in enumerate(merged) if row.get("ip")}
    for update in updates:
        ip = update.get("ip")
        if ip in positions:
            merged[positions[ip]] = {**merged[positions[ip]], **update}
        else:
            positions[ip] = len(merged)
            merged.append(dict(update))
    return merged
