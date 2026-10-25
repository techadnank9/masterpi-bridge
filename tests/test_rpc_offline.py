import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from masterpi import rpc as rpcmod
from masterpi.client import MasterPi


class FakeRPC(rpcmod.MasterPiRPC):
    def __init__(self):
        super().__init__(host="x")
        self.calls = []

    def call(self, method, *params, tolerate_error=False):
        self.calls.append((method, params))
        return [True, 7800, method]


def test_body():
    assert rpcmod.build_body("GetBatteryVoltage", [], 1) == {
        "jsonrpc": "2.0", "method": "GetBatteryVoltage", "params": [], "id": 1}


def test_angle_mapping():
    assert rpcmod.pulse_to_rpc_angle(1500) == 0
    assert rpcmod.pulse_to_rpc_angle(500) == pytest.approx(90)
    assert rpcmod.pulse_to_rpc_angle(2500) == pytest.approx(-90)


def test_servo2_refused():
    with pytest.raises(ValueError):
        FakeRPC().servos_pulse(500, {2: 1500})


def test_clamps():
    r = FakeRPC()
    r.servos_pulse(10, {1: 9999})
    method, params = r.calls[-1]
    assert params[0] == 300 and params[2] == pytest.approx(-90)
    r.motors(100, -100, 0, 0)
    assert r.calls[-1][1] == (1, 60, 2, -60, 3, 0, 4, 0)


def test_drive_always_stops(monkeypatch):
    bot = MasterPi(host="x")
    bot.rpc = FakeRPC()
    monkeypatch.setattr("time.sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        bot.drive(90, 10)
    names = [c[0] for c in bot.rpc.calls]
    assert names[0] == "SetBrushMotor" and names[-1] == "SetBrushMotor"


def test_drive_capped(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    bot = MasterPi(host="x")
    bot.rpc = FakeRPC()
    bot.drive(90, 99)
    assert sum(slept) == pytest.approx(3.0)
