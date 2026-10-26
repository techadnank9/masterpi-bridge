#!/usr/bin/env python3
"""Natural-language control of the MasterPi through Gemini (Interactions API, requests only).

  python3 agent/run.py                 # REPL, every physical action waits for Enter
  python3 agent/run.py --auto          # no confirmation
  python3 agent/run.py --dry-run       # print robot calls instead of sending them
  python3 agent/run.py "wave hello"    # one command, then exit
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.tools import PHYSICAL, describe, execute, tools_for  # noqa: E402
from cli import load_env  # noqa: E402
from masterpi import MasterPi  # noqa: E402

API = "https://generativelanguage.googleapis.com/v1beta/interactions"
SYSTEM = (
    "You control a small Hiwonder MasterPi robot: a mecanum-wheel base with a 4-joint arm, a gripper "
    "and a camera on the gripper. Use the tools to do what the user asks, step by step. Prefer short "
    "moves (1 s or less) and check with look or sonar when position matters. Never drive more than "
    "3 s in one call. If unsure what the user wants, ask instead of moving. When done, reply with "
    "one short sentence."
)
SIM_NOTE = (
    " You are running in a MuJoCo simulation. locate is a perfect object detector: call it first to learn "
    "what is in the scene (kind 'object' can be picked up, kind 'place' is where things go). For moving "
    "things use pick then place_on; they line the robot up by themselves. Check with locate afterwards. "
    "Objects with height_cm above -1 are already stacked or inside something."
)
MAX_STEPS = 16


class Gemini:
    def __init__(self, model, thinking_level, tools=None, sim=False):
        self.key = os.environ.get("GEMINI_API_KEY")
        if not self.key:
            sys.exit("GEMINI_API_KEY missing: add it to masterpi_bridge/.env")
        self.model = model
        self.thinking_level = thinking_level
        self.prev_id = None
        self.tools = tools
        self.system = SYSTEM + (SIM_NOTE if sim else "")

    def send(self, input_):
        body = {"model": self.model, "input": input_, "tools": self.tools, "system_instruction": self.system}
        if self.thinking_level:
            body["generation_config"] = {"thinking_level": self.thinking_level}
        if self.prev_id:
            body["previous_interaction_id"] = self.prev_id
        for attempt in range(3):  # venue Wi-Fi drops connections; retry before giving up
            try:
                r = requests.post(API, json=body, headers={"x-goog-api-key": self.key}, timeout=120)
                break
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise RuntimeError("lost the connection to Gemini (check the laptop's internet)")
                time.sleep(1.5 * (attempt + 1))
        if r.status_code == 400 and self.thinking_level and "thinking" in r.text:
            self.thinking_level = None  # field not accepted for this model: retry without it
            return self.send(input_)
        if not r.ok:
            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:500]}")
        data = r.json()
        self.prev_id = data.get("id", self.prev_id)
        return data


def step_text(step):
    if step.get("type") in ("text", "model_output", "output_text"):
        t = step.get("text")
        if t:
            return t
        return "".join(c.get("text", "") for c in step.get("content", []) if isinstance(c, dict))
    return ""


def ask_terminal(name, args):
    ans = input(f"  plan: {describe(name, args)}  [Enter = run, s = skip, q = stop] ").strip().lower()
    return {"s": "skip", "q": "quit"}.get(ans, "run")


def handle(gem, bot, command, auto, confirm=ask_terminal, log=print):
    """Runs one user command to completion. confirm(name, args) -> 'run' | 'skip' | 'quit'.

    STOP (bot.abort) ends the task between steps or mid-move; the conversation is then reset so
    Gemini does not carry on with the old plan.
    """
    from masterpi.client import Stopped
    try:
        _handle(gem, bot, command, auto, confirm, log)
    except Stopped:
        gem.prev_id = None
        log("task stopped")


def _handle(gem, bot, command, auto, confirm, log):
    from masterpi.client import Stopped
    data = gem.send(command)
    bot.check()
    for _ in range(MAX_STEPS):
        steps = data.get("steps") or data.get("outputs") or []
        calls = [s for s in steps if s.get("type") == "function_call"]
        for s in steps:
            t = step_text(s)
            if t:
                log(f"gemini: {t}")
        if not calls and data.get("output_text") and not any(step_text(s) for s in steps):
            log(f"gemini: {data['output_text']}")
        if not calls:
            return
        results = []
        for c in calls:
            name, args = c.get("name"), c.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            if name in PHYSICAL and not auto:
                ans = confirm(name, args)
                if ans == "quit":
                    bot.stop()
                    results.append({"type": "function_result", "name": name, "call_id": c.get("id"),
                                    "result": [{"type": "text", "text": "user cancelled the task"}]})
                    gem.send(results)
                    return
                if ans == "skip":
                    log(f"  skipped: {describe(name, args)}")
                    results.append({"type": "function_result", "name": name, "call_id": c.get("id"),
                                    "result": [{"type": "text", "text": "user skipped this action"}]})
                    continue
            log(f"  run: {describe(name, args)}")
            bot.check()
            try:
                out = execute(bot, name, args)
            except Stopped:
                raise
            except Exception as e:  # report robot errors back to the model instead of crashing
                bot.stop()
                out = [{"type": "text", "text": f"error: {e}"}]
            log("   -> " + next((b["text"] for b in out if b["type"] == "text"), "image"))
            results.append({"type": "function_result", "name": name, "call_id": c.get("id"), "result": out})
        bot.check()
        data = gem.send(results)
        bot.check()
    log("step limit reached, stopping")
    bot.stop()


def main():
    load_env()
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="*")
    p.add_argument("--auto", action="store_true", help="run physical actions without confirmation")
    p.add_argument("--dry-run", action="store_true", help="print robot calls instead of sending them")
    p.add_argument("--sim", action="store_true", help="drive the MuJoCo twin instead of the robot")
    p.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-4-argon"))
    p.add_argument("--thinking", default=os.environ.get("GEMINI_THINKING", "low"))
    p.add_argument("--host", default=None)
    a = p.parse_args()

    bot = MasterPi(dry_run=a.dry_run, sim=a.sim, host=a.host)
    gem = Gemini(a.model, a.thinking, tools_for(bot), sim=a.sim)
    print(f"model {a.model}, robot {'DRY RUN' if a.dry_run else bot.rpc.url}, "
          f"{'auto' if a.auto else 'confirm each move'}. Ctrl-C stops the robot.")
    try:
        if a.command:
            handle(gem, bot, " ".join(a.command), a.auto)
            return
        while True:
            line = input("\nyou> ").strip()
            if line in ("exit", "quit"):
                break
            if line:
                handle(gem, bot, line, a.auto)
    except (KeyboardInterrupt, EOFError):
        print("\nstopping robot")
    finally:
        try:
            bot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
