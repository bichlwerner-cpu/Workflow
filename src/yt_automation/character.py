"""Parametric 2D brand mascot.

The whole point: a *code-defined* character instead of AI-generated images.
Every pose reuses the exact same part definitions (colors, proportions, line
weight) and only changes joint angles / positions, so the character is 100%
consistent across an arbitrary number of frames -- which is exactly what an
editor needs to string poses together smoothly.

Pipeline:
    Pose + Expression  ->  build_svg()  ->  SVG string
    SVG                ->  rasterize()  ->  transparent PNG

Re-brand by editing the PALETTE constants -- one place, every pose updates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

# --------------------------------------------------------------------------
# Brand palette -- change these to re-skin the whole character.
# --------------------------------------------------------------------------
BODY = "#FFC83D"        # main yellow
BODY_SHADE = "#F2A53A"  # soft bottom shading
BODY_LIGHT = "#FFE08A"  # top highlight
OUTLINE = "#2A2118"     # dark brown outline (softer than pure black)
WHITE = "#FFFFFF"
PUPIL = "#2A2118"
CHEEK = "#FF8C69"       # coral blush
SHOE = "#2A2118"        # dark feet read as little shoes
SHADOW = "#2A2118"      # ground shadow (low opacity)

OUTLINE_W = 7.0
ARM_W = 34.0
LEG_W = 40.0

# --------------------------------------------------------------------------
# Palette presets -- pick the brand identity with use_palette("name").
# Each preset is a full colour set; shades/highlights are tuned per colour.
# --------------------------------------------------------------------------
PALETTES: dict[str, dict[str, str]] = {
    "sunny":  {"BODY": "#FFC83D", "BODY_SHADE": "#F2A53A", "BODY_LIGHT": "#FFE08A",
               "OUTLINE": "#2A2118", "CHEEK": "#FF8C69", "SHOE": "#2A2118"},
    "teal":   {"BODY": "#36C5C0", "BODY_SHADE": "#2AA8A4", "BODY_LIGHT": "#8FE7E3",
               "OUTLINE": "#143534", "CHEEK": "#FF8C69", "SHOE": "#143534"},
    "blue":   {"BODY": "#4D9DE0", "BODY_SHADE": "#3E82BC", "BODY_LIGHT": "#AFD6F4",
               "OUTLINE": "#15273A", "CHEEK": "#FF8C69", "SHOE": "#15273A"},
    "purple": {"BODY": "#9B6DD6", "BODY_SHADE": "#7E55B5", "BODY_LIGHT": "#D0B6F0",
               "OUTLINE": "#291A3E", "CHEEK": "#FF9AA2", "SHOE": "#291A3E"},
    "coral":  {"BODY": "#FF8A5B", "BODY_SHADE": "#E8714A", "BODY_LIGHT": "#FFC2A4",
               "OUTLINE": "#3A1E14", "CHEEK": "#FF5E7A", "SHOE": "#3A1E14"},
}


def use_palette(name: str) -> None:
    """Re-skin the whole character by swapping the active colour set."""
    global BODY, BODY_SHADE, BODY_LIGHT, OUTLINE, PUPIL, CHEEK, SHOE, SHADOW
    p = PALETTES[name]
    BODY, BODY_SHADE, BODY_LIGHT = p["BODY"], p["BODY_SHADE"], p["BODY_LIGHT"]
    OUTLINE = PUPIL = SHADOW = p["OUTLINE"]
    CHEEK, SHOE = p["CHEEK"], p["SHOE"]

# Canvas
CW, CH = 600, 760

# Anchor geometry (front view, character centered)
HX, HY = 300.0, 215.0          # head center
HRX, HRY = 130.0, 122.0        # head radii
BODY_TOP, BODY_BOT = 322.0, 566.0
BODY_HALF_W = 92.0
SHOULDER_L = (224.0, 360.0)    # screen-left shoulder pivot
SHOULDER_R = (376.0, 360.0)
HIP_L = (262.0, 556.0)
HIP_R = (338.0, 556.0)
UPPER_ARM, FORE_ARM = 80.0, 76.0
HAND_R = 28.0
UPPER_LEG, LOWER_LEG = 70.0, 80.0
FOOT_W, FOOT_H = 54.0, 30.0


# --------------------------------------------------------------------------
# Rig data
# --------------------------------------------------------------------------
@dataclass
class Arm:
    shoulder: float = 0.0   # deg, 0 = straight down, sign is per-side outward
    elbow: float = 0.0      # deg relative to upper arm
    hand: str = "mitten"    # mitten | point | thumb | open


@dataclass
class Leg:
    hip: float = 0.0        # deg, 0 = straight down
    knee: float = 0.0       # deg relative to upper leg


@dataclass
class Pose:
    name: str
    arm_l: Arm = field(default_factory=Arm)
    arm_r: Arm = field(default_factory=Arm)
    leg_l: Leg = field(default_factory=Leg)
    leg_r: Leg = field(default_factory=Leg)
    head_tilt: float = 0.0   # deg, + tilts head to screen-right
    bob: float = 0.0         # vertical body offset (px, + = down)
    lean: float = 0.0        # whole-body lean deg


@dataclass
class Expression:
    name: str
    eye: str = "open"        # open | happy | wide | half | wink_l | wink_r | x | closed
    look: tuple[float, float] = (0.0, 0.0)   # pupil offset, each in [-1, 1]
    brow: float = 0.0        # deg, + = angry (inner down), - = surprised/sad (inner up)
    brow_dy: float = 0.0     # raise(-)/lower(+) brows in px
    mouth: str = "smile"     # see _mouth()
    cheeks: bool = True


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _pt(origin: tuple[float, float], angle_deg: float, length: float) -> tuple[float, float]:
    """Point at `length` from origin; angle 0 = down (+y), + = toward +x."""
    a = math.radians(angle_deg)
    return (origin[0] + length * math.sin(a), origin[1] + length * math.cos(a))


def _limb(p0, ang_upper, ang_elbow_rel, len_u, len_f, width):
    """Return (elbow, end, svg) for a 2-segment limb with dark outline + fill."""
    elbow = _pt(p0, ang_upper, len_u)
    end = _pt(elbow, ang_upper + ang_elbow_rel, len_f)
    d = f"M {p0[0]:.1f} {p0[1]:.1f} L {elbow[0]:.1f} {elbow[1]:.1f} L {end[0]:.1f} {end[1]:.1f}"
    outline = (
        f'<path d="{d}" fill="none" stroke="{OUTLINE}" '
        f'stroke-width="{width + OUTLINE_W * 2:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    fill = (
        f'<path d="{d}" fill="none" stroke="{BODY}" '
        f'stroke-width="{width:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return elbow, end, outline, fill


def _hand(center, style, ang):
    """Mitten / pointing / thumb hand at `center`, oriented along `ang` (deg, 0=down)."""
    cx, cy = center
    parts = [
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{HAND_R + OUTLINE_W:.1f}" fill="{OUTLINE}"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{HAND_R:.1f}" fill="{BODY}"/>',
    ]
    if style == "point":
        tip = _pt(center, ang, HAND_R + 26)
        parts.insert(1, f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                        f'stroke="{OUTLINE}" stroke-width="{ARM_W * 0.62 + OUTLINE_W * 2:.1f}" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                     f'stroke="{BODY}" stroke-width="{ARM_W * 0.62:.1f}" stroke-linecap="round"/>')
    elif style == "thumb":
        tip = _pt(center, 180, HAND_R + 24)  # thumb always points up
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                     f'stroke="{OUTLINE}" stroke-width="{ARM_W * 0.55 + OUTLINE_W * 2:.1f}" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                     f'stroke="{BODY}" stroke-width="{ARM_W * 0.55:.1f}" stroke-linecap="round"/>')
    elif style in ("one", "two", "three"):
        n = {"one": 1, "two": 2, "three": 3}[style]
        spread = 19
        base = 180 - (n - 1) / 2 * spread  # fingers fan around straight up
        fw = ARM_W * 0.5
        for k in range(n):
            tip = _pt(center, base + k * spread, HAND_R + 30)
            parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                         f'stroke="{OUTLINE}" stroke-width="{fw + OUTLINE_W * 2:.1f}" stroke-linecap="round"/>')
        for k in range(n):
            tip = _pt(center, base + k * spread, HAND_R + 30)
            parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                         f'stroke="{BODY}" stroke-width="{fw:.1f}" stroke-linecap="round"/>')
    return "".join(parts)


def _foot(end, ang_leg):
    """Little dark shoe at the end of a leg."""
    cx, cy = _pt(end, ang_leg, 6)
    return (
        f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({ang_leg:.1f})">'
        f'<ellipse cx="6" cy="0" rx="{FOOT_W / 2:.1f}" ry="{FOOT_H / 2:.1f}" '
        f'fill="{SHOE}" stroke="{OUTLINE}" stroke-width="2"/></g>'
    )


# --------------------------------------------------------------------------
# Body / head / face
# --------------------------------------------------------------------------
def _body_path() -> str:
    l = HX - BODY_HALF_W
    r = HX + BODY_HALF_W
    top = BODY_TOP
    bot = BODY_BOT
    cr = 78.0
    d = (
        f"M {l:.1f} {top + cr:.1f} "
        f"Q {l:.1f} {top:.1f} {l + cr:.1f} {top:.1f} "
        f"L {r - cr:.1f} {top:.1f} Q {r:.1f} {top:.1f} {r:.1f} {top + cr:.1f} "
        f"L {r:.1f} {bot - cr:.1f} Q {r:.1f} {bot:.1f} {r - cr:.1f} {bot:.1f} "
        f"L {l + cr:.1f} {bot:.1f} Q {l:.1f} {bot:.1f} {l:.1f} {bot - cr:.1f} Z"
    )
    return d


def _eye(cx, cy, kind, look):
    rx, ry = 27.0, 33.0
    dx, dy = look[0] * 11, look[1] * 12
    if kind in ("happy",):
        # ^_^ closed happy eye: upward arc
        return (f'<path d="M {cx - 26:.1f} {cy + 4:.1f} Q {cx:.1f} {cy - 26:.1f} {cx + 26:.1f} {cy + 4:.1f}" '
                f'fill="none" stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
    if kind == "closed":
        return (f'<line x1="{cx - 24:.1f}" y1="{cy:.1f}" x2="{cx + 24:.1f}" y2="{cy:.1f}" '
                f'stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
    if kind == "x":
        return (f'<g stroke="{OUTLINE}" stroke-width="9" stroke-linecap="round">'
                f'<line x1="{cx - 18:.1f}" y1="{cy - 18:.1f}" x2="{cx + 18:.1f}" y2="{cy + 18:.1f}"/>'
                f'<line x1="{cx + 18:.1f}" y1="{cy - 18:.1f}" x2="{cx - 18:.1f}" y2="{cy + 18:.1f}"/></g>')
    if kind == "wide":
        rx, ry = 30.0, 38.0
    sclera = f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{WHITE}" stroke="{OUTLINE}" stroke-width="4"/>'
    pupil = f'<circle cx="{cx + dx:.1f}" cy="{cy + dy:.1f}" r="14.5" fill="{PUPIL}"/>'
    shine = f'<circle cx="{cx + dx - 5:.1f}" cy="{cy + dy - 6:.1f}" r="4.5" fill="{WHITE}"/>'
    g = sclera + pupil + shine
    if kind == "half":
        lid = f'<rect x="{cx - rx - 2:.1f}" y="{cy - ry - 2:.1f}" width="{rx * 2 + 4:.1f}" height="{ry + 4:.1f}" fill="{BODY}"/>'
        lid += f'<line x1="{cx - rx:.1f}" y1="{cy:.1f}" x2="{cx + rx:.1f}" y2="{cy:.1f}" stroke="{OUTLINE}" stroke-width="6" stroke-linecap="round"/>'
        g += lid
    return g


def _brow(cx, cy, side, angle, dy):
    """Eyebrow stroke. side=-1 (screen-left) / +1 (screen-right)."""
    y = cy + dy
    # inner end moves by angle (angry: inner down; surprised/sad: inner up)
    inner_dx = 18 * side
    rot = angle * side
    x1, x2 = cx - 22, cx + 22
    return (f'<g transform="rotate({rot:.1f} {cx:.1f} {y:.1f})">'
            f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'stroke="{OUTLINE}" stroke-width="9" stroke-linecap="round"/></g>')


def _mouth(kind):
    cx, cy = HX, HY + 60
    if kind == "smile":
        return (f'<path d="M {cx - 34:.1f} {cy - 4:.1f} Q {cx:.1f} {cy + 30:.1f} {cx + 34:.1f} {cy - 4:.1f}" '
                f'fill="none" stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
    if kind == "big_smile":
        return (f'<path d="M {cx - 42:.1f} {cy - 6:.1f} Q {cx:.1f} {cy + 46:.1f} {cx + 42:.1f} {cy - 6:.1f} '
                f'Q {cx:.1f} {cy + 16:.1f} {cx - 42:.1f} {cy - 6:.1f} Z" fill="{OUTLINE}"/>')
    if kind == "neutral" or kind == "flat":
        return (f'<line x1="{cx - 26:.1f}" y1="{cy + 6:.1f}" x2="{cx + 26:.1f}" y2="{cy + 6:.1f}" '
                f'stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
    if kind == "frown":
        return (f'<path d="M {cx - 32:.1f} {cy + 18:.1f} Q {cx:.1f} {cy - 14:.1f} {cx + 32:.1f} {cy + 18:.1f}" '
                f'fill="none" stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
    if kind == "o":
        return (f'<ellipse cx="{cx:.1f}" cy="{cy + 6:.1f}" rx="16" ry="20" fill="{OUTLINE}"/>')
    if kind == "surprise":
        return (f'<ellipse cx="{cx:.1f}" cy="{cy + 8:.1f}" rx="22" ry="30" fill="{OUTLINE}"/>')
    # --- visemes for lip-sync ---
    vis = {
        "rest": (24, 7), "mbp": (26, 5), "talk_e": (30, 14),
        "talk_i": (34, 10), "talk_a": (30, 30), "talk_o": (20, 26), "talk_u": (15, 18),
    }
    if kind in vis:
        rx, ry = vis[kind]
        if kind == "mbp":
            return (f'<line x1="{cx - rx:.1f}" y1="{cy + 6:.1f}" x2="{cx + rx:.1f}" y2="{cy + 6:.1f}" '
                    f'stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round"/>')
        inner = ""
        if ry > 16:
            inner = f'<ellipse cx="{cx:.1f}" cy="{cy + 12:.1f}" rx="{rx * 0.5:.1f}" ry="{ry * 0.32:.1f}" fill="{CHEEK}"/>'
        return (f'<ellipse cx="{cx:.1f}" cy="{cy + 6:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{OUTLINE}"/>{inner}')
    return _mouth("smile")


# --------------------------------------------------------------------------
# Assemble
# --------------------------------------------------------------------------
def _glasses(eL, eR, eye_y):
    """Round intellectual glasses over the eyes (psychology / 'smart' brand cue)."""
    r = 38.0
    bridge = (f'<line x1="{eL + r - 4:.1f}" y1="{eye_y:.1f}" x2="{eR - r + 4:.1f}" y2="{eye_y:.1f}" '
              f'stroke="{OUTLINE}" stroke-width="7" stroke-linecap="round"/>')
    temples = (f'<line x1="{eL - r:.1f}" y1="{eye_y - 2:.1f}" x2="{eL - r - 34:.1f}" y2="{eye_y - 10:.1f}" '
               f'stroke="{OUTLINE}" stroke-width="7" stroke-linecap="round"/>'
               f'<line x1="{eR + r:.1f}" y1="{eye_y - 2:.1f}" x2="{eR + r + 34:.1f}" y2="{eye_y - 10:.1f}" '
               f'stroke="{OUTLINE}" stroke-width="7" stroke-linecap="round"/>')
    lenses = ""
    for cx in (eL, eR):
        lenses += (f'<circle cx="{cx:.1f}" cy="{eye_y:.1f}" r="{r:.1f}" fill="{WHITE}" fill-opacity="0.18" '
                   f'stroke="{OUTLINE}" stroke-width="7"/>'
                   f'<path d="M {cx - r + 8:.1f} {eye_y - 14:.1f} Q {cx - 4:.1f} {eye_y - r + 6:.1f} {cx + 14:.1f} {eye_y - r + 12:.1f}" '
                   f'fill="none" stroke="{WHITE}" stroke-width="5" stroke-linecap="round" opacity="0.6"/>')
    return temples + bridge + lenses


ACCESSORIES = ("glasses",)


def build_svg(pose: Pose, expr: Expression, *, bg: str | None = None, scale: float = 1.0,
              accessory: str | None = None) -> str:
    L_arm, R_arm = pose.arm_l, pose.arm_r
    L_leg, R_leg = pose.leg_l, pose.leg_r

    # Limbs (screen-left arm bends left -> negative outward handled via sign of angles in library)
    el_l, hand_l, ol_l, fl_l = _limb(SHOULDER_L, L_arm.shoulder, L_arm.elbow, UPPER_ARM, FORE_ARM, ARM_W)
    el_r, hand_r, ol_r, fl_r = _limb(SHOULDER_R, R_arm.shoulder, R_arm.elbow, UPPER_ARM, FORE_ARM, ARM_W)
    kn_l, foot_l, oleg_l, fleg_l = _limb(HIP_L, L_leg.hip, L_leg.knee, UPPER_LEG, LOWER_LEG, LEG_W)
    kn_r, foot_r, oleg_r, fleg_r = _limb(HIP_R, R_leg.hip, R_leg.knee, UPPER_LEG, LOWER_LEG, LEG_W)

    arm_l_ang = L_arm.shoulder + L_arm.elbow
    arm_r_ang = R_arm.shoulder + R_arm.elbow

    # Layer order: shadow -> legs -> arms(behind) -> body -> head -> face -> hands(front)
    layers = []
    layers.append(f'<ellipse cx="{HX:.1f}" cy="712" rx="150" ry="26" fill="{SHADOW}" opacity="0.16"/>')

    body_g = []  # everything that bobs/leans together
    # legs
    body_g += [oleg_l, oleg_r, fleg_l, fleg_r,
               _foot(foot_l, L_leg.hip + L_leg.knee), _foot(foot_r, R_leg.hip + R_leg.knee)]
    # arms behind body
    body_g += [ol_l, ol_r, fl_l, fl_r]
    # body
    body_g.append(f'<path d="{_body_path()}" fill="{BODY}" stroke="{OUTLINE}" stroke-width="{OUTLINE_W}"/>')
    body_g.append(f'<path d="{_body_path()}" fill="{BODY_SHADE}" opacity="0.0"/>')  # reserved
    # belly highlight
    body_g.append(f'<ellipse cx="{HX - 30:.1f}" cy="400" rx="34" ry="60" fill="{BODY_LIGHT}" opacity="0.35"/>')
    # hands in front of body
    body_g.append(_hand(hand_l, L_arm.hand, arm_l_ang))
    body_g.append(_hand(hand_r, R_arm.hand, arm_r_ang))

    # head group (tilts)
    head = []
    head.append(f'<ellipse cx="{HX:.1f}" cy="{HY:.1f}" rx="{HRX:.1f}" ry="{HRY:.1f}" '
                f'fill="{BODY}" stroke="{OUTLINE}" stroke-width="{OUTLINE_W}"/>')
    head.append(f'<ellipse cx="{HX - 38:.1f}" cy="{HY - 46:.1f}" rx="44" ry="34" fill="{BODY_LIGHT}" opacity="0.45"/>')
    # cheeks
    if expr.cheeks:
        head.append(f'<ellipse cx="{HX - 78:.1f}" cy="{HY + 34:.1f}" rx="20" ry="13" fill="{CHEEK}" opacity="0.55"/>')
        head.append(f'<ellipse cx="{HX + 78:.1f}" cy="{HY + 34:.1f}" rx="20" ry="13" fill="{CHEEK}" opacity="0.55"/>')
    # eyes
    eye_y = HY - 6
    eL, eR = HX - 52, HX + 52
    if expr.eye == "wink_l":
        head.append(_eye(eL, eye_y, "closed", expr.look)); head.append(_eye(eR, eye_y, "open", expr.look))
    elif expr.eye == "wink_r":
        head.append(_eye(eL, eye_y, "open", expr.look)); head.append(_eye(eR, eye_y, "closed", expr.look))
    else:
        head.append(_eye(eL, eye_y, expr.eye, expr.look)); head.append(_eye(eR, eye_y, expr.eye, expr.look))
    # brows
    if expr.eye not in ("happy", "x", "closed"):
        head.append(_brow(eL, eye_y - 44, -1, expr.brow, expr.brow_dy))
        head.append(_brow(eR, eye_y - 44, +1, expr.brow, expr.brow_dy))
    # mouth
    head.append(_mouth(expr.mouth))
    # accessory
    if accessory == "glasses":
        head.append(_glasses(eL, eR, eye_y))

    head_g = (f'<g transform="rotate({pose.head_tilt:.1f} {HX:.1f} {HY + 40:.1f})">' + "".join(head) + "</g>")

    inner = "".join(body_g) + head_g
    # body bob + lean
    inner = (f'<g transform="translate(0 {pose.bob:.1f}) rotate({pose.lean:.1f} {HX:.1f} 480)">'
             + inner + "</g>")
    layers.append(inner)

    bg_rect = f'<rect width="{CW}" height="{CH}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CW * scale:.0f}" height="{CH * scale:.0f}" '
            f'viewBox="0 0 {CW} {CH}">{bg_rect}{"".join(layers)}</svg>')


def rasterize(svg: str, out_path: Path, *, width: int = 600, transparent: bool = True) -> Path:
    import cairosvg
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(out_path),
        output_width=width,
        output_height=int(width * CH / CW),
        background_color="transparent" if transparent else "white",
    )
    return out_path


# --------------------------------------------------------------------------
# Pose & expression library  (named, ready to use)
# --------------------------------------------------------------------------
POSES: dict[str, Pose] = {
    "idle":        Pose("idle", Arm(-14, -6), Arm(14, 6), Leg(-7, 0), Leg(7, 0)),
    "wave":        Pose("wave", Arm(-14, -6), Arm(150, -28, "open"), Leg(-7, 0), Leg(7, 0), head_tilt=4),
    "point_up":    Pose("point_up", Arm(-14, -6), Arm(173, 0, "point"), Leg(-7, 0), Leg(7, 0)),
    "point_right": Pose("point_right", Arm(-14, -6), Arm(96, 0, "point"), Leg(-7, 0), Leg(7, 0)),
    "point_left":  Pose("point_left", Arm(-96, 0, "point"), Arm(14, 6), Leg(-7, 0), Leg(7, 0)),
    "thumbs_up":   Pose("thumbs_up", Arm(-14, -6), Arm(62, -10, "thumb"), Leg(-7, 0), Leg(7, 0)),
    "thinking":    Pose("thinking", Arm(-14, -6), Arm(158, -78, "mitten"), Leg(-7, 0), Leg(7, 0), head_tilt=6),
    "hands_hips":  Pose("hands_hips", Arm(60, 30), Arm(-60, -30), Leg(-7, 0), Leg(7, 0)),
    "shrug":       Pose("shrug", Arm(-72, -40, "open"), Arm(72, 40, "open"), Leg(-7, 0), Leg(7, 0)),
    "celebrate":   Pose("celebrate", Arm(-150, 12, "open"), Arm(150, -12, "open"), Leg(-9, 0), Leg(9, 0), bob=-8),
    "welcome":     Pose("welcome", Arm(-56, -16, "open"), Arm(56, 16, "open"), Leg(-7, 0), Leg(7, 0)),
    "run":         Pose("run", Arm(44, -34), Arm(-30, -10), Leg(-32, 22), Leg(38, -34), lean=8),
    "walk":        Pose("walk", Arm(22, -12), Arm(-18, -8), Leg(-20, 10), Leg(24, -18), lean=3),
    "facepalm":    Pose("facepalm", Arm(-14, -6), Arm(150, -112, "open"), Leg(-7, 0), Leg(7, 0), head_tilt=-4),
    "explain":     Pose("explain", Arm(-44, -30, "open"), Arm(44, 30, "open"), Leg(-7, 0), Leg(7, 0)),
    "hand_on_heart":Pose("hand_on_heart", Arm(60, 120, "mitten"), Arm(14, 6), Leg(-7, 0), Leg(7, 0), head_tilt=3),
    "ponder":      Pose("ponder", Arm(-158, 78, "mitten"), Arm(14, 6), Leg(-7, 0), Leg(7, 0), head_tilt=-6),
    "mind_blown":  Pose("mind_blown", Arm(-132, -30, "open"), Arm(132, 30, "open"), Leg(-8, 0), Leg(8, 0)),
    "count_one":   Pose("count_one", Arm(-14, -6), Arm(20, -124, "one"), Leg(-7, 0), Leg(7, 0)),
    "count_two":   Pose("count_two", Arm(-14, -6), Arm(20, -124, "two"), Leg(-7, 0), Leg(7, 0)),
    "count_three": Pose("count_three", Arm(-14, -6), Arm(20, -124, "three"), Leg(-7, 0), Leg(7, 0)),
}

EXPRESSIONS: dict[str, Expression] = {
    "neutral":   Expression("neutral", "open", (0, 0), 0, 0, "smile"),
    "happy":     Expression("happy", "happy", (0, 0), 0, 0, "big_smile"),
    "talk":      Expression("talk", "open", (0, 0), 0, 0, "talk_a"),
    "surprised": Expression("surprised", "wide", (0, 0), -18, -4, "surprise"),
    "sad":       Expression("sad", "half", (0, 0.4), -14, 2, "frown", cheeks=False),
    "angry":     Expression("angry", "open", (0, 0), 20, 4, "frown", cheeks=False),
    "thinking":  Expression("thinking", "open", (0.5, -0.5), 6, -2, "flat"),
    "wink":      Expression("wink", "wink_r", (0, 0), 0, 0, "smile"),
    "cool":      Expression("cool", "half", (0, 0), 0, 0, "smile"),
    "dead":      Expression("dead", "x", (0, 0), 0, 0, "neutral", cheeks=False),
    "curious":   Expression("curious", "wide", (0, 0), -10, -2, "smile"),
    "empathetic":Expression("empathetic", "open", (0, 0.15), -8, 0, "smile"),
    "aha":       Expression("aha", "wide", (0, 0), -14, -3, "big_smile"),
    "confused":  Expression("confused", "open", (0.4, -0.1), 6, 0, "o"),
}

# Mouth shapes for lip-sync. Map these onto a neutral-eyed face per frame.
VISEMES: list[str] = ["rest", "mbp", "talk_a", "talk_e", "talk_i", "talk_o", "talk_u"]


def viseme_expression(viseme: str, base: Expression | None = None) -> Expression:
    """An expression that keeps the eyes of `base` but swaps the mouth to a viseme."""
    base = base or EXPRESSIONS["neutral"]
    return replace(base, name=f"{base.name}+{viseme}", mouth=viseme)


def contact_sheet(out_path: Path, *, cols: int = 4, cell_w: int = 300,
                  pad: int = 16, label: bool = True, accessory: str | None = None) -> Path:
    """Render every pose (fitting face) + every expression (idle body) into one PNG grid."""
    from PIL import Image, ImageDraw, ImageFont

    items: list[tuple[str, str]] = []  # (svg, caption)
    for name, pose in POSES.items():
        expr = EXPRESSIONS[_POSE_FACE.get(name, "neutral")]
        items.append((build_svg(pose, expr, accessory=accessory), f"pose: {name}"))
    for name, expr in EXPRESSIONS.items():
        items.append((build_svg(POSES["idle"], expr, accessory=accessory), f"face: {name}"))

    cell_h = int(cell_w * CH / CW)
    cap_h = 30 if label else 0
    rows = (len(items) + cols - 1) // cols
    W = cols * cell_w + (cols + 1) * pad
    H = rows * (cell_h + cap_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (244, 241, 234))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for i, (svg, cap) in enumerate(items):
            r, c = divmod(i, cols)
            x = pad + c * (cell_w + pad)
            y = pad + r * (cell_h + cap_h + pad)
            cell_png = Path(tmp) / f"cell_{i}.png"
            rasterize(svg, cell_png, width=cell_w, transparent=True)
            cell = Image.open(cell_png).convert("RGBA")
            sheet.paste(cell, (x, y), cell)
            if label:
                draw.text((x + 6, y + cell_h + 4), cap, fill=(42, 33, 24), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path


# Sensible default face per pose (so the exported pose "reads" right).
_POSE_FACE = {
    "wave": "happy", "celebrate": "happy", "thumbs_up": "happy",
    "welcome": "happy", "facepalm": "sad", "thinking": "thinking",
    "walk": "happy", "explain": "neutral", "hand_on_heart": "empathetic",
    "ponder": "thinking", "mind_blown": "surprised", "count_one": "neutral",
    "count_two": "neutral", "count_three": "neutral",
}


def export_library(out_dir: Path, *, width: int = 1200, full: bool = False,
                   svg_too: bool = True, accessory: str | None = None) -> list[Path]:
    """Write the full transparent-PNG image library an editor can composite.

    Layout:
        poses/<pose>.png         every pose with a fitting face
        expressions/<expr>.png   idle body, every expression
        visemes/<viseme>.png     idle body, neutral eyes, lip-sync mouth shapes
        full/<pose>__<expr>.png  (only with full=True) the whole matrix
        svg/<...>.svg            editable vector source (if svg_too)
    """
    written: list[Path] = []

    def emit(svg: str, rel: str) -> None:
        png = out_dir / f"{rel}.png"
        rasterize(svg, png, width=width, transparent=True)
        written.append(png)
        if svg_too:
            svg_path = out_dir / "svg" / f"{rel}.svg"
            svg_path.parent.mkdir(parents=True, exist_ok=True)
            svg_path.write_text(svg, encoding="utf-8")

    for name, pose in POSES.items():
        expr = EXPRESSIONS[_POSE_FACE.get(name, "neutral")]
        emit(build_svg(pose, expr, accessory=accessory), f"poses/{name}")

    for name, expr in EXPRESSIONS.items():
        emit(build_svg(POSES["idle"], expr, accessory=accessory), f"expressions/{name}")

    for viseme in VISEMES:
        emit(build_svg(POSES["idle"], viseme_expression(viseme), accessory=accessory), f"visemes/{viseme}")

    if full:
        for pname, pose in POSES.items():
            for ename, expr in EXPRESSIONS.items():
                emit(build_svg(pose, expr, accessory=accessory), f"full/{pname}__{ename}")

    return written
