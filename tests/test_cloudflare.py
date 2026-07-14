import ipaddress
import unittest

from proxy_tester import cloudflare


class CloudflareTests(unittest.TestCase):
    def test_networks_are_valid_ip_networks(self):
        nets = cloudflare.networks()

        self.assertEqual(len(nets), len(cloudflare.CF_CIDRS))
        self.assertTrue(all(isinstance(net, ipaddress.IPv4Network) for net in nets))

    def test_usable_hosts_handles_common_prefixes(self):
        self.assertEqual(cloudflare.usable_hosts(ipaddress.ip_network("192.0.2.0/30")), 2)
        self.assertEqual(cloudflare.usable_hosts(ipaddress.ip_network("192.0.2.0/31")), 2)
        self.assertEqual(cloudflare.usable_hosts(ipaddress.ip_network("192.0.2.1/32")), 1)
        self.assertEqual(cloudflare.usable_hosts(ipaddress.ip_network("2001:db8::/126")), 0)

    def test_total_usable_hosts_sums_networks(self):
        nets = [ipaddress.ip_network("192.0.2.0/30"), ipaddress.ip_network("198.51.100.0/30")]

        self.assertEqual(cloudflare.total_usable_hosts(nets), 4)

    def test_usable_ips_from_network_skips_network_and_broadcast(self):
        net = ipaddress.ip_network("192.0.2.0/30")

        self.assertEqual(list(cloudflare.usable_ips_from_network(net)), ["192.0.2.1", "192.0.2.2"])

    def test_all_candidates_yields_all_ips_from_all_ranges(self):
        nets = [ipaddress.ip_network("192.0.2.0/30"), ipaddress.ip_network("198.51.100.0/31")]

        with unittest.mock.patch.object(cloudflare, "networks", return_value=nets):
            ips = list(cloudflare.all_candidates())

        self.assertEqual(ips, ["192.0.2.1", "192.0.2.2", "198.51.100.0", "198.51.100.1"])

    def test_random_ip_from_network_returns_usable_address_inside_network(self):
        net = ipaddress.ip_network("192.0.2.0/30")

        ip = ipaddress.ip_address(cloudflare.random_ip_from_network(net))

        self.assertIn(ip, net)
        self.assertNotEqual(ip, net.network_address)
        self.assertNotEqual(ip, net.broadcast_address)

    def test_random_candidates_are_unique_and_inside_cloudflare_ranges(self):
        nets = cloudflare.networks()

        ips = list(cloudflare.random_candidates(20))

        self.assertEqual(len(ips), 20)
        self.assertEqual(len(set(ips)), 20)
        self.assertTrue(all(any(ipaddress.ip_address(ip) in net for net in nets) for ip in ips))

    def test_random_candidates_rejects_impossible_limit(self):
        total = cloudflare.total_usable_hosts(cloudflare.networks())

        with self.assertRaises(ValueError):
            list(cloudflare.random_candidates(total + 1))

    def test_random_candidates_from_network_stays_in_selected_network(self):
        net = ipaddress.ip_network("103.21.244.0/22")

        ips = list(cloudflare.random_candidates_from_network(net, 10))

        self.assertEqual(len(ips), 10)
        self.assertEqual(len(set(ips)), 10)
        self.assertTrue(all(ipaddress.ip_address(ip) in net for ip in ips))

    def test_random_candidates_from_network_rejects_impossible_limit(self):
        net = ipaddress.ip_network("192.0.2.0/30")

        with self.assertRaises(ValueError):
            list(cloudflare.random_candidates_from_network(net, 3))


if __name__ == "__main__":
    unittest.main()
