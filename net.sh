#!/bin/bash
# One helper for the robot day. Run from anywhere: ~/Documents/masterpi_bridge/net.sh <command>
#
#   robot      join the robot's Wi-Fi (HW-676EB762)
#   phone      join the iPhone hotspot
#   status     wifi address, robot reachable?, internet?
#   fix-order  put "iPhone USB" ahead of Wi-Fi, so robot Wi-Fi + cable internet work together (asks for password)
#   start      start the robot's control service (needed after every robot boot)
#   check      battery, control server and camera on the robot
#   up         robot + start + check, in one go
#   ssh        open a shell on the robot
#   venue      move the robot onto a building Wi-Fi (asks you for its password); run while on robot Wi-Fi
#   find       find the robot on the current network and save ROBOT_HOST in .env
#   home-ap    put the robot back on its own HW- Wi-Fi (run while you can reach it)
#   isolation  does the Wi-Fi the Mac is on let devices see each other? (test a venue network first)
ROBOT_SSID="${ROBOT_SSID:-HW-676EB762}"
ROBOT_PASS="${ROBOT_PASS:-hiwonder}"
PHONE_SSID="${PHONE_SSID:-iPhone (2)}"
DIR="$(cd "$(dirname "$0")" && pwd)"
ROBOT="$(grep -s '^ROBOT_HOST=' "$DIR/.env" | cut -d= -f2)"; ROBOT="${ROBOT:-192.168.149.1}"

set_host() {  # remember where the robot is, for the web app and the commands below
  touch "$DIR/.env"; grep -v '^ROBOT_HOST=' "$DIR/.env" > "$DIR/.env.tmp"; echo "ROBOT_HOST=$1" >> "$DIR/.env.tmp"
  mv "$DIR/.env.tmp" "$DIR/.env"; ROBOT="$1"
}

wifi_ip() { ifconfig en0 2>/dev/null | awk '/inet /{print $2}'; }

join() {  # ssid [password]; retries while the network appears
  for i in $(seq 1 10); do
    if [ -n "$2" ]; then out=$(networksetup -setairportnetwork en0 "$1" "$2" 2>&1)
    else out=$(networksetup -setairportnetwork en0 "$1" 2>&1); fi
    [ -z "$out" ] && return 0
    echo "  $out (retry $i/10)"; sleep 3
  done
  echo "  gave up: is the network on? (robot: one beep, LED2 flashing)"; return 1
}

status() {
  echo "wifi:     $(wifi_ip || true) $( [ "$(wifi_ip | cut -d. -f1-3)" = 192.168.149 ] && echo '(robot Wi-Fi)')"
  echo "robot at: $ROBOT"
  if nc -z -G 2 $ROBOT 9030 2>/dev/null; then echo "robot:    control server up"
  elif nc -z -G 2 $ROBOT 22 2>/dev/null; then echo "robot:    reachable, control server off  ->  net.sh start"
  else echo "robot:    not reachable"; fi
  curl -s -m 4 -o /dev/null https://www.google.com && echo "internet: yes" || echo "internet: no  ->  net.sh fix-order, phone cable + Personal Hotspot on"
}

start() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 pi@$ROBOT 'sudo systemctl start masterpi.service' \
    && echo "control service started" || { echo "could not start it (robot reachable? run: net.sh status)"; return 1; }
  for i in $(seq 1 15); do nc -z -G 1 $ROBOT 9030 2>/dev/null && { echo "control server up"; return 0; }; sleep 1; done
  echo "service started but port 9030 not open yet"
}

check() {
  echo "battery:  $(python3 "$DIR/cli.py" battery 2>&1 | tail -1) mV  (charge below 7000)"
  nc -z -G 2 $ROBOT 9030 2>/dev/null && echo "control:  ok" || echo "control:  off  ->  net.sh start"
  nc -z -G 2 $ROBOT 8080 2>/dev/null && echo "camera:   ok  http://$ROBOT:8080/?action=stream" || echo "camera:   off"
}

case "$1" in
  robot) set_host 192.168.149.1; echo "joining $ROBOT_SSID"; join "$ROBOT_SSID" "$ROBOT_PASS"
         for i in $(seq 1 10); do [ "$(wifi_ip | cut -d. -f1-3)" = 192.168.149 ] && break; sleep 1; done
         status ;;
  phone) echo "joining $PHONE_SSID"; join "$PHONE_SSID"; sleep 3; status ;;
  fix-order) sudo networksetup -ordernetworkservices "iPhone USB" "USB 10/100/1000 LAN" "Pixel 9 Pro" \
               "Pixel 10 Pro XL" "Thunderbolt Bridge" "Wi-Fi" "Tailscale" && echo "iPhone USB is now first" ;;
  start) start ;;
  check) check ;;
  up)    "$0" robot && start && check ;;
  ssh)   ssh pi@$ROBOT ;;
  venue)
    ssid="${2:-SHACK15_Members}"
    nc -z -G 3 $ROBOT 22 2>/dev/null || { echo "join the robot's Wi-Fi first: net.sh robot"; exit 1; }
    printf "Password for %s (hidden): " "$ssid"; read -rs pass; echo
    # Credentials go over SSH stdin, never on a command line. The robot falls back to its own HW- Wi-Fi
    # if it cannot join, and KEY1 (long press) forces that too.
    printf '%s\n%s\n' "$ssid" "$pass" | ssh -o BatchMode=yes pi@$ROBOT 'sudo python3 -c "
import sys, glob
ssid, pw = sys.stdin.read().split(chr(10))[:2]
path = (glob.glob(\"/home/pi/hiwonder-toolbox/hiwonder_wifi_conf.py\") + glob.glob(\"/home/pi/hiwonder-toolbox/wifi_conf.py\"))[0]
keep = [l for l in open(path).read().splitlines() if not l.strip().startswith((\"HW_WIFI_MODE\", \"HW_WIFI_STA_SSID\", \"HW_WIFI_STA_PASSWORD\"))]
keep += [\"HW_WIFI_MODE = 2\", \"HW_WIFI_STA_SSID = %r\" % ssid, \"HW_WIFI_STA_PASSWORD = %r\" % pw]
open(path, \"w\").write(chr(10).join(keep) + chr(10))
print(\"saved to\", path)
"' || exit 1
    unset pass
    echo "restarting the robot's Wi-Fi; it will leave HW-676EB762 now"
    ssh -o BatchMode=yes pi@$ROBOT 'sudo systemctl restart hw_wifi.service' 2>/dev/null
    echo "next: join $ssid on this Mac, wait ~40 s, then: net.sh find" ;;
  home-ap)
    ssh -o BatchMode=yes pi@$ROBOT 'sudo sed -i -E "s/^(HW_WIFI_MODE|HW_WIFI_STA_SSID|HW_WIFI_STA_PASSWORD)/# \1/" /home/pi/hiwonder-toolbox/*wifi_conf.py && sudo systemctl restart hw_wifi.service' \
      && { set_host 192.168.149.1; echo "robot back on its own Wi-Fi (HW-676EB762) in ~30 s"; } ;;
  isolation)
    ip=$(wifi_ip); [ -z "$ip" ] && { echo "Mac is not on Wi-Fi"; exit 1; }
    echo "Mac on $ip, gateway $(route -n get default 2>/dev/null | awk '/gateway/{print $2}')"
    python3 - "$ip" <<'PY'
import ipaddress, socket, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
ip = sys.argv[1]
net = ipaddress.ip_network(f"{ip}/22" if ip.startswith("10.") else f"{ip}/24", strict=False)
def probe(h):
    for port in (22, 80, 443, 8080, 9030):
        try:
            socket.create_connection((str(h), port), 0.25).close()
            return str(h)
        except OSError:
            pass
with ThreadPoolExecutor(256) as ex:
    peers = [p for p in ex.map(probe, net.hosts()) if p and p != ip]
arp = subprocess.run(["arp", "-an"], capture_output=True, text=True).stdout
macs = {l.split(" at ")[1].split()[0] for l in arp.splitlines() if " at " in l and "incomplete" not in l and "on en0" in l}
print(f"devices answering: {len(peers)}, distinct hardware addresses seen: {len(macs)}")
if len(peers) > 3 and len(macs) <= 2:
    print("ISOLATED: every device answers from the same address (proxy ARP). The robot would be unreachable here.")
elif len(peers) == 0:
    print("ISOLATED or empty: no other device is reachable. The robot would most likely be unreachable here.")
else:
    print("OPEN: devices can see each other. Worth moving the robot here: net.sh venue \"<network name>\"")
PY
    ;;
  find)
    host=$(python3 "$DIR/find_robot.py" | head -1)
    if [ "$host" = "not found" ] || [ -z "$host" ]; then echo "robot not found on this network (venue Wi-Fi may isolate devices)"; exit 1; fi
    echo "robot at $host"; set_host "$host"
    echo "saved ROBOT_HOST=$host in .env; restart the web app to use it" ;;
  status|"") status ;;
  *) sed -n '2,13p' "$0" ;;
esac
