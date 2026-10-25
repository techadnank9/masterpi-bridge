"""Hiwonder MasterPi arm IK, ported from ArmIK/InverseKinematics.py + ArmMoveIK.py.

Coordinates are Hiwonder's arm frame in cm: +y forward, +x right, +z up, origin at the IK base.
Pitch alpha is the gripper angle in degrees: 0 horizontal, -90 pointing straight down.
"""
from math import acos, atan2, degrees, radians, cos, sin, sqrt

L1, L2, L3, L4 = 8.00 + 1.30, 6.50, 6.20, 10.00  # cm, l1 includes ArmMoveIK's +1.3
K = 2000.0 / 180.0  # us per degree


def angles(x, y, z, alpha):
    """Returns (theta3, theta4, theta5, theta6) in degrees, or None if unreachable."""
    theta6 = degrees(atan2(y, x))
    p = sqrt(x * x + y * y)
    cd, pd = L4 * cos(radians(alpha)), L4 * sin(radians(alpha))
    af, cf = p - cd, z - L1 - pd
    ac = sqrt(af * af + cf * cf)
    if ac == 0 or L2 + L3 < round(ac, 4):
        return None
    cos_abc = round((L2 ** 2 + L3 ** 2 - ac ** 2) / (2 * L2 * L3), 4)
    cos_bac = round((ac ** 2 + L2 ** 2 - L3 ** 2) / (2 * L2 * ac), 4)
    if abs(cos_abc) > 1 or abs(cos_bac) > 1:
        return None
    theta4 = 180.0 - degrees(acos(cos_abc))
    theta5 = degrees(acos(af / ac) * (-1 if cf < 0 else 1) + acos(cos_bac))
    theta3 = alpha - theta5 + theta4
    return theta3, theta4, theta5, theta6


def pulses_for(theta3, theta4, theta5, theta6):
    """ArmMoveIK.transformAngelAdaptArm, without Deviation.yaml (the robot adds that itself)."""
    return {3: round(theta3 * K + 1500), 4: round(theta4 * K + 1500),
            5: round(1500 + (90 - theta5) * K), 6: round(theta6 * K) + 500}


def _valid(p):
    return all(500 <= v <= 2500 for v in p.values())


def solve(x, y, z, alpha=0.0, alpha_lo=-90.0, alpha_hi=90.0):
    """Like ArmIK.setPitchRangeMoving: try alpha, else the closest reachable pitch in range.

    Returns (pulses, used_alpha) or None.
    """
    best = None
    a = float(alpha)
    for step in range(0, 181):
        for cand in ((a - step, a + step) if step else (a,)):
            if not alpha_lo <= cand <= alpha_hi:
                continue
            ang = angles(x, y, z, cand)
            if ang is None:
                continue
            p = pulses_for(*ang)
            if _valid(p):
                best = (p, cand)
                break
        if best:
            return best
    return None
