#!/bin/bash
# Join robot Wi-Fi, install SSH key (asks robot password once), inspect robot, run SSH move test,
# then cycle Wi-Fi back to the hotspot. Log: ssh_run.log
SSID="${1:-HW-676EB762}"
ROBOT=pi@192.168.149.1
cd "$(dirname "$0")"
LOG=ssh_run.log
: > "$LOG"
log() { echo "$(date +%T) $*" | tee -a "$LOG"; }
back() { log "switching back to hotspot"; networksetup -setairportpower en0 off; sleep 2; networksetup -setairportpower en0 on; log "done"; }
# trap back EXIT  # not needed: internet comes over iPhone USB

log "joining $SSID"
for i in $(seq 1 24); do
  ip=$(ipconfig getifaddr en0); [ "${ip#192.168.149.}" != "$ip" ] && break
  networksetup -setairportnetwork en0 "$SSID" hiwonder >> "$LOG" 2>&1 || echo "  $SSID not visible yet, is the robot on? retrying..."
  sleep 5
done
for i in $(seq 1 20); do nc -z -G 2 192.168.149.1 22 2>/dev/null && break; echo "  waiting for robot SSH..."; sleep 3; done
log "laptop ip=$ip"

[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -q
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new $ROBOT true 2>/dev/null; then
  echo ">>> Type the robot password when asked: raspberrypi   (Pi 5 image; typing is invisible, then Enter)"
  ssh-copy-id -o StrictHostKeyChecking=accept-new $ROBOT
fi

S="ssh -o BatchMode=yes -o ConnectTimeout=5 $ROBOT"
$S true || { log "SSH key auth failed"; exit 1; }
log "ssh ok. robot info:"
$S 'cat /proc/device-tree/model; echo; ls /home/pi/MasterPi/HiwonderSDK >/dev/null 2>&1 && echo OLD_SDK; ls /home/pi/MasterPi/common >/dev/null 2>&1 && echo NEW_SDK; ls /home/pi/MasterPi; echo "--- services"; systemctl list-units --type=service --all --no-pager | grep -i -E "master|hw|wonder|ros"; echo "--- procs"; ps aux | grep -i -E "masterpi|rpc|ros" | grep -v grep; echo "--- listening"; ss -ltnp 2>/dev/null | head -20; echo "--- wifi conf"; ls /home/pi/hiwonder-toolbox 2>/dev/null; echo "--- sudo"; sudo -n true && echo SUDO_NOPASSWD' >> "$LOG" 2>&1

if grep -q OLD_SDK "$LOG"; then
  log "OLD_SDK: running move test (arm home, forward 1 s)"
  $S 'mkdir -p /home/pi/hack' && scp -q pi_fallback/move_test.py $ROBOT:/home/pi/hack/ \
    && $S 'sudo python3 /home/pi/hack/move_test.py' >> "$LOG" 2>&1
  log "move test exit $?"
elif grep -q NEW_SDK "$LOG"; then
  log "NEW_SDK (Pi 5): running move test (arm home, forward 1 s)"
  $S 'mkdir -p /home/pi/hack' && scp -q pi_fallback/move_test_pi5.py $ROBOT:/home/pi/hack/ \
    && $S 'cd /home/pi/MasterPi && python3 /home/pi/hack/move_test_pi5.py' >> "$LOG" 2>&1
  log "move test exit $?"
else
  log "unknown SDK, skipped move test"
fi
