#!/bin/bash
# Join robot Wi-Fi, run Phase 1 sequence, then cycle Wi-Fi so the Mac rejoins the internet hotspot.
# Log: phase1.log
SSID="${1:-HW-676EB762}"
PASS="${2:-hiwonder}"
ROBOT=192.168.149.1
cd "$(dirname "$0")"
LOG=phase1.log
: > "$LOG"
log() { echo "$(date +%T) $*" | tee -a "$LOG"; }

log "joining $SSID"
networksetup -setairportnetwork en0 "$SSID" "$PASS" >> "$LOG" 2>&1
for i in $(seq 1 30); do
  ip=$(ipconfig getifaddr en0)
  [ "${ip#192.168.149.}" != "$ip" ] && break
  sleep 1
done
log "laptop ip=$ip"

ok=0
for i in $(seq 1 20); do
  nc -z -G 1 $ROBOT 9030 2>/dev/null && { ok=1; break; }
  sleep 1
done

if [ $ok = 1 ]; then
  log "robot RPC up"
  for cmd in "ping" "arm-home" "drive --dir 90 --sec 1" "demo"; do
    log "== $cmd"
    python3 cli.py $cmd >> "$LOG" 2>&1 || { log "FAILED: $cmd"; python3 cli.py stop >> "$LOG" 2>&1; break; }
    sleep 2
  done
else
  log "port 9030 not open. ping + port scan:"
  ping -c 2 -t 2 $ROBOT >> "$LOG" 2>&1
  for p in 22 80 5900 8080 9030 9090; do nc -z -G 1 $ROBOT $p 2>/dev/null && log "open $p"; done
fi

log "switching back to hotspot"
networksetup -setairportpower en0 off; sleep 2; networksetup -setairportpower en0 on
log "done"
