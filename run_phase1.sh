#!/bin/bash
# Waits up to 10 min for the robot, then runs ping, arm-home, drive, demo. Log: phase1.log
cd "$(dirname "$0")"
LOG=phase1.log
: > "$LOG"
echo "waiting for robot at 192.168.149.1:9030 ..." | tee -a "$LOG"
for i in $(seq 1 300); do
  if nc -z -G 1 192.168.149.1 9030 2>/dev/null; then
    echo "robot reachable after ~$((i*2)) s" | tee -a "$LOG"
    sleep 3
    for cmd in "ping" "arm-home" "drive --dir 90 --sec 1" "demo"; do
      echo "== $cmd" | tee -a "$LOG"
      python3 cli.py $cmd >> "$LOG" 2>&1 || { echo "FAILED: $cmd" | tee -a "$LOG"; python3 cli.py stop >> "$LOG" 2>&1; exit 1; }
      sleep 2
    done
    echo "ALL DONE" | tee -a "$LOG"
    exit 0
  fi
  ip=$(ipconfig getifaddr en0)
  if [ -n "$ip" ] && [ "${ip#192.0.0.}" = "$ip" ]; then
    gw=$(route -n get default 2>/dev/null | awk '/gateway/{print $2}')
    ports=""; for p in 22 80 8080 9030; do nc -z -G 1 "${gw:-192.168.149.1}" $p 2>/dev/null && ports="$ports $p"; done
    echo "$(date +%T) on robot wifi? ip=$ip gw=$gw open_on_gw:${ports:- none}" >> "$LOG"
    if [ -n "$gw" ] && [ "$gw" != "192.168.149.1" ] && nc -z -G 1 "$gw" 9030 2>/dev/null; then
      echo "robot RPC found at $gw, use ROBOT_HOST=$gw" >> "$LOG"
    fi
  fi
  sleep 2
done
echo "robot never reachable" | tee -a "$LOG"
exit 1
