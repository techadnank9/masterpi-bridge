"""High level MasterPi control. Every base move is time-capped and ends in stop()."""
import math
import threading
import time

from .rpc import MasterPiRPC

HOME = (0, 6, 18, 0)  # x, y, z cm, pitch deg (Hiwonder's own home)
# Stock ArmMoveIk on the Pi 5 image is broken (calls an undefined setPitchRangeMoving), so poses
# are sent as raw pulses. Computed on the robot with ArmIK.setPitchRange; deviation is added server side.
POSES = {
    "home": {3: 695, 4: 2413, 5: 782, 6: 1500},     # (0, 6, 18), pitch 0
    "right": {3: 838, 4: 2477, 5: 872, 6: 1058},    # (5, 6, 18)
    "reach_r": {3: 1064, 4: 2491, 5: 1439, 6: 1266},  # (5, 13, 11), pitch -33
    "reach_l": {3: 1064, 4: 2491, 5: 1439, 6: 1734},  # (-5, 13, 11), pitch -33
    "low": {3: 1193, 4: 2482, 5: 1733, 6: 1500},    # (0, 15, 6), pitch -47
}
GRIP_OPEN, GRIP_CLOSED = 1500, 2000  # calibrate on the real gripper, step by 100
MAX_DRIVE_S = 3.0
MAX_SPEED = 60
A_PLUS_B = 67 + 59  # mm, from common.mecanum


def mecanum_duties(speed, direction_deg, yaw=0.0):
    """Same math as common.mecanum.MecanumChassis.set_velocity, returns motor 1..4 duties."""
    speed = max(-MAX_SPEED, min(MAX_SPEED, speed))
    vx = speed * math.cos(math.radians(direction_deg))
    vy = speed * math.sin(math.radians(direction_deg))
    vp = -yaw * A_PLUS_B
    v1, v2 = int(vy + vx - vp), int(vy - vx + vp)
    v3, v4 = int(vy - vx - vp), int(vy + vx + vp)
    return -v1, v2, -v3, v4


class Stopped(Exception):
    """Raised inside a move when STOP was pressed; the move's finally-block still stops the motors."""


class MasterPi:
    def __init__(self, dry_run=False, sim=False, **kw):
        self.abort = threading.Event()
        if sim:
            from .sim import SimRPC
            kw.pop("host", None)
            self.rpc = SimRPC(**kw)
        elif dry_run:
            from .dryrun import DryRunRPC
            self.rpc = DryRunRPC(**kw)
        else:
            self.rpc = MasterPiRPC(**kw)

    # ---- arm by coordinates (Hiwonder IK ported to the laptop; works on robot and twin) ----
    def _sleep(self, seconds):
        """Sleep in short slices so STOP can cut a move short."""
        seconds = max(0.0, seconds)
        n = max(1, math.ceil(seconds / 0.05))
        for _ in range(n):
            if self.abort.is_set():
                raise Stopped()
            time.sleep(seconds / n)

    def check(self):
        if self.abort.is_set():
            raise Stopped()

    def arm_to(self, x, y, z, pitch=-30.0, movetime_ms=1000):
        """Move the gripper tip to (x right, y forward, z up) cm in the arm frame. Returns used pitch or None."""
        self.check()
        from .ik import solve
        sol = solve(x, y, z, pitch)
        if sol is None:
            return None
        pulses, used = sol
        movetime_ms = max(int(movetime_ms), 300)
        self.rpc.servos_pulse(movetime_ms, pulses)
        self._sleep(movetime_ms / 1000 + 0.15)
        return used

    def pick(self, x, y, z=-2.0):
        """Open, come down on (x, y) from above, close, lift. z=-2 cm is a 3 cm block on the floor."""
        self.gripper(GRIP_OPEN)
        if self.arm_to(x, y, z + 6, -70, 900) is None:
            return False
        if self.arm_to(x, y, z, -70, 700) is None:
            return False
        self.gripper(GRIP_CLOSED, 600)
        self.arm_to(x, y, z + 10, -30, 900)
        return True

    def place(self, x, y, z=-1.0):
        if self.arm_to(x, y, z + 7, -60, 900) is None or self.arm_to(x, y, z, -70, 700) is None:
            return False
        self.gripper(GRIP_OPEN, 500)
        self.arm_to(x, y, z + 8, -30, 700)
        return True

    def turn(self, yaw=0.3, seconds=1.0):
        """Rotate in place. yaw -0.4..0.4, positive is clockwise."""
        yaw = max(-0.4, min(0.4, float(yaw)))
        self.drive(90, seconds, speed=0, yaw=yaw)

    def snapshot(self, cam="robot"):
        if hasattr(self.rpc, "twin"):
            return self.rpc.snapshot(cam)
        return self.rpc.snapshot()

    @property
    def can_locate(self):
        return hasattr(self.rpc, "locate")

    def locate(self, name=None):
        if not self.can_locate:
            raise NotImplementedError("the real robot has no object detector yet; use look instead")
        return self.rpc.locate(name)

    def approach(self, name, reach_cm=15.5, tries=14):
        """Closed loop: face the object, drive until it is reach_cm ahead of the arm, centre it sideways."""
        self.check()
        for _ in range(tries):
            hits = [o for o in self.locate(name) if not o.get("held")]
            if not hits:
                return {"ok": False, "why": f"no {name} found"}
            o = hits[0]
            fwd, right, bearing = o["forward_cm"], o["right_cm"], o["bearing_deg"]
            if abs(fwd - reach_cm) <= 1.5 and abs(right) <= 1.2:
                return {"ok": True, "object": o}
            if o["distance_cm"] > reach_cm + 6 and abs(bearing) > 6:
                self.turn(0.2 if bearing > 0 else -0.2, min(2.5, abs(bearing) / 45.0))
            elif abs(fwd - reach_cm) > 1.5:
                err = fwd - reach_cm
                # speed 20 is ~10 cm/s; the 0.3 s ramp-up costs ~0.15 s of travel
                self.drive(90 if err > 0 else 270, min(3.0, max(0.3, 0.15 + abs(err) / 10.0)), speed=20)
            else:
                self.drive(0 if right > 0 else 180, min(2.0, max(0.3, 0.15 + abs(right) / 10.0)), speed=20)
            self._sleep(0.25)
        o = self.locate(name)
        return {"ok": False, "why": "could not line up", "object": o[0] if o else None}

    def sonar(self):
        return self.rpc.sonar_mm()

    def battery(self):
        return self.rpc.battery_mv()

    def stop(self):
        self.rpc.stop()

    def drive(self, direction_deg=90, seconds=1.0, speed=40, yaw=0.0):
        self.check()
        seconds = max(0.0, min(float(seconds), MAX_DRIVE_S))
        try:
            # Ramp up over ~0.3 s: a full-speed start on all four motors browns out weak batteries
            # and resets the Pi.
            for frac in (0.25, 0.5, 0.75):
                self.rpc.motors(*mecanum_duties(speed * frac, direction_deg, yaw * frac))
                self._sleep(0.1)
            self.rpc.motors(*mecanum_duties(speed, direction_deg, yaw))
            self._sleep(max(0.0, seconds - 0.3))
        finally:
            self.rpc.stop()

    def pose(self, name, movetime_ms=1500):
        self.check()
        movetime_ms = max(int(movetime_ms), 300)
        res = self.rpc.servos_pulse(movetime_ms, POSES[name])
        self._sleep(movetime_ms / 1000 + 0.1)
        return res

    def arm_home(self, movetime_ms=1500):
        return self.pose("home", movetime_ms)

    def arm_ik(self, x, y, z, alpha=0, movetime_ms=1000):
        movetime_ms = max(int(movetime_ms), 300)
        res = self.rpc.arm_ik(x, y, z, alpha, -90, 90, movetime_ms)
        self._sleep(movetime_ms / 1000 + 0.1)
        return res

    def gripper(self, pulse, movetime_ms=500):
        self.check()
        movetime_ms = max(int(movetime_ms), 300)
        self.rpc.servos_pulse(movetime_ms, {1: pulse})
        self._sleep(movetime_ms / 1000)
