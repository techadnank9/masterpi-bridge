#!/usr/bin/env python3
"""MasterPi laptop CLI. `python cli.py stop` must always work."""
import argparse
import os
import sys
from pathlib import Path


def load_env():
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    from masterpi import MasterPi
    from masterpi.client import GRIP_OPEN

    p = argparse.ArgumentParser()
    p.add_argument("--host", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("battery")
    sub.add_parser("stop")
    d = sub.add_parser("drive")
    d.add_argument("--dir", type=int, default=90, help="90 fwd, 0 right, 180 left, 270 back")
    d.add_argument("--sec", type=float, default=1.0)
    d.add_argument("--speed", type=int, default=40, help="0..60")
    po = sub.add_parser("pose")
    po.add_argument("name", help="home, right, reach_r, reach_l, low")
    sub.add_parser("arm-home")
    g = sub.add_parser("gripper")
    g.add_argument("--pulse", type=int, default=GRIP_OPEN)
    sub.add_parser("demo")
    a = p.parse_args()

    bot = MasterPi(host=a.host)
    try:
        if a.cmd == "ping":
            print(f"{bot.rpc.url} battery {bot.battery()} mV")
        elif a.cmd == "battery":
            print(bot.battery())
        elif a.cmd == "stop":
            bot.stop()
            print("stopped")
        elif a.cmd == "drive":
            bot.drive(a.dir, a.sec, a.speed)
            print("done")
        elif a.cmd == "pose":
            print(bot.pose(a.name))
        elif a.cmd == "arm-home":
            print(bot.arm_home())
        elif a.cmd == "gripper":
            bot.gripper(a.pulse)
            print("gripper", a.pulse)
        elif a.cmd == "demo":
            bot.rpc.sonar_rgb(0, 255, 0)
            print("arm home:", bot.arm_home())
            bot.gripper(GRIP_OPEN)
            bot.drive(90, 1.0)
            bot.rpc.sonar_rgb(0, 0, 0)
            print("battery mV:", bot.battery())
    except OSError as e:  # requests' connection errors subclass OSError
        print(f"cannot reach robot at {bot.rpc.url}: {type(e).__name__}")
        print("check: laptop on HW- Wi-Fi? `ipconfig getifaddr en0` should be 192.168.149.x")
        sys.exit(2)
    except KeyboardInterrupt:
        bot.stop()
        print("interrupted, stopped")
        sys.exit(130)


if __name__ == "__main__":
    main()
