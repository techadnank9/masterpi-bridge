#!/bin/bash
# Join robot Wi-Fi, scan all TCP ports on the robot, grab HTTP banners, rejoin hotspot. Log: port_scan.log
SSID="${1:-HW-676EB762}"
cd "$(dirname "$0")"
LOG=port_scan.log
: > "$LOG"
log() { echo "$(date +%T) $*" | tee -a "$LOG"; }
back() { log "switching back to hotspot"; networksetup -setairportpower en0 off; sleep 2; networksetup -setairportpower en0 on; log "done"; }
# trap back EXIT  # not needed: internet comes over iPhone USB

log "joining $SSID"
networksetup -setairportnetwork en0 "$SSID" hiwonder >> "$LOG" 2>&1
for i in $(seq 1 30); do ip=$(ipconfig getifaddr en0); [ "${ip#192.168.149.}" != "$ip" ] && break; sleep 1; done
log "laptop ip=$ip"

python3 - >> "$LOG" 2>&1 <<'EOF'
import socket, urllib.request
from concurrent.futures import ThreadPoolExecutor
H = "192.168.149.1"
def probe(p):
    try:
        with socket.create_connection((H, p), timeout=0.4):
            return p
    except OSError:
        return None
with ThreadPoolExecutor(400) as ex:
    open_ports = [p for p in ex.map(probe, range(1, 65536)) if p]
print("OPEN:", open_ports)
for p in open_ports:
    try:
        s = socket.create_connection((H, p), timeout=1.5); s.settimeout(1.5)
        try: print(p, "banner:", s.recv(120))
        except OSError: print(p, "no banner")
        s.close()
    except OSError as e: print(p, e)
    for method in ("GET", "POST"):
        try:
            req = urllib.request.Request(f"http://{H}:{p}/", method=method,
                data=b'{"jsonrpc":"2.0","method":"GetBatteryVoltage","params":[],"id":1}' if method == "POST" else None,
                headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=2)
            print(p, method, r.status, r.read(200))
        except Exception as e:
            print(p, method, type(e).__name__, str(e)[:120])
EOF
