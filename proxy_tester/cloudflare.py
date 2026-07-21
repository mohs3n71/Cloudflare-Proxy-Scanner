import ipaddress
import random


CF_CIDRS = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
]

RNG = random.SystemRandom()


def networks():
    return [ipaddress.ip_network(cidr) for cidr in CF_CIDRS]


def usable_hosts(net):
    if net.version != 4:
        return 0
    if net.prefixlen >= 31:
        return net.num_addresses
    return net.num_addresses - 2


def total_usable_hosts(items):
    return sum(usable_hosts(net) for net in items)


def usable_ips_from_network(net):
    if usable_hosts(net) <= 0:
        return
    if net.prefixlen >= 31:
        for ip in net:
            yield str(ip)
        return
    current = net.network_address + 1
    last = net.broadcast_address
    while current < last:
        yield str(current)
        current += 1


def all_candidates():
    for net in networks():
        yield from usable_ips_from_network(net)


def random_ip_from_network(net):
    count = usable_hosts(net)
    if count <= 0:
        raise ValueError(f"{net} has no usable IPv4 addresses")

    if net.prefixlen >= 31:
        offset = RNG.randrange(count)
    else:
        offset = RNG.randrange(1, net.num_addresses - 1)
    return str(net.network_address + offset)


def random_candidates(limit):
    items = networks()
    yield from random_candidates_from_networks(items, limit, "Cloudflare IPv4 addresses")


def random_candidates_from_networks(items, limit, description="IPv4 addresses"):
    items = list(items)
    if not items:
        raise ValueError("No IP ranges are available.")
    max_candidates = total_usable_hosts(items)
    if limit > max_candidates:
        raise ValueError(
            f"Requested {limit} IPs, but only {max_candidates} usable {description} are available"
        )
    weights = [usable_hosts(net) for net in items]
    seen = set()
    while len(seen) < limit:
        net = RNG.choices(items, weights=weights, k=1)[0]
        ip = random_ip_from_network(net)
        if ip not in seen:
            seen.add(ip)
            yield ip


def random_candidates_from_network(net, limit):
    max_candidates = usable_hosts(net)
    if limit > max_candidates:
        raise ValueError(
            f"Requested {limit} IPs, but only {max_candidates} usable addresses are available in {net}"
        )

    seen = set()
    while len(seen) < limit:
        ip = random_ip_from_network(net)
        if ip not in seen:
            seen.add(ip)
            yield ip
