"""MuJoCo twin smoke test: commands go through the same RPC methods as the real robot."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mujoco = pytest.importorskip("mujoco")
from masterpi import MasterPi, ik  # noqa: E402


def base(tw):
    with tw.lock:
        return [float(tw.d.qpos[tw.m.joint(n).qposadr[0]]) for n in ("base_x", "base_y", "base_yaw")]


def test_ik_matches_robot_pulses():
    # pulses computed on the real robot by Hiwonder's ArmIK.setPitchRange
    assert ik.solve(0, 6, 18, 0)[0] == {3: 695, 4: 2413, 5: 782, 6: 1500}
    assert ik.solve(0, 15, 6, -30)[0] == {3: 1193, 4: 2482, 5: 1733, 6: 1500}


def test_twin_drive_turn_and_arm():
    bot = MasterPi(sim=True)
    tw = bot.rpc.twin
    tw.reset()
    time.sleep(0.3)
    x0, y0, _ = base(tw)
    bot.drive(90, 0.8, speed=40)
    time.sleep(0.2)
    x1, y1, _ = base(tw)
    assert x1 - x0 > 0.07 and abs(y1 - y0) < 0.01            # forward is +x in the model
    bot.drive(0, 0.8, speed=40)
    time.sleep(0.2)
    assert base(tw)[1] < y1 - 0.07                           # strafe right is -y
    bot.turn(0.3, 0.8)
    time.sleep(0.2)
    assert base(tw)[2] < -0.5                                # clockwise is negative yaw
    used = bot.arm_to(0, 13, 11, -30, 600)
    time.sleep(0.4)
    with tw.lock:
        R = tw.d.body("chassis").xmat.reshape(3, 3)
        t = R.T @ (tw.d.site("tcp").xpos - tw.d.site("ik_origin").xpos) * 100
    assert used is not None and abs(t[0] - 13) < 0.6 and abs(t[2] - 11) < 0.6
