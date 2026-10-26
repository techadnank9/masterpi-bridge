#!/usr/bin/env python3
"""Local web UI for the MasterPi Gemini agent. Switch between the MuJoCo twin and the real robot in the page.

  python3 agent/web.py              # http://localhost:3000, starts on the real robot
  python3 agent/web.py --sim        # starts on the MuJoCo twin
  python3 agent/web.py --dry-run    # "Real robot" prints commands instead of sending them
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.run import Gemini, handle  # noqa: E402
from agent.tools import describe, tools_for  # noqa: E402
from cli import load_env  # noqa: E402
from masterpi import MasterPi  # noqa: E402
from masterpi.envs import ENVS  # noqa: E402

REAL_SUGGESTIONS = [
    ("Tuck the arm in", "Moves the arm to its home pose"),
    ("Drive forward a little", "Short, slow move"),
    ("Turn left a bit", "Rotates in place"),
    ("Reach down in front and close the gripper", "Arm down, jaws shut"),
    ("Open the gripper", "Opens the jaws"),
    ("Slide right a little, then come back", "Mecanum strafe"),
]

PAGE = (Path(__file__).parent / "web.html").read_text


class Agent:
    """One command at a time; physical tool calls wait for a Run/Skip/Cancel answer from the page.

    Holds one backend per mode ("sim" = MuJoCo twin, "real" = the robot or dry run) and swaps between them.
    """

    def __init__(self, mode, model, thinking, host=None, dry_run=False):
        self.model, self.thinking, self.host, self.dry_run = model, thinking, host, dry_run
        self.bots = {}
        self.log_lines, self.busy, self.pending = [], False, None
        self._answer, self._cv = None, threading.Condition()
        self.set_mode(mode)

    def set_mode(self, mode):
        if mode not in ("sim", "real"):
            return False
        if self.busy:
            return False
        if mode not in self.bots:
            self.bots[mode] = MasterPi(sim=mode == "sim", dry_run=self.dry_run and mode == "real", host=self.host)
        self.mode, self.bot = mode, self.bots[mode]
        self.gem = Gemini(self.model, self.thinking, tools_for(self.bot), sim=mode == "sim")  # fresh conversation
        self.auto = mode == "sim"  # the twin acts straight away; the robot asks first
        return True

    def log(self, line):
        self.log_lines.append({"t": time.strftime("%H:%M:%S"), "text": line})
        del self.log_lines[:-300]

    def confirm(self, name, args):
        with self._cv:
            self.pending, self._answer = {"name": name, "desc": describe(name, args)}, None
            while self._answer is None:
                self._cv.wait(0.5)
            ans, self.pending = self._answer, None
        return ans

    def answer(self, ans):
        with self._cv:
            if self.pending:
                self._answer = ans
                self._cv.notify_all()

    def run(self, text):
        if self.busy:
            return False
        self.busy = True
        self.bot.abort.clear()
        self.log(f"you: {text}")

        def work():
            try:
                handle(self.gem, self.bot, text, self.auto, confirm=self.confirm, log=self.log)
            except Exception as e:
                self.log(f"error: {e}")
                try:
                    self.bot.stop()  # motors off, but this is a failure, not the user's STOP
                except Exception:
                    pass
            finally:
                self.busy = False

        threading.Thread(target=work, daemon=True).start()
        return True

    def stop(self):
        self.bot.abort.set()   # ends the running task, not just the motors
        self.answer("quit")
        try:
            self.bot.stop()
            self.log("STOP sent to robot")
        except Exception as e:
            self.log(f"STOP failed: {e}")


class Handler(BaseHTTPRequestHandler):
    agent: Agent = None

    @property
    def sim(self):
        return self.agent.mode == "sim"

    @property
    def dry_run(self):
        return self.agent.mode == "real" and self.agent.dry_run

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def query(self):
        from urllib.parse import parse_qs, urlparse
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def stream(self, cam):
        """MJPEG: the browser shows it as a live video in a plain <img>."""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                rpc = self.agent.bot.rpc
                if not hasattr(rpc, "twin"):        # switched to the real robot: end this stream
                    break
                jpg = rpc.twin.frames.get(cam)      # look the twin up every frame: scene switches replace it
                if jpg:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                time.sleep(1 / 12)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        a = self.agent
        if self.path == "/":
            return self.send(200, PAGE(), "text/html; charset=utf-8")
        if self.path == "/state":
            return self.send(200, {"log": a.log_lines, "busy": a.busy, "pending": a.pending,
                                   "auto": a.auto, "dry_run": self.dry_run, "model": a.gem.model,
                                   "robot": a.bot.rpc.url, "sim": self.sim, "mode": a.mode,
                                   "env": a.bot.rpc.twin.env_id if self.sim else None,
                                   "envs": [{"id": k, "name": v["name"]} for k, v in ENVS.items()],
                                   "suggestions": [{"text": t, "hint": h} for t, h in
                                                   (ENVS[a.bot.rpc.twin.env_id]["scenarios"] if self.sim else REAL_SUGGESTIONS)],
                                   "cams": ["lab", "robot", "top"] if self.sim else ["robot"],
                                   "stream": "/stream.mjpg" if self.sim else
                                   None if self.dry_run else f"http://{a.bot.rpc.host}:8080/?action=stream"})
        if self.path == "/battery":
            try:
                return self.send(200, {"mv": a.bot.battery()})
            except Exception as e:
                return self.send(200, {"mv": None, "error": type(e).__name__})
        if self.path.startswith("/stream.mjpg") and self.sim:
            return self.stream(self.query().get("cam", "lab"))
        if self.path.startswith("/snapshot.jpg"):
            try:
                jpg = a.bot.snapshot(self.query().get("cam", "robot"))
            except Exception:
                jpg = None
            return self.send(200, jpg, "image/jpeg") if jpg else self.send(404, {"error": "no camera"})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        a, b = self.agent, self.body()
        if self.path == "/stop":
            a.stop()
            return self.send(200, {"ok": True})
        if self.path == "/command":
            text = (b.get("text") or "").strip()
            return self.send(200, {"ok": bool(text) and a.run(text)})
        if self.path == "/confirm":
            a.answer(b.get("answer") if b.get("answer") in ("run", "skip", "quit") else "skip")
            return self.send(200, {"ok": True})
        if self.path == "/reset" and self.sim:
            a.stop()
            a.bot.rpc.reset()
            a.log("lab reset")
            return self.send(200, {"ok": True})
        if self.path == "/env" and self.sim:
            if a.busy:
                return self.send(409, {"ok": False, "error": "busy"})
            env = b.get("env")
            if env in ENVS:
                a.bot.rpc.set_env(env)
                a.gem = Gemini(a.model, a.thinking, tools_for(a.bot), sim=True)  # new scene, new conversation
                a.log(f"scene: {ENVS[env]['name']}")
            return self.send(200, {"ok": env in ENVS})
        if self.path == "/mode":
            mode = b.get("mode")
            if a.busy:
                return self.send(409, {"ok": False, "error": "busy"})
            if mode != a.mode:
                try:
                    a.bot.stop()
                except Exception:
                    pass
                if not a.set_mode(mode):
                    return self.send(400, {"ok": False})
                a.log(f"mode: {'simulation' if mode == 'sim' else 'real robot'}")
                if mode == "real" and not a.dry_run:
                    try:
                        a.log(f"robot: connected, battery {a.bot.battery()} mV")
                    except Exception as e:
                        a.log(f"error: cannot reach robot ({type(e).__name__})")
            return self.send(200, {"ok": True, "mode": a.mode})
        if self.path == "/auto":
            a.auto = bool(b.get("on"))
            return self.send(200, {"auto": a.auto})
        self.send(404, {"error": "not found"})


def main():
    load_env()
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 3000)))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sim", action="store_true", help="drive the MuJoCo twin instead of the robot")
    p.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-4-argon"))
    p.add_argument("--thinking", default=os.environ.get("GEMINI_THINKING", "low"))
    p.add_argument("--host", default=None)
    a = p.parse_args()

    Handler.agent = agent = Agent("sim" if a.sim else "real", a.model, a.thinking, host=a.host, dry_run=a.dry_run)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"MasterPi agent UI on http://localhost:{a.port}  (starting in {agent.mode} mode)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for bot in agent.bots.values():
            try:
                bot.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
