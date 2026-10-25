import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run, tools
from masterpi import MasterPi


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.ok, self.text = data, status, status < 400, str(data)

    def json(self):
        return self._d


@pytest.fixture
def gemini(monkeypatch):
    """Scripted Interactions API: first reply asks for tools, second reply is final text."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    sent = []
    replies = [
        {"id": "i1", "steps": [
            {"type": "function_call", "id": "c1", "name": "arm_pose", "arguments": {"pose": "home"}},
            {"type": "function_call", "id": "c2", "name": "drive", "arguments": {"direction": "forward", "seconds": 9}},
        ]},
        {"id": "i2", "steps": [{"type": "text", "text": "Done."}]},
    ]

    def post(url, json, headers, timeout):
        sent.append(json)
        return FakeResp(replies[len(sent) - 1])

    monkeypatch.setattr(run.requests, "post", post)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return sent


def test_loop_runs_tools_and_returns_results(gemini, capsys):
    bot = MasterPi(dry_run=True)
    run.handle(run.Gemini("gemini-4-argon", "low", tools.tools_for(bot)), bot, "go home then forward", auto=True)
    first, second = gemini
    assert first["input"] == "go home then forward"
    assert {t["name"] for t in first["tools"]} >= {"drive", "arm_pose", "look", "stop"}
    assert first["generation_config"] == {"thinking_level": "low"}
    assert second["previous_interaction_id"] == "i1"
    assert [r["call_id"] for r in second["input"]] == ["c1", "c2"]
    assert all(r["type"] == "function_result" for r in second["input"])
    out = capsys.readouterr().out
    assert "drove forward 3.0 s" in out  # 9 s request clamped to 3 s
    assert "gemini: Done." in out


def test_confirm_skip_and_quit(gemini, monkeypatch):
    answers = iter(["skip", "quit"])
    bot = MasterPi(dry_run=True)
    run.handle(run.Gemini("gemini-4-argon", None), bot, "x", auto=False, confirm=lambda n, a: next(answers))
    results = gemini[1]["input"]
    assert "skipped" in results[0]["result"][0]["text"]
    assert "cancelled" in results[1]["result"][0]["text"]
    assert "generation_config" not in gemini[0]


def test_look_without_camera():
    out = tools.execute(MasterPi(dry_run=True), "look", {})
    assert out == [{"type": "text", "text": "camera unavailable"}]


def test_turn_is_pure_rotation(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    bot = MasterPi(dry_run=True)
    calls = []
    bot.rpc.call = lambda m, *p, **k: calls.append((m, p)) or [True, [], m]
    bot.turn(0.3, 1)
    duties = calls[3][1]  # full-speed frame after the ramp
    # Pure yaw: after the per-motor sign flips in mecanum.py every motor gets the same duty
    assert [duties[1], duties[3], duties[5], duties[7]] == [-37, -37, -37, -37]


def test_stop_ends_the_task(monkeypatch):
    """STOP must end the whole task, not just the current move (Gemini would otherwise keep going)."""
    import threading
    import time as _time
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    calls = []

    def post(url, json, headers, timeout):  # a model that never stops asking to drive
        calls.append(json)
        return FakeResp({"id": f"i{len(calls)}", "steps": [
            {"type": "function_call", "id": "c", "name": "drive", "arguments": {"direction": "forward", "seconds": 3}}]})

    monkeypatch.setattr(run.requests, "post", post)
    bot = MasterPi(dry_run=True)
    log = []
    gem = run.Gemini("gemini-4-argon", None, tools.tools_for(bot))
    t = threading.Thread(target=run.handle, args=(gem, bot, "go", True), kwargs={"log": log.append})
    t.start()
    _time.sleep(0.4)
    bot.abort.set()
    t.join(2)
    assert not t.is_alive()
    assert "task stopped" in log and gem.prev_id is None
    assert len(calls) <= 2
