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
ROBOT_SSID="${ROBOT_SSID:-HW-676EB762}"
ROBOT_PASS="${ROBOT_PASS:-hiwonder}"
PHONE_SSID="${PHONE_SSID:-iPhone (2)}"
ROBOT=192.168.149.1
DIR="$(cd "$(dirname "$0")" && pwd)"

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
  robot) echo "joining $ROBOT_SSID"; join "$ROBOT_SSID" "$ROBOT_PASS"
         for i in $(seq 1 10); do [ "$(wifi_ip | cut -d. -f1-3)" = 192.168.149 ] && break; sleep 1; done
         status ;;
  phone) echo "joining $PHONE_SSID"; join "$PHONE_SSID"; sleep 3; status ;;
  fix-order) sudo networksetup -ordernetworkservices "iPhone USB" "USB 10/100/1000 LAN" "Pixel 9 Pro" \
               "Pixel 10 Pro XL" "Thunderbolt Bridge" "Wi-Fi" "Tailscale" && echo "iPhone USB is now first" ;;
  start) start ;;
  check) check ;;
  up)    "$0" robot && start && check ;;
  ssh)   ssh pi@$ROBOT ;;
  status|"") status ;;
  *) sed -n '2,10p' "$0" ;;
esac
