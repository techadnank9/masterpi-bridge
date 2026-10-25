"""Simulated environments for the MasterPi twin: scenery, things to pick up, places to put them, scenarios.

Coordinates are world metres. The robot starts at the origin facing +x; its arm reaches floor objects
about 0.22 m ahead of the chassis centre. Textures are CC0 from polyhaven.com (assets/textures).
"""
import os
from pathlib import Path

import mujoco

TEX = Path(__file__).resolve().parents[1] / "assets" / "textures"
MODEL = os.environ.get("MASTERPI_MJCF", os.path.expanduser("~/Documents/masterpi-mujoco/masterpi.xml"))

BOX, CYL, SPH = mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_CYLINDER, mujoco.mjtGeom.mjGEOM_SPHERE
RED, BLUE, GREEN = (0.86, 0.16, 0.16, 1), (0.16, 0.36, 0.86, 1), (0.16, 0.66, 0.30, 1)
YELLOW, ORANGE, PURPLE = (1.0, 0.82, 0.1, 1), (1.0, 0.5, 0.1, 1), (0.55, 0.3, 0.8, 1)
CARDBOARD = (0.72, 0.56, 0.38, 1)

# Pickable object: (name, shape, half-size, rgba, x, y)
# Place: (name, kind, x, y, rgba, half-size)  kind = "pad" (flat) or "bin" (low walls)
# Decor: (shape, pos, size, rgba or texture name, collides)
ENVS = {
    "lab": {
        "name": "Basic lab",
        "floor": None,
        "objects": [("red block", BOX, 0.015, RED, 0.23, 0.00),
                    ("blue block", BOX, 0.015, BLUE, 0.52, 0.22),
                    ("green block", BOX, 0.015, GREEN, 0.45, -0.32)],
        "places": [("yellow square", "pad", 0.10, 0.38, YELLOW, 0.06)],
        "decor": [(BOX, (1.45, 0, 0.1), (0.02, 0.75, 0.1), (0.75, 0.78, 0.85, 1), True)],
        "tape": True,
        "scenarios": [
            ("Put the red block on the yellow square", "One pick and one place"),
            ("Stack the blue block on the red one", "Pick, carry and stack"),
            ("Build a tower of all three blocks on the yellow square", "Plans a 3-step stack"),
            ("Put the green block on the yellow square", "Drives across the lab first"),
        ],
    },
    "living_room": {
        "name": "Living room tidy-up",
        "floor": ("laminate_floor_02", 5),
        "sky": ((0.92, 0.9, 0.86), (0.75, 0.72, 0.68)),
        "light": (1.0, 0.95, 0.88),
        "objects": [("red toy block", BOX, 0.015, RED, 0.24, 0.05),
                    ("green ball", SPH, 0.015, GREEN, 0.55, -0.30),
                    ("purple toy block", BOX, 0.015, PURPLE, 0.70, 0.30),
                    ("orange toy block", BOX, 0.015, ORANGE, 0.10, -0.42)],
        "places": [("toy box", "bin", -0.12, 0.42, (0.85, 0.35, 0.3, 1), 0.075)],
        "decor": [
            (BOX, (0.62, 0.0, 0.003), (0.32, 0.24, 0.003), (0.55, 0.16, 0.2, 1), False),     # rug
            (BOX, (1.25, 0.0, 0.22), (0.18, 0.7, 0.22), (0.35, 0.42, 0.55, 1), True),         # sofa base
            (BOX, (1.40, 0.0, 0.5), (0.05, 0.7, 0.12), (0.32, 0.38, 0.5, 1), True),           # sofa back
            (BOX, (0.95, 0.0, 0.38), (0.14, 0.26, 0.015), "wood_table_001", True),            # coffee table top
            *[(CYL, (0.95 + dx, dy, 0.18), (0.012, 0.18), (0.3, 0.2, 0.12, 1), True)
              for dx in (-0.12, 0.12) for dy in (-0.23, 0.23)],                                # table legs
            (BOX, (-0.2, -0.9, 0.45), (0.4, 0.03, 0.45), (0.93, 0.91, 0.87, 1), True),        # wall
            (CYL, (-0.35, 0.75, 0.15), (0.1, 0.15), (0.78, 0.45, 0.3, 1), True),              # plant pot
            (SPH, (-0.35, 0.75, 0.38), (0.14,), (0.25, 0.5, 0.28, 1), True),                   # plant
        ],
        "scenarios": [
            ("Tidy up: put every toy in the toy box", "Plans the order, four pick-and-places"),
            ("Put the green ball in the toy box", "Picks a ball, not a block"),
            ("Put the purple toy block in the toy box", "Fetches it from the rug"),
            ("Stack the orange toy block on the red one", "Carry and stack"),
        ],
    },
    "warehouse": {
        "name": "Warehouse sorting",
        "floor": ("concrete_floor_worn_001", 6),
        "sky": ((0.55, 0.58, 0.62), (0.25, 0.27, 0.3)),
        "light": (0.95, 0.97, 1.0),
        "objects": [("red parcel", BOX, 0.016, RED, 0.24, 0.0),
                    ("blue parcel", BOX, 0.016, BLUE, 0.40, -0.18),
                    ("green parcel", BOX, 0.016, GREEN, 0.42, 0.20),
                    ("brown parcel", BOX, 0.016, CARDBOARD, 0.60, 0.02)],
        "places": [("red bin", "bin", -0.10, 0.40, RED, 0.06),
                   ("blue bin", "bin", 0.12, 0.45, BLUE, 0.06),
                   ("green bin", "bin", 0.34, 0.50, GREEN, 0.06),
                   ("returns pallet", "pad", 0.05, -0.45, CARDBOARD, 0.09)],
        "decor": [
            *[(BOX, (1.3, y, 0.35), (0.12, 0.25, 0.35), (0.25, 0.32, 0.55, 1), True) for y in (-0.55, 0.0, 0.55)],  # racks
            *[(BOX, (1.3, y, h), (0.13, 0.26, 0.01), "plywood", False) for y in (-0.55, 0.0, 0.55) for h in (0.25, 0.5)],
            (BOX, (0.45, 0.75, 0.001), (0.9, 0.02, 0.001), YELLOW, False),                   # safety tape
            (BOX, (0.45, -0.75, 0.001), (0.9, 0.02, 0.001), YELLOW, False),
        ],
        "scenarios": [
            ("Sort every coloured parcel into the bin of the same colour", "Matches colours, three runs"),
            ("Put the brown parcel on the returns pallet", "No bin matches it"),
            ("Move the red parcel to the red bin", "One pick and drop"),
            ("Put the blue parcel in the blue bin", "One pick and drop"),
        ],
    },
    "mars": {
        "name": "Mars outpost",
        "floor": ("red_laterite_soil_stones", 4),
        "sky": ((0.85, 0.6, 0.42), (0.35, 0.18, 0.12)),
        "light": (1.0, 0.82, 0.65),
        "objects": [("blue mineral", SPH, 0.016, (0.2, 0.55, 0.95, 1), 0.25, 0.04),
                    ("green crystal", BOX, 0.014, (0.35, 0.9, 0.55, 1), 0.55, -0.35),
                    ("grey rock", SPH, 0.016, (0.45, 0.42, 0.4, 1), 0.45, 0.30)],
        "places": [("sample tray", "bin", 0.0, -0.45, (0.85, 0.87, 0.9, 1), 0.06),
                   ("landing pad", "pad", -0.25, 0.40, (0.9, 0.9, 0.95, 1), 0.09)],
        "decor": [
            (CYL, (1.15, 0.45, 0.25), (0.22, 0.25), (0.88, 0.9, 0.92, 1), True),             # lander body
            *[(CYL, (1.15 + dx, 0.45 + dy, 0.06), (0.015, 0.06), (0.5, 0.5, 0.55, 1), True)
              for dx, dy in ((0.25, 0), (-0.25, 0), (0, 0.25), (0, -0.25))],
            (BOX, (1.0, -0.45, 0.25), (0.02, 0.3, 0.18), (0.12, 0.18, 0.4, 1), True),          # solar panel
            *[(SPH, p, (r,), (0.45, 0.24, 0.16, 1), True) for p, r in
              (((0.8, -0.05, 0.03), 0.05), ((0.25, -0.65, 0.02), 0.035), ((-0.4, -0.1, 0.04), 0.06),
               ((0.7, 0.62, 0.025), 0.04))],
        ],
        "scenarios": [
            ("Collect the blue mineral and put it in the sample tray", "Avoids rocks on the way"),
            ("Bring every sample except plain rock to the sample tray", "Decides what counts as a sample"),
            ("Put the green crystal in the sample tray", "Long drive, then a drop"),
            ("Put the grey rock on the landing pad", "Carry to the pad"),
        ],
    },
}


def _material(spec, tex, repeat):
    name = f"mat_{tex}"
    if not any(m.name == name for m in spec.materials):
        spec.add_texture(name=f"tex_{tex}", type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(TEX / f"{tex}.png"))
        m = spec.add_material(name=name, texrepeat=[repeat, repeat], reflectance=0.02)
        m.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = f"tex_{tex}"
    return name


def build(env_id="lab"):
    env = ENVS[env_id]
    spec = mujoco.MjSpec.from_file(MODEL)
    wb = spec.worldbody

    if env.get("floor"):
        tex, rep = env["floor"]
        floor = next(g for g in wb.geoms if g.name == "floor")
        floor.material = _material(spec, tex, rep)
    if env.get("sky"):
        top, bottom = env["sky"]
        for t in spec.textures:
            if t.type == mujoco.mjtTexture.mjTEXTURE_SKYBOX:
                t.rgb1, t.rgb2 = list(top), list(bottom)
    if env.get("light"):
        for light in spec.worldbody.lights:
            if light.name == "key":
                light.diffuse = [c * 0.8 for c in env["light"]]

    for i, (name, shape, h, rgba, x, y) in enumerate(env["objects"]):
        b = wb.add_body(name=f"obj_{i}", pos=[x, y, h + 0.0005])
        b.add_freejoint()
        size = [h, h, h] if shape == BOX else [h, 0, 0]
        b.add_geom(type=shape, size=size, rgba=list(rgba), mass=0.012, friction=[1.2, 0.02, 0.001], condim=4)

    for i, (name, kind, x, y, rgba, s) in enumerate(env["places"]):
        if kind == "pad":
            g = wb.add_geom(name=f"place_{i}", type=BOX, pos=[x, y, 0.0008], size=[s, s, 0.0008], rgba=list(rgba))
            g.contype = g.conaffinity = 0
        else:  # bin: floor plate + four 2.4 cm walls
            wb.add_geom(name=f"place_{i}", type=BOX, pos=[x, y, 0.002], size=[s, s, 0.002], rgba=list(rgba))
            wall = [0.024 / 2, 0.003]
            for dx, dy, sx, sy in ((s, 0, wall[1], s), (-s, 0, wall[1], s), (0, s, s, wall[1]), (0, -s, s, wall[1])):
                wb.add_geom(type=BOX, pos=[x + dx, y + dy, 0.004 + wall[0]], size=[sx, sy, wall[0]], rgba=list(rgba))

    for shape, pos, size, look, collides in env["decor"]:
        kw = {"material": _material(spec, look, 1)} if isinstance(look, str) else {"rgba": list(look)}
        size = list(size) + [0] * (3 - len(size))
        g = wb.add_geom(type=shape, pos=list(pos), size=size, **kw)
        if not collides:
            g.contype = g.conaffinity = 0

    if env.get("tape"):
        for (x, y, sx, sy) in [(0.45, 0.75, 0.95, 0.008), (0.45, -0.75, 0.95, 0.008),
                               (-0.5, 0, 0.008, 0.75), (1.4, 0, 0.008, 0.75)]:
            g = wb.add_geom(type=BOX, pos=[x, y, 0.0005], size=[sx, sy, 0.0005], rgba=[0.2, 0.25, 0.45, 1])
            g.contype = g.conaffinity = 0

    wb.add_camera(name="lab", pos=[-0.55, -0.85, 0.85], xyaxes=[0.84, -0.55, 0, 0.3, 0.46, 0.84])
    wb.add_camera(name="top", pos=[0.45, 0, 1.6], xyaxes=[0, -1, 0, 1, 0, 0])
    return spec.compile()
