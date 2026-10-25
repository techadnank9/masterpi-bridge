"""MasterPi client methods exposed to Gemini as function tools."""
import base64
import json

from masterpi.client import GRIP_CLOSED, GRIP_OPEN, POSES

DIRS = {"forward": 90, "back": 270, "left": 180, "right": 0}


def fn(name, description, props=None, required=None):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []},
    }


BASE_TOOLS = [
    fn("drive", "Drive the mecanum base in a straight line, then stop. About 7 cm per second at speed 20, 15 at speed 40.",
       {"direction": {"type": "string", "enum": list(DIRS), "description": "forward, back, left (strafe), right (strafe)"},
        "seconds": {"type": "number", "description": "0.2 to 3"},
        "speed": {"type": "integer", "description": "10 to 60, default 30"}},
       ["direction", "seconds"]),
    fn("turn", "Rotate the base in place, then stop. Roughly 65 degrees per second.",
       {"clockwise": {"type": "boolean"},
        "seconds": {"type": "number", "description": "0.2 to 3"}},
       ["clockwise", "seconds"]),
    fn("arm_pose", "Move the arm to a named pose. home = upright, tucked over the robot. "
       "reach_r / reach_l = forward and down to the right / left. low = forward and down in front.",
       {"pose": {"type": "string", "enum": list(POSES)}}, ["pose"]),
    fn("arm_to", "Move the gripper tip to a point in the arm frame, in cm: x right, y forward, z up "
       "(the floor is about z = -3.5). Reachable roughly 8-18 cm forward. pitch: gripper angle, 0 level, -90 straight down.",
       {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
        "pitch": {"type": "number", "description": "-90 to 30, default -30"}},
       ["x", "y", "z"]),
    fn("gripper", "Open or close the gripper.",
       {"state": {"type": "string", "enum": ["open", "close"]}}, ["state"]),
    fn("stop", "Stop all wheel motors immediately."),
    fn("battery", "Read the battery voltage in millivolts. Below 7000 needs charging."),
    fn("sonar", "Read the front ultrasonic distance in millimetres."),
    fn("look", "Take a photo with the gripper camera and look at it."),
]

SIM_TOOLS = [
    fn("locate", "Simulated object detector: list objects with their position relative to the arm "
       "(forward_cm, right_cm), distance and bearing (degrees, positive = to the right).",
       {"name": {"type": "string", "description": "optional filter, e.g. 'red' or 'yellow square'"}}),
    fn("approach", "Drive and turn until the named object is lined up about 15 cm in front of the arm, ready to pick or place.",
       {"name": {"type": "string", "description": "e.g. 'red block' or 'yellow square'"}}, ["name"]),
    fn("pick", "Pick up a block: lines up with it if needed, then grasps and lifts it.",
       {"name": {"type": "string", "description": "e.g. 'red block'"}}, ["name"]),
    fn("place_on", "Carry the held block to a target object or square and put it down there.",
       {"name": {"type": "string", "description": "e.g. 'yellow square' or 'blue block' to stack"}}, ["name"]),
]

PHYSICAL = {"drive", "turn", "arm_pose", "arm_to", "gripper", "approach", "pick", "place_on"}
POSE_WORDS = {
    "home": "tuck the arm in",
    "right": "swing the arm to the right",
    "reach_r": "reach forward to the right",
    "reach_l": "reach forward to the left",
    "low": "reach down in front",
}


def tools_for(bot):
    return BASE_TOOLS + (SIM_TOOLS if bot.can_locate else [])


def describe(name, args):
    if name == "drive":
        d = args.get("direction")
        verb = f"drive {d}" if d in ("forward", "back") else f"slide {d}"
        return f"{verb} for {args.get('seconds')} s at speed {args.get('speed', 30)}"
    if name == "turn":
        return f"turn {'clockwise' if args.get('clockwise') else 'counter-clockwise'} for {args.get('seconds')} s"
    if name == "arm_pose":
        return POSE_WORDS.get(args.get("pose"), f"move the arm to {args.get('pose')}")
    if name == "arm_to":
        return f"move the gripper to {args.get('y')} cm ahead, {args.get('x')} cm right, {args.get('z')} cm up"
    if name == "gripper":
        return f"{args.get('state')} the gripper"
    if name == "approach":
        return f"line up with the {args.get('name')}"
    if name == "pick":
        return f"pick up the {args.get('name')}"
    if name == "place_on":
        return f"put it on the {args.get('name')}"
    if name == "locate":
        return f"find {args.get('name') or 'objects'}"
    return name


def _in_reach(o):
    return 12 <= o["forward_cm"] <= 18 and abs(o["right_cm"]) <= 4


def execute(bot, name, args):
    """Runs one tool call. Returns a list of Interactions API result content blocks."""
    def text(s):
        return [{"type": "text", "text": s if isinstance(s, str) else json.dumps(s)}]

    if name == "drive":
        secs = max(0.2, min(3.0, float(args.get("seconds", 1))))
        speed = max(10, min(60, int(args.get("speed", 30))))
        bot.drive(DIRS[args["direction"]], secs, speed=speed)
        return text(f"done: drove {args['direction']} {secs} s at speed {speed}")
    if name == "turn":
        secs = max(0.2, min(3.0, float(args.get("seconds", 1))))
        bot.turn(0.3 if args.get("clockwise") else -0.3, secs)
        return text(f"done: turned for {secs} s")
    if name == "arm_pose":
        return text(f"result: {bot.pose(args['pose'])}")
    if name == "arm_to":
        used = bot.arm_to(float(args["x"]), float(args["y"]), float(args["z"]), float(args.get("pitch", -30)))
        return text("unreachable point" if used is None else f"done, gripper pitch {used} degrees")
    if name == "gripper":
        bot.gripper(GRIP_CLOSED if args.get("state") == "close" else GRIP_OPEN)
        return text(f"gripper {args.get('state')}")
    if name == "stop":
        bot.stop()
        return text("stopped")
    if name == "battery":
        return text(f"{bot.battery()} mV")
    if name == "sonar":
        return text(f"{bot.sonar()} mm")
    if name == "look":
        views = [("robot", "gripper camera")] + ([("lab", "lab overview camera (simulation only)")] if bot.can_locate else [])
        out = []
        for cam, label in views:
            jpg = bot.snapshot(cam)
            if jpg:
                out += [{"type": "text", "text": label},
                        {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}]
        return out or text("camera unavailable")

    # simulation skills (need an object detector)
    if name == "locate":
        return text(bot.locate(args.get("name")))
    if name == "approach":
        return text(bot.approach(args["name"]))
    if name == "pick":
        target = args["name"]
        found = [o for o in bot.locate(target) if o.get("kind", "object") == "object"]
        if not found:
            return text(f"no {args['name']} found")
        o = found[0]
        if o["held"]:
            return text(f"already holding the {o['name']}")
        if not _in_reach(o):
            a = bot.approach(o["name"])
            o = a.get("object") or o
        if not bot.pick(o["right_cm"], o["forward_cm"]):
            return text(f"could not reach the {o['name']} at {o['forward_cm']} cm ahead")
        held = any(x["held"] for x in bot.locate(o["name"]))
        return text(f"{'holding' if held else 'missed'} the {o['name']}")
    if name == "place_on":
        a = bot.approach(args["name"])
        o = a.get("object")
        if not o:
            return text(f"no {args['name']} found")
        z = 1.5 if "block" in o["name"] else -1.5  # stacking needs 3 cm more height
        ok = bot.place(o["right_cm"], o["forward_cm"], z)
        bot.arm_home()
        return text(f"placed on the {o['name']}" if ok else f"could not reach the {o['name']}")
    return text(f"unknown tool {name}")
