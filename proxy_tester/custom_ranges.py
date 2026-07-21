import ipaddress


def parse_custom_ranges(text):
    networks = []
    for line_number, line in enumerate(text.splitlines(), 1):
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid IP range on line {line_number}: {value}") from exc
        if network.version != 4:
            raise ValueError(f"Only IPv4 ranges are supported (line {line_number}: {value}).")
        networks.append(network)
    return list(ipaddress.collapse_addresses(networks))


def custom_ranges_text(networks):
    return "\n".join(str(network) for network in networks)
