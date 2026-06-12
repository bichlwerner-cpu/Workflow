"""Deterministic procedural stickman renderer.

The character is a parametric skeleton drawn with Pillow — no AI image
generation involved, so the character is pixel-perfectly consistent in every
frame of every video, while remaining fully posable and animatable.

Conventions:
  - Poses are authored for a character FACING RIGHT; facing=-1 mirrors.
  - Limb angles are degrees from "straight down"; positive rotates toward
    the facing direction. Torso angle is from "straight up", positive leans
    toward the facing direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Tuple

from PIL import ImageDraw

from .utils import RGB, mix

Vec = Tuple[float, float]


@dataclass
class Pose:
    torso: float = 0.0
    head_tilt: float = 0.0
    front_arm: Tuple[float, float] = (10.0, 8.0)    # (shoulder, elbow-bend)
    back_arm: Tuple[float, float] = (-10.0, -8.0)
    front_leg: Tuple[float, float] = (8.0, 3.0)     # (hip, knee-bend)
    back_leg: Tuple[float, float] = (-8.0, -3.0)
    y_offset: float = 0.0                           # fraction of scale, + = lifted


POSE_LIBRARY = {
    "idle":         Pose(),
    "talking":      Pose(front_arm=(38, 55)),
    "explaining":   Pose(torso=2, front_arm=(75, 25), back_arm=(-18, -12)),
    "pointing":     Pose(front_arm=(92, 2), back_arm=(-14, -6)),
    "pointing_up":  Pose(front_arm=(155, 15), head_tilt=-4),
    "thinking":     Pose(head_tilt=7, front_arm=(35, 125), back_arm=(-8, -4)),
    "shocked":      Pose(torso=-6, head_tilt=-4, front_arm=(115, 35),
                         back_arm=(-115, -35), front_leg=(14, 2), back_leg=(-14, -2)),
    "happy":        Pose(front_arm=(132, 18), back_arm=(-132, -18), head_tilt=-2),
    "sad":          Pose(torso=7, head_tilt=16, front_arm=(4, 2), back_arm=(-4, -2)),
    "facepalm":     Pose(torso=4, head_tilt=12, front_arm=(55, 118), back_arm=(-6, -4)),
    "shrug":        Pose(head_tilt=5, front_arm=(45, 115), back_arm=(-45, -115)),
    "arms_crossed": Pose(front_arm=(50, 100), back_arm=(-45, -105)),
    "presenting":   Pose(torso=2, front_arm=(70, 35), back_arm=(-25, -18)),
    "walking":      Pose(),
    "mind_blown":   Pose(torso=-8, head_tilt=-5, front_arm=(135, 55), back_arm=(-135, -55)),
    "celebrating":  Pose(front_arm=(128, 15), back_arm=(-128, -15)),
}

# Crumpled-on-the-floor target used by the "collapse" action.
COLLAPSED = Pose(torso=58, head_tilt=28, front_arm=(35, 20), back_arm=(-30, -15),
                 front_leg=(60, 75), back_leg=(-55, -70), y_offset=-0.10)


def lerp_pose(a: Pose, b: Pose, u: float) -> Pose:
    u = max(0.0, min(1.0, u))

    def l(x: float, y: float) -> float:
        return x + (y - x) * u

    return Pose(
        torso=l(a.torso, b.torso),
        head_tilt=l(a.head_tilt, b.head_tilt),
        front_arm=(l(a.front_arm[0], b.front_arm[0]), l(a.front_arm[1], b.front_arm[1])),
        back_arm=(l(a.back_arm[0], b.back_arm[0]), l(a.back_arm[1], b.back_arm[1])),
        front_leg=(l(a.front_leg[0], b.front_leg[0]), l(a.front_leg[1], b.front_leg[1])),
        back_leg=(l(a.back_leg[0], b.back_leg[0]), l(a.back_leg[1], b.back_leg[1])),
        y_offset=l(a.y_offset, b.y_offset),
    )


# Proportions relative to character scale S (total height ~= S).
HEAD_R = 0.110
TORSO = 0.340
UPPER_ARM = 0.180
FOREARM = 0.160
THIGH = 0.210
SHIN = 0.210


def animate_pose(name: str, t: float, phase: float, speaking: bool) -> Pose:
    """Layer organic motion (sway, talk gestures, walk/jump cycles) on a base pose."""
    base = POSE_LIBRARY.get(name, POSE_LIBRARY["idle"])
    p = replace(base)
    p.head_tilt += 1.8 * math.sin(t * 1.1 + phase)
    p.torso += 0.7 * math.sin(t * 0.9 + phase * 1.3)

    if speaking:
        g = math.sin(2 * math.pi * 2.3 * t + phase)
        fu, ff = p.front_arm
        p.front_arm = (fu + 4 * g, ff + 14 * g)
        p.head_tilt += 2.2 * math.sin(2 * math.pi * 1.6 * t + phase * 2)

    if name == "walking":
        s = math.sin(2 * math.pi * 1.5 * t + phase)
        p.front_leg = (25 * s, 10 + 10 * max(0.0, -s))
        p.back_leg = (-25 * s, -10 - 10 * max(0.0, s))
        p.front_arm = (-22 * s + 8, 12)
        p.back_arm = (22 * s - 8, -12)
        p.y_offset += 0.015 * abs(math.cos(2 * math.pi * 1.5 * t + phase))
    elif name == "celebrating":
        bounce = max(0.0, math.sin(2 * math.pi * 1.4 * t + phase))
        p.y_offset += 0.06 * bounce
        fu, ff = p.front_arm
        p.front_arm = (fu, ff + 18 * math.sin(2 * math.pi * 2.8 * t + phase))
        bu, bf = p.back_arm
        p.back_arm = (bu, bf - 18 * math.sin(2 * math.pi * 2.8 * t + phase))
    return p


def is_blinking(t: float, phase: float) -> bool:
    cycle = t * 0.31 + phase * 0.17
    return (cycle - math.floor(cycle)) < 0.045


def _polar(origin: Vec, angle_deg: float, length: float, facing: int) -> Vec:
    a = math.radians(angle_deg)
    return (origin[0] + math.sin(a) * length * facing, origin[1] + math.cos(a) * length)


def _line(draw: ImageDraw.ImageDraw, a: Vec, b: Vec, color: RGB, width: int) -> None:
    draw.line([a, b], fill=color, width=width)
    r = width / 2
    for p in (a, b):
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def _limb(draw, origin: Vec, seg1: float, seg2: float, angles: Tuple[float, float],
          color: RGB, width: int, facing: int) -> Vec:
    mid = _polar(origin, angles[0], seg1, facing)
    end = _polar(mid, angles[0] + angles[1], seg2, facing)
    _line(draw, origin, mid, color, width)
    _line(draw, mid, end, color, width)
    return end


HEAD_FILL: RGB = (252, 250, 244)
FACE_INK: RGB = (30, 30, 36)


def draw_character(
    draw: ImageDraw.ImageDraw,
    ground: Vec,
    scale: float,
    color: RGB,
    bg_fill: RGB,
    pose: Pose,
    emotion: str = "neutral",
    mouth_open: bool = False,
    blink: bool = False,
    facing: int = 1,
    accessory: str = "none",
    hair: str = "none",
    accent: RGB = (255, 214, 10),
    shadow: bool = True,
) -> None:
    """Draw one stickman anchored at `ground` (feet position when standing)."""
    S = scale
    width = max(3, int(S * 0.032))
    head_r = HEAD_R * S

    leg_len = (THIGH + SHIN) * S * 0.96
    pelvis = (ground[0], ground[1] - leg_len - pose.y_offset * S)

    # Ground contact shadow (squashes slightly when the character jumps).
    if shadow:
        sw = S * (0.30 - 0.10 * min(1.0, pose.y_offset * 6))
        sh = S * 0.035
        draw.ellipse([ground[0] - sw, ground[1] - sh, ground[0] + sw, ground[1] + sh],
                     fill=mix(bg_fill, (0, 0, 0), 0.18))

    # Torso (angle from straight up).
    ta = math.radians(pose.torso)
    neck = (pelvis[0] + math.sin(ta) * TORSO * S * facing, pelvis[1] - math.cos(ta) * TORSO * S)
    shoulder = (pelvis[0] + math.sin(ta) * TORSO * S * 0.92 * facing,
                pelvis[1] - math.cos(ta) * TORSO * S * 0.92)

    hand_r = width * 0.85
    foot_len = S * 0.075

    # Back limbs first (slightly darkened for depth), then torso, front limbs.
    back_color = mix(color, bg_fill, 0.25)
    end = _limb(draw, pelvis, THIGH * S, SHIN * S, pose.back_leg, back_color, width, facing)
    _foot(draw, end, foot_len, back_color, width, facing)
    end = _limb(draw, shoulder, UPPER_ARM * S, FOREARM * S, pose.back_arm, back_color, width, facing)
    _hand(draw, end, hand_r, back_color)
    _line(draw, pelvis, neck, color, width)
    end = _limb(draw, pelvis, THIGH * S, SHIN * S, pose.front_leg, color, width, facing)
    _foot(draw, end, foot_len, color, width, facing)
    end = _limb(draw, shoulder, UPPER_ARM * S, FOREARM * S, pose.front_arm, color, width, facing)
    _hand(draw, end, hand_r, color)

    # Head: warm fill with the body color as outline; face ink stays dark so
    # expressions read identically on every background.
    ha = math.radians(pose.torso + pose.head_tilt)
    hc = (neck[0] + math.sin(ha) * head_r * 1.18 * facing, neck[1] - math.cos(ha) * head_r * 1.18)
    draw.ellipse([hc[0] - head_r, hc[1] - head_r, hc[0] + head_r, hc[1] + head_r],
                 fill=HEAD_FILL, outline=color, width=width)

    _draw_hair(draw, hair, hc, head_r, color, width, facing)
    _draw_face(draw, hc, head_r, FACE_INK, emotion, mouth_open, blink, facing, width, HEAD_FILL)
    _draw_accessory(draw, accessory, hc, head_r, neck, color, accent, width, facing)


def _hand(draw, p: Vec, r: float, color: RGB) -> None:
    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def _foot(draw, p: Vec, length: float, color: RGB, width: int, facing: int) -> None:
    _line(draw, p, (p[0] + length * facing, p[1]), color, width)


def _draw_hair(draw, hair: str, hc: Vec, r: float, color: RGB, width: int, facing: int) -> None:
    fw = max(2, int(width * 0.8))
    if hair == "spiky":
        for k in range(5):
            ang = math.radians(-95 + 36 * k - 72)  # fan over the top
            base = (hc[0] + math.cos(ang) * r * 0.92, hc[1] + math.sin(ang) * r * 0.92)
            tip = (hc[0] + math.cos(ang - 0.12) * r * 1.32, hc[1] + math.sin(ang - 0.12) * r * 1.32)
            _line(draw, base, tip, color, fw)
    elif hair == "bob":
        draw.arc([hc[0] - r * 1.12, hc[1] - r * 1.12, hc[0] + r * 1.12, hc[1] + r * 0.95],
                 start=150, end=390, fill=color, width=int(r * 0.22))
    elif hair == "curly":
        for k in range(4):
            ang = math.radians(-150 + 40 * k)
            cx = hc[0] + math.cos(ang) * r * 0.95
            cy = hc[1] + math.sin(ang) * r * 0.95
            cr = r * 0.26
            draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)


# --------------------------------------------------------------------------- face

_BROWS = {
    # (inner_dy, outer_dy) per eye relative to brow base height (+ = lower)
    "neutral":  (0.0, 0.0),
    "happy":    (-0.06, -0.06),
    "sad":      (-0.10, 0.06),
    "shocked":  (-0.16, -0.16),
    "angry":    (0.12, -0.08),
    "thinking": (-0.12, -0.02),
    "confused": (-0.12, 0.04),
    "smug":     (0.04, -0.02),
    "curious":  (-0.12, -0.04),
    "excited":  (-0.14, -0.14),
}


def _draw_face(draw, hc: Vec, r: float, color: RGB, emotion: str,
               mouth_open: bool, blink: bool, facing: int, width: int,
               bg_fill: RGB) -> None:
    fw = max(2, int(width * 0.6))
    shift = 0.12 * r * facing
    eye_y = hc[1] - 0.18 * r
    eye_dx = 0.27 * r
    eye_r = 0.085 * r
    if emotion in ("shocked", "excited"):
        eye_r = 0.115 * r
    elif emotion == "smug":
        eye_r = 0.07 * r

    for side in (-1, 1):
        ex = hc[0] + shift + side * eye_dx
        if blink:
            _line(draw, (ex - eye_r, eye_y), (ex + eye_r, eye_y), color, fw)
        else:
            draw.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r], fill=color)
            if emotion == "smug":  # lowered lid
                draw.rectangle([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y - eye_r * 0.2], fill=bg_fill)

        inner_dy, outer_dy = _BROWS.get(emotion, (0.0, 0.0))
        if emotion in ("thinking", "confused") and side == -1:
            inner_dy, outer_dy = 0.02, 0.02  # asymmetric brows
        brow_y = eye_y - 0.22 * r
        bx_in = ex - side * eye_r * 1.1
        bx_out = ex + side * eye_r * 1.1
        _line(draw,
              (bx_in, brow_y + inner_dy * r),
              (bx_out, brow_y + outer_dy * r),
              color, fw)

    mc = (hc[0] + shift, hc[1] + 0.34 * r)
    mw = 0.46 * r
    if mouth_open:
        mh = 0.30 * r if emotion in ("shocked", "excited", "mind_blown") else 0.22 * r
        draw.ellipse([mc[0] - mw * 0.55, mc[1] - mh / 2, mc[0] + mw * 0.55, mc[1] + mh / 2], fill=color)
    else:
        if emotion in ("happy", "excited", "curious"):
            draw.arc([mc[0] - mw, mc[1] - mw * 0.9, mc[0] + mw, mc[1] + mw * 0.5],
                     start=25, end=155, fill=color, width=fw)
        elif emotion in ("sad", "angry"):
            draw.arc([mc[0] - mw * 0.8, mc[1], mc[0] + mw * 0.8, mc[1] + mw * 1.1],
                     start=205, end=335, fill=color, width=fw)
        elif emotion == "shocked":
            o = mw * 0.34
            draw.ellipse([mc[0] - o, mc[1] - o, mc[0] + o, mc[1] + o], outline=color, width=fw)
        elif emotion == "confused":
            pts = [(mc[0] - mw * 0.7, mc[1]), (mc[0] - mw * 0.25, mc[1] - mw * 0.22),
                   (mc[0] + mw * 0.25, mc[1] + mw * 0.22), (mc[0] + mw * 0.7, mc[1])]
            draw.line(pts, fill=color, width=fw, joint="curve")
        elif emotion == "smug":
            draw.arc([mc[0] - mw * 0.9, mc[1] - mw * 0.7, mc[0] + mw * 0.5, mc[1] + mw * 0.3],
                     start=35, end=120, fill=color, width=fw)
        else:  # neutral / thinking
            _line(draw, (mc[0] - mw * 0.5, mc[1]), (mc[0] + mw * 0.5, mc[1]), color, fw)


# --------------------------------------------------------------------- accessories

def _draw_accessory(draw, accessory: str, hc: Vec, r: float, neck: Vec,
                    color: RGB, accent: RGB, width: int, facing: int) -> None:
    fw = max(2, int(width * 0.6))
    shift = 0.12 * r * facing
    if accessory == "glasses":
        eye_y = hc[1] - 0.18 * r
        eye_dx = 0.27 * r
        gr = 0.20 * r
        for side in (-1, 1):
            ex = hc[0] + shift + side * eye_dx
            draw.ellipse([ex - gr, eye_y - gr, ex + gr, eye_y + gr], outline=color, width=fw)
        _line(draw, (hc[0] + shift - eye_dx + gr, eye_y), (hc[0] + shift + eye_dx - gr, eye_y), color, fw)
    elif accessory == "hat":
        top = hc[1] - r
        draw.rectangle([hc[0] - r * 0.55, top - r * 0.75, hc[0] + r * 0.55, top + r * 0.08], fill=color)
        _line(draw, (hc[0] - r * 0.95, top + r * 0.06), (hc[0] + r * 0.95, top + r * 0.06), color, width)
    elif accessory == "bowtie":
        s = r * 0.34
        for side in (-1, 1):
            draw.polygon([(neck[0], neck[1]), (neck[0] + side * s, neck[1] - s * 0.55),
                          (neck[0] + side * s, neck[1] + s * 0.55)], fill=accent)
    elif accessory == "mustache":
        my = hc[1] + 0.18 * r
        mx = hc[0] + shift
        for side in (-1, 1):
            draw.arc([mx + (side * 0.05 - 0.35 if side < 0 else -0.05) * r, my - 0.10 * r,
                      mx + (0.05 if side < 0 else side * 0.05 + 0.35) * r, my + 0.16 * r],
                     start=180 if side < 0 else 270, end=270 if side < 0 else 360,
                     fill=color, width=fw)
