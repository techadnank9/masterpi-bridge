#!/usr/bin/env python3
"""Sweep local /24 subnets for the MasterPi RPC port (9030) and print the host."""
import ipaddress
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

PORT = 9030


def local_ips():
    out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0] == "inet" and not parts[1].startswith("127."):
            yield parts[1]


def open_port(host, timeout=0.2):
    try:
        with socket.create_connection((host, PORT), timeout=timeout):
            return host
    except OSError:
        return None


def main():
    candidates = ["192.168.149.1", "raspberrypi.local"]
    for ip in local_ips():
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
        candidates += [str(h) for h in net.hosts() if str(h) != ip]
    with ThreadPoolExecutor(max_workers=128) as ex:
        for hit in ex.map(open_port, candidates):
            if hit:
                print(hit)
                print(f"put ROBOT_HOST={hit} in .env")
                return
    print("not found")


if __name__ == "__main__":
    main()
