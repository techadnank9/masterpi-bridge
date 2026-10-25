"""JSON-RPC client for the stock Hiwonder MasterPi RPCServer (port 9030)."""
import itertools
import os

import requests

K = 2000.0 / 180.0  # us per degree on these PWM servos
VALID_SERVOS = {1, 3, 4, 5, 6}  # id 2 does not exist on this robot


def pulse_to_rpc_angle(pulse: int) -> float:
    """Stock SetPWMServo takes an angle where +90 -> 500us and -90 -> 2500us (0 -> 1500)."""
    return (1500 - pulse) / K


def build_body(method, params, req_id):
    return {"jsonrpc": "2.0", "method": method, "params": list(params), "id": req_id}


class MasterPiRPC:
    def __init__(self, host=None, port=None, timeout=3.0):
        self.host = host or os.getenv("ROBOT_HOST", "192.168.149.1")
        self.port = int(port or os.getenv("ROBOT_RPC_PORT", "9030"))
        self.url = f"http://{self.host}:{self.port}/"
        self.timeout = timeout
        self._ids = itertools.count(1)

    def call(self, method, *params, tolerate_error=False):
        body = build_body(method, params, next(self._ids))
        r = requests.post(self.url, json=body, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            if tolerate_error:
                return data["error"]
            raise RuntimeError(f"{method}: {data['error']}")
        return data.get("result")

    # chassis
    def move(self, direction_deg):
        # Speed fixed at 70 by stock server. Stock code returns a JSON-RPC error on success
        # (unbound variable), so errors are tolerated here and callers always follow with stop().
        return self.call("SetMovementAngle", int(direction_deg), tolerate_error=True)

    def stop(self):
        # Belt and braces: stop via movement angle and zero the motors directly.
        try:
            self.call("SetMovementAngle", -1, tolerate_error=True)
        finally:
            self.motors(0, 0, 0, 0)

    def motors(self, m1, m2, m3, m4):
        args = []
        for i, s in enumerate((m1, m2, m3, m4), start=1):
            args += [i, max(-60, min(60, int(s)))]
        return self.call("SetBrushMotor", *args)

    # arm
    def servos_pulse(self, use_time_ms, pulses: dict):
        # Pi 5 image: [time, id, angle, ...] with no servo count (the 4B image had a count after time)
        args = [max(300, int(use_time_ms))]
        for sid, p in pulses.items():
            sid = int(sid)
            if sid not in VALID_SERVOS:
                raise ValueError(f"invalid servo id {sid}")
            args += [sid, pulse_to_rpc_angle(max(500, min(2500, int(p))))]
        return self.call("SetPWMServo", *args)

    def arm_ik(self, x, y, z, alpha=0, alpha1=-90, alpha2=90, movetime_ms=1000):
        return self.call("ArmMoveIk", x, y, z, alpha, alpha1, alpha2, max(300, int(movetime_ms)))

    # telemetry
    def battery_mv(self):
        res = self.call("GetBatteryVoltage")
        return res[1] if isinstance(res, list) else res

    def sonar_rgb(self, r, g, b):
        return self.call("SetSonarRGB", 0, r, g, b, tolerate_error=True)

    def sonar_mm(self):
        res = self.call("GetSonarDistance", tolerate_error=True)
        return res[1] if isinstance(res, list) and res and res[0] is True else None

    # camera (mjpg_server.py on the robot, port 8080)
    def snapshot(self):
        """Returns one JPEG frame as bytes, or None if the stream is not available."""
        base = f"http://{self.host}:8080"
        for path in ("/?action=snapshot", "/snapshot"):
            try:
                r = requests.get(base + path, timeout=self.timeout)
                if r.ok and r.content[:2] == b"\xff\xd8":
                    return r.content
            except requests.RequestException:
                pass
        # Fall back to pulling the first frame out of the MJPEG stream
        try:
            with requests.get(base + "/?action=stream", stream=True, timeout=self.timeout) as r:
                buf = b""
                for chunk in r.iter_content(4096):
                    buf += chunk
                    a, b = buf.find(b"\xff\xd8"), buf.find(b"\xff\xd9")
                    if a != -1 and b > a:
                        return buf[a:b + 2]
                    if len(buf) > 2_000_000:
                        break
        except requests.RequestException:
            pass
        return None
