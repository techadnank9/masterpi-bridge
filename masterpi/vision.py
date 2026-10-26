"""Camera-based find and pick for the real robot (and the twin): colour blobs + visual servoing.

The arm holds one LOOK pose with the gripper camera tilted at the floor ahead. To pick an object the
base slides and drives until the object's blob sits on the GRAB pixel, the spot where an object is when
it is inside the gripper's reach; then a fixed pick runs there. Only the GRAB pixel needs calibrating
(`python3 cli.py calibrate-grab` with an object on the reach spot). The servo learns which way the image
moves for each base motion, so the camera's mounting orientation does not matter.
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np

CALIB = Path(__file__).resolve().parents[1] / "calib.json"
LOOK = (0, 8, 15, -55)          # arm frame cm + requested pitch; solves to pitch -29 on this arm
REACH = (0.0, 15.5)              # x right, y forward (cm) where pick() grabs a floor object
MIN_AREA = 60

# OpenCV HSV: H 0-180. Red wraps around 0.
COLORS = {
    "red": [((0, 110, 70), (8, 255, 255)), ((170, 110, 70), (180, 255, 255))],
    "orange": [((9, 120, 120), (20, 255, 255))],
    "yellow": [((21, 100, 110), (34, 255, 255))],
    "green": [((40, 80, 50), (85, 255, 255))],
    "blue": [((95, 120, 50), (128, 255, 255))],
    "purple": [((129, 60, 50), (165, 255, 255))],
}


def load_calib():
    d = {"grab_px": [319, 400], "signs": {"strafe_u": -1, "drive_v": 1}}  # defaults measured in the twin
    if CALIB.exists():
        d.update(json.loads(CALIB.read_text()))
    return d


def save_calib(**kw):
    d = load_calib()
    d.update(kw)
    CALIB.write_text(json.dumps(d, indent=2))
    return d


def decode(jpg):
    return cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)


def blobs(img, color):
    """Returns blobs of one colour, biggest first: dicts with u, v (pixel centre), area, box."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in COLORS[color]:
        mask |= cv2.inRange(hsv, lo, hi)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    out = [{"u": float(cents[i][0]), "v": float(cents[i][1]), "area": int(stats[i, cv2.CC_STAT_AREA]),
            "box": [int(x) for x in stats[i, :4]]}
           for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_AREA]
    return sorted(out, key=lambda b: -b["area"])


def color_of(name):
    for c in COLORS:
        if c in name.lower():
            return c
    return None


class Eyes:
    """Find, line up with, and pick objects using only the gripper camera."""

    def __init__(self, bot):
        self.bot = bot
        self.cal = load_calib()

    def look(self):
        self.bot.arm_to(*LOOK, movetime_ms=700)
        self.bot._sleep(0.35)  # let the image settle
        jpg = self.bot.snapshot("robot")
        return decode(jpg) if jpg else None

    def see(self):
        """Every coloured blob in view, as a short list Gemini can read."""
        img = self.look()
        if img is None:
            return {"ok": False, "why": "camera unavailable"}
        h, w = img.shape[:2]
        found = []
        for c in COLORS:
            for b in blobs(img, c)[:3]:
                side = "left" if b["u"] < w * 0.4 else "right" if b["u"] > w * 0.6 else "ahead"
                dist = "close" if b["v"] > h * 0.7 else "far" if b["v"] < h * 0.45 else "mid"
                found.append({"color": c, "where": f"{side}, {dist}", "u": round(b["u"]), "v": round(b["v"]),
                              "size_px": b["area"]})
        return {"ok": True, "objects": found}

    def _find(self, color, sweeps=12):
        """Look; if the colour is not in view, turn about 30 degrees and look again (up to a full turn)."""
        for i in range(sweeps):
            img = self.look()
            if img is None:
                return None, None
            bs = blobs(img, color)
            if bs:
                return bs[0], img.shape[:2]
            self.bot.turn(0.3, 0.45)
        return None, None

    def line_up(self, color, tries=24, tol_u=14, tol_v=10):
        """Visual servo until the colour's blob sits on the grab pixel."""
        tu, tv = self.cal["grab_px"]
        signs = dict(self.cal["signs"])
        b, shape = self._find(color)
        if not b:
            return {"ok": False, "why": f"no {color} object in sight after a full turn"}
        last = None
        for _ in range(tries):
            eu, ev = b["u"] - tu, b["v"] - tv
            if abs(eu) <= tol_u and abs(ev) <= tol_v:
                return {"ok": True, "pixel": [round(b["u"]), round(b["v"])]}
            if last is not None:  # learn the sign of each motion from what the image did
                axis, moved, before = last
                after = eu if axis == "strafe_u" else ev
                if abs(before) > 25 and abs(after) > abs(before) + 6:
                    signs[axis] *= -1
            far = ev < -150
            if abs(eu) > tol_u and (abs(eu) > abs(ev) * 0.6 or abs(ev) <= tol_v):
                if far:  # far away: turn toward it, it is quicker than sliding
                    self.bot.turn(0.2 if eu * signs["strafe_u"] < 0 else -0.2, min(1.0, 0.2 + abs(eu) / 400))
                else:
                    right = eu * signs["strafe_u"] < 0
                    self.bot.drive(0 if right else 180, min(1.5, 0.3 + abs(eu) / 260), speed=20)
                last = ("strafe_u", True, eu)
            else:
                fwd = ev * signs["drive_v"] < 0
                self.bot.drive(90 if fwd else 270, min(2.5, 0.3 + abs(ev) / (90 if far else 220)), speed=20)
                last = ("drive_v", True, ev)
            self.bot._sleep(0.15)
            img = self.look()
            bs = blobs(img, color) if img is not None else []
            if not bs:
                b, shape = self._find(color, sweeps=3)
                if not b:
                    return {"ok": False, "why": f"lost sight of the {color} object"}
                last = None
            else:
                b = bs[0]
        if signs != self.cal["signs"]:
            self.cal = save_calib(signs=signs)
        return {"ok": False, "why": "could not line up", "pixel": [round(b["u"]), round(b["v"])]}

    def pick(self, name):
        color = color_of(name)
        if not color:
            return {"ok": False, "why": f"I can only find objects by colour; '{name}' has none I know"}
        r = self.line_up(color)
        if not r["ok"]:
            return r
        ok = self.bot.pick(*REACH)
        self.bot.arm_home()
        return {"ok": ok, "picked": name}

    def place_on(self, name):
        color = color_of(name)
        if not color:
            return {"ok": False, "why": f"I can only find places by colour; '{name}' has none I know"}
        r = self.line_up(color)
        if not r["ok"]:
            return r
        ok = self.bot.place(*REACH, z=-1.0)
        self.bot.arm_home()
        return {"ok": ok, "placed_on": name}

    def calibrate_grab(self, color):
        """With an object of this colour on the reach spot, record where it appears."""
        img = self.look()
        bs = blobs(img, color) if img is not None else []
        if not bs:
            return {"ok": False, "why": f"no {color} object in view"}
        self.cal = save_calib(grab_px=[round(bs[0]["u"]), round(bs[0]["v"])])
        return {"ok": True, "grab_px": self.cal["grab_px"]}
