#!/usr/bin/env python3
"""Sweep local /24 subnets for the MasterPi RPC port (9030) and print the host."""
import ipaddress
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

PORT = 9030


def local_nets():
    """Yields each local IPv4 network (venue Wi-Fi is often /22, so honour the real netmask, capped at /22)."""
    out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[0] == "inet" and not parts[1].startswith(("127.", "169.254.", "192.0.0.")):
            mask = parts[3]
            bits = bin(int(mask, 16)).count("1") if mask.startswith("0x") else 24
            yield parts[1], max(22, min(bits, 30))


def open_port(host, timeout=0.2):
    try:
        with socket.create_connection((host, PORT), timeout=timeout):
            return host
    except OSError:
        return None


def main():
    candidates = ["192.168.149.1", "raspberrypi.local"]
    for ip, bits in local_nets():
        net = ipaddress.ip_network(f"{ip}/{bits}", strict=False)
        candidates += [str(h) for h in net.hosts() if str(h) != ip]
    with ThreadPoolExecutor(max_workers=128) as ex:
        for hit in ex.map(open_port, candidates):
            if hit:
                print(hit)
                return
    print("not found")


if __name__ == "__main__":
    main()
