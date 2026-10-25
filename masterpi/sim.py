"""MuJoCo twin of the MasterPi that speaks the same JSON-RPC methods as the robot's rpc_server.py.

Everything above it (mecanum mixing, pulse conversion, Gemini tools, web UI) runs unchanged.
Model: github.com/techadnank9/masterpi-mujoco (masterpi.xml); scenes come from envs.py.

Simplifications, stated so nobody mistakes the twin for the robot:
  * base moves by velocity actuators, not wheel contact (no wheel slip), 0.005 m/s per duty point
  * grasp assist: closing the gripper within 3 cm of an object pins it to the gripper until it
    opens (like robot-gym's capture assist); slide-joint fingers on a 3 cm cube are not reliable
  * locate() is a simulated perfect object detector; the real robot has no equivalent yet
"""
import io
import math
import os
import threading
import time

import mujoco
import numpy as np

from .client import mecanum_duties
from .rpc import K, MasterPiRPC

from .envs import ENVS, build

M_PER_DUTY = 0.005          # m/s of wheel surface speed per motor duty point
A_PLUS_B = 0.126            # m, mecanum a + b
GRIP_OPEN_M, GRIP_CLOSED_M = 0.020, 0.002


class Twin:
    """Owns the model, steps physics in real time, renders cameras on its own thread."""

    CAMS = {"lab": "lab", "robot": "wrist_cam", "top": "top"}

    def __init__(self, env="lab", width=640, height=480, fps=12):
        self.env_id, self.env = env, ENVS[env]
        self.objects = [o[0] for o in self.env["objects"]]
        self.places = [p[0] for p in self.env["places"]]
        self.m = build(env)
        self.d = mujoco.MjData(self.m)
        self.lock = threading.Lock()
        self.act = {self.m.actuator(i).name: i for i in range(self.m.nu)}
        self.duties = (0, 0, 0, 0)
        self.servo_moves = {}          # actuator -> (q0, q1, t0, dur)
        self.grip_target = GRIP_OPEN_M
        self.holding = None
        self.frames = {}
        self.size, self.fps = (height, width), fps
        self.running = True
        self._set_arm({3: 695, 4: 2413, 5: 782, 6: 1500}, instant=True)
        self.d.ctrl[self.act["servo1_gripper"]] = GRIP_OPEN_M
        mujoco.mj_forward(self.m, self.d)
        threading.Thread(target=self._physics, daemon=True).start()
        threading.Thread(target=self._render, daemon=True).start()

    # ---- physics ----
    def _physics(self):
        start_wall, start_sim = time.time(), self.d.time
        while self.running:
            with self.lock:
                target = start_sim + (time.time() - start_wall)
                n = 0
                while self.d.time < target and n < 200:
                    self._apply_controls()
                    mujoco.mj_step(self.m, self.d)
                    n += 1
                if n == 200:  # fell behind: resync instead of spiralling
                    start_wall, start_sim = time.time(), self.d.time
            time.sleep(0.004)

    def _apply_controls(self):
        d1, d2, d3, d4 = self.duties
        v1, v2, v3, v4 = -d1, d2, -d3, d4                    # undo the sign flips in mecanum.py
        vy = (v1 + v2 + v3 + v4) / 4 * M_PER_DUTY            # forward
        vx = (v1 - v2 - v3 + v4) / 4 * M_PER_DUTY            # right
        vp = (-v1 + v2 - v3 + v4) / 4 * M_PER_DUTY
        wz = vp / A_PLUS_B                                   # mecanum.py: vp = -angular_rate*(a+b) -> CCW
        yaw = self.d.qpos[self.m.joint("base_yaw").qposadr[0]]
        fwd, left = vy, -vx
        self.d.ctrl[self.act["drive_vx"]] = fwd * math.cos(yaw) - left * math.sin(yaw)
        self.d.ctrl[self.act["drive_vy"]] = fwd * math.sin(yaw) + left * math.cos(yaw)
        self.d.ctrl[self.act["drive_wz"]] = wz
        t = self.d.time
        for a, (q0, q1, t0, dur) in list(self.servo_moves.items()):
            f = 1.0 if dur <= 0 else min(1.0, (t - t0) / dur)
            self.d.ctrl[a] = q0 + (q1 - q0) * f
            if f >= 1.0:
                del self.servo_moves[a]
        self.d.ctrl[self.act["servo1_gripper"]] = self.grip_target
        self._grasp_assist()

    def _grasp_assist(self):
        closing = self.grip_target < 0.012
        if self.holding is not None and not closing:
            self.holding = None                      # let go: the block falls under physics again
        if closing and self.holding is None:
            tcp = self.d.site("tcp").xpos
            for i, name in enumerate(self.objects):
                b = self.d.body(f"obj_{i}")
                if np.linalg.norm(b.xpos - tcp) < 0.03:
                    g = self.d.body("gripper_base")
                    gR = g.xmat.reshape(3, 3)
                    inv = np.zeros(4)
                    mujoco.mju_negQuat(inv, g.xquat)
                    relq = np.zeros(4)
                    mujoco.mju_mulQuat(relq, inv, b.xquat)
                    self._grip_rel = (gR.T @ (b.xpos - g.xpos), relq)
                    self.holding = i
                    break
        if self.holding is not None:                 # carry: pin the block to the gripper frame
            g = self.d.body("gripper_base")
            relpos, relq = self._grip_rel
            j = self.m.joint(self.m.body(f"obj_{self.holding}").jntadr[0])
            qa, va = j.qposadr[0], j.dofadr[0]
            self.d.qpos[qa:qa + 3] = g.xpos + g.xmat.reshape(3, 3) @ relpos
            q = np.zeros(4)
            mujoco.mju_mulQuat(q, g.xquat, relq)
            self.d.qpos[qa + 3:qa + 7] = q
            self.d.qvel[va:va + 6] = 0

    def _finger_gap(self):
        return abs(self.d.qpos[self.m.joint("finger_left_j").qposadr[0]]) * 2 + 0.0

    # ---- rendering ----
    def _render(self):
        h, w = self.size
        r = mujoco.Renderer(self.m, h, w)
        from PIL import Image
        opt = mujoco.MjvOption()
        opt.flags[mujoco.mjtVisFlag.mjVIS_RANGEFINDER] = 0
        period = 1.0 / self.fps
        while self.running:
            t0 = time.time()
            for key, cam in self.CAMS.items():
                with self.lock:
                    r.update_scene(self.d, camera=cam, scene_option=opt)
                img = r.render()
                if key == "robot":
                    img = img[::-1, ::-1]  # wrist_cam is mounted upside down in the MJCF
                buf = io.BytesIO()
                Image.fromarray(img).save(buf, "JPEG", quality=80)
                self.frames[key] = buf.getvalue()
            time.sleep(max(0.0, period - (time.time() - t0)))

    def frame(self, cam="lab"):
        for _ in range(50):
            if cam in self.frames:
                return self.frames[cam]
            time.sleep(0.05)
        return None

    # ---- actuation used by SimRPC ----
    def _set_arm(self, pulses, use_time_ms=0, instant=False):
        q = {}
        for sid, p in pulses.items():
            deg = (p - 1500) / K
            name = {6: "servo6_base", 5: "servo5_shoulder", 4: "servo4_elbow", 3: "servo3_wrist"}.get(sid)
            if name:
                q[self.act[name]] = math.radians(-deg if sid == 3 else deg)
        if 1 in pulses:
            f = (min(2500, max(500, pulses[1])) - 1500) / 500.0
            self.grip_target = float(np.clip(GRIP_OPEN_M - f * (GRIP_OPEN_M - GRIP_CLOSED_M), GRIP_CLOSED_M, GRIP_OPEN_M))
        for a, q1 in q.items():
            if instant:
                self.d.ctrl[a] = q1
                self.d.qpos[self.m.jnt_qposadr[self.m.actuator_trnid[a, 0]]] = q1
            else:
                self.servo_moves[a] = (float(self.d.ctrl[a]), q1, self.d.time, use_time_ms / 1000.0)

    def set_pulses(self, pulses, use_time_ms):
        with self.lock:
            self._set_arm(pulses, use_time_ms)

    def set_duties(self, duties):
        with self.lock:
            self.duties = tuple(int(x) for x in duties)

    def sonar_mm(self):
        with self.lock:
            vals = [self.d.sensor(n).data[0] for n in ("sonar_left", "sonar_right")]
        vals = [v for v in vals if v >= 0]
        return int(min(vals) * 1000) if vals else 5000

    def locate(self, color=None):
        """Ground-truth object positions in the arm's IK frame (cm, +y forward, +x right)."""
        out = []
        with self.lock:
            R = self.d.body("chassis").xmat.reshape(3, 3)
            o = self.d.site("ik_origin").xpos.copy()
            items = [(n, "object", i, self.d.body(f"obj_{i}").xpos.copy()) for i, n in enumerate(self.objects)]
            items += [(n, "place", i, self.m.geom(f"place_{i}").pos.copy()) for i, n in enumerate(self.places)]
            holding = self.holding
        words = [w for w in (color or "").lower().replace(" block", "").split() if w not in ("the", "a")]
        for name, kind, idx, p in items:
            if words and not all(w in name for w in words):
                continue
            v = R.T @ (p - o) * 100  # model frame: +x forward, +y left
            fwd, right, up = v[0], -v[1], v[2]
            out.append({"name": name, "forward_cm": round(float(fwd), 1), "right_cm": round(float(right), 1),
                        "height_cm": round(float(up), 1), "distance_cm": round(float(math.hypot(fwd, right)), 1),
                        "bearing_deg": round(float(math.degrees(math.atan2(right, fwd))), 1),
                        "kind": kind, "held": kind == "object" and holding == idx})
        return out

    def reset(self):
        with self.lock:
            self.holding = None
            mujoco.mj_resetData(self.m, self.d)
            self.holding, self.duties, self.servo_moves = None, (0, 0, 0, 0), {}
            self.grip_target = GRIP_OPEN_M
            self._set_arm({3: 695, 4: 2413, 5: 782, 6: 1500}, instant=True)
            mujoco.mj_forward(self.m, self.d)


class SimRPC(MasterPiRPC):
    """Drop-in replacement for MasterPiRPC that drives the MuJoCo twin."""

    _twin = None

    def __init__(self, **kw):
        super().__init__(host="sim", **kw)
        if SimRPC._twin is None:
            SimRPC._twin = Twin(os.environ.get("MASTERPI_ENV", "lab"))
        self.url = "mujoco://masterpi"

    @property
    def twin(self):
        return SimRPC._twin

    def set_env(self, env):
        if env not in ENVS or env == self.twin.env_id:
            return
        old = SimRPC._twin
        SimRPC._twin = Twin(env)
        old.running = False

    def call(self, method, *params, tolerate_error=False):
        t = self.twin
        if method == "SetBrushMotor":
            duties = dict(zip(params[0::2], params[1::2]))
            cur = list(t.duties)
            for mid, s in duties.items():
                cur[int(mid) - 1] = max(-100, min(100, int(s)))
            t.set_duties(cur)
            return [True, [], method]
        if method == "SetMovementAngle":
            angle = params[0]
            t.set_duties((0, 0, 0, 0) if angle == -1 else mecanum_duties(70, angle))
            return [True, [], method]
        if method == "SetPWMServo":
            use_time = params[0]
            pulses = {int(sid): round(1500 - ang * K) for sid, ang in zip(params[1::2], params[2::2])}
            t.set_pulses(pulses, use_time)
            return [True, [], method]
        if method == "GetBatteryVoltage":
            return [True, 8100, method]
        if method == "GetSonarDistance":
            return [True, t.sonar_mm(), method]
        if method == "SetSonarRGB":
            return [True, [], method]
        return {"code": -32601, "message": f"{method} not simulated"} if tolerate_error else [False, "E05", method]

    def snapshot(self, cam="robot"):
        return self.twin.frame(cam)

    def locate(self, name=None):
        return self.twin.locate(name)

    def reset(self):
        self.twin.reset()
