"""Konsistenter Stick-Man-Charakter für die Faceless-Brand.

Der Charakter wird einmal in einer JSON-Datei definiert (Farben, Proportionen,
Accessoire) und daraus deterministisch gerendert -- dadurch sieht er in jedem
Bild und jedem Video identisch aus.

Outputs:
  - render_pose_image:        einzelne Pose als PNG (optional transparent)
  - render_pose_sheet:        Übersichtsgitter aller Posen
  - render_thumbnail:         gebrandetes Thumbnail mit Titel + Charakter
  - render_background_video:  animierter Hintergrund-Clip für die Pipeline
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import textwrap
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from PIL import Image, ImageDraw

from .fonts import bold_font as _font

ACCESSORIES = ("none", "cap", "beanie", "headphones", "antenna")

Point = tuple[float, float]


# ============================================================
# Charakter-Definition (die "DNA" der Brand)
# ============================================================


@dataclass(frozen=True)
class CharacterSpec:
    name: str = "Stixx"
    line_color: str = "#F2F2F2"
    accent_color: str = "#FF7A59"
    bg_color: str = "#0F1115"
    line_width: float = 0.05    # Strichstärke relativ zur Charakterhöhe
    head_ratio: float = 0.16    # Kopfdurchmesser relativ zur Charakterhöhe
    accessory: str = "cap"
    eyes: bool = True
    outline_color: str = "#101218"  # Kontur, macht die Figur auf hellen
    outline_width: float = 0.014    # Hintergründen sichtbar; 0 = aus

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "CharacterSpec":
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        spec = cls(**{k: v for k, v in data.items() if k in known})
        if spec.accessory not in ACCESSORIES:
            raise ValueError(
                f"accessory muss eins von {ACCESSORIES} sein, "
                f"nicht '{spec.accessory}'"
            )
        return spec

    @classmethod
    def load_or_create(cls, path: Path) -> "CharacterSpec":
        if path.exists():
            return cls.load(path)
        spec = cls()
        spec.save(path)
        return spec


def _hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _blend(a: str, b: str, t: float) -> tuple[int, int, int]:
    ra, ga, ba = _hex_rgb(a)
    rb, gb, bb = _hex_rgb(b)
    return (
        round(ra + (rb - ra) * t),
        round(ga + (gb - ga) * t),
        round(ba + (bb - ba) * t),
    )


# ============================================================
# Posen-Skelett
# ============================================================
#
# Winkel in Grad. 0 = senkrecht nach unten, positiv = nach vorne
# (der Charakter schaut nach rechts). Ellbogen/Knie sind relativ
# zum Oberarm/Oberschenkel.


# Gesichtsausdrücke: steuern Mund, Augenbrauen und Augenform
EXPRESSIONS = (
    "neutral", "smile", "grin", "flat", "sad", "angry", "shocked", "sleepy",
)


@dataclass(frozen=True)
class Pose:
    torso: float = 0.0       # Lehnen des Oberkörpers, + = vor
    head: float = 0.0        # Kopfneigung relativ zum Torso
    l_shoulder: float = 10.0   # hinterer (gedimmter) Arm
    l_elbow: float = 8.0
    r_shoulder: float = -10.0  # vorderer Arm
    r_elbow: float = -8.0
    l_hip: float = 6.0
    l_knee: float = -4.0
    r_hip: float = -6.0
    r_knee: float = 4.0
    lift: float = 0.0        # vertikaler Versatz (Sprung), relativ zur Höhe
    rot: float = 0.0         # Rotation der ganzen Figur (z.B. liegend)
    expression: str = "neutral"


def walk_pose(phase: float) -> Pose:
    """Parametrischer Laufzyklus; `phase` in Zyklen (1.0 = ein Schritt-Paar)."""
    s = math.sin(2 * math.pi * phase)
    bob = abs(math.sin(2 * math.pi * phase))
    return Pose(
        torso=7,
        head=-2,
        l_hip=30 * s,
        l_knee=-32 * max(0.0, -s),
        r_hip=-30 * s,
        r_knee=-32 * max(0.0, s),
        l_shoulder=-24 * s + 6,
        l_elbow=18,
        r_shoulder=24 * s - 6,
        r_elbow=-18,
        lift=0.012 * bob,
    )


POSES: dict[str, Pose] = {
    # Neutral / Gestik
    "idle": Pose(),
    "wave": Pose(torso=2, head=-3, r_shoulder=150, r_elbow=35, expression="smile"),
    "point": Pose(
        torso=5, r_shoulder=95, r_elbow=-5, l_shoulder=18, l_elbow=12,
        expression="smile",
    ),
    "point_up": Pose(torso=2, head=-8, r_shoulder=165, r_elbow=5, expression="smile"),
    "point_down": Pose(torso=8, head=14, r_shoulder=35, r_elbow=-12),
    "present": Pose(torso=3, r_shoulder=60, r_elbow=35, l_shoulder=14, expression="smile"),
    "explain": Pose(
        torso=2, l_shoulder=45, l_elbow=42, r_shoulder=52, r_elbow=38,
    ),
    "think": Pose(
        torso=-2, head=9, r_shoulder=55, r_elbow=125, l_shoulder=12,
        expression="flat",
    ),
    "shrug": Pose(
        torso=-2, head=6,
        l_shoulder=42, l_elbow=95, r_shoulder=-42, r_elbow=-95,
        expression="flat",
    ),
    # Emotionen
    "happy": Pose(
        torso=-6, head=-8, lift=0.01,
        l_shoulder=-28, l_elbow=-15, r_shoulder=-34, r_elbow=-20,
        expression="grin",
    ),
    "celebrate": Pose(
        torso=-3, head=-6, lift=0.025,
        l_shoulder=160, l_elbow=15, r_shoulder=205, r_elbow=-15,
        l_hip=12, l_knee=-8, r_hip=-12, r_knee=8,
        expression="grin",
    ),
    "sad": Pose(
        torso=14, head=30,
        l_shoulder=-4, l_elbow=-4, r_shoulder=-6, r_elbow=-4,
        l_knee=-7, r_knee=7,
        expression="sad",
    ),
    "angry": Pose(
        torso=10, head=-4,
        l_shoulder=55, l_elbow=125, r_shoulder=70, r_elbow=120,
        expression="angry",
    ),
    "shocked": Pose(
        torso=-10, head=-10,
        l_shoulder=150, l_elbow=25, r_shoulder=215, r_elbow=-25,
        l_hip=14, l_knee=-6, r_hip=-14, r_knee=6,
        expression="shocked",
    ),
    "facepalm": Pose(
        torso=6, head=14, r_shoulder=70, r_elbow=132, expression="flat",
    ),
    "dab": Pose(
        torso=8, head=22,
        l_shoulder=215, l_elbow=0, r_shoulder=150, r_elbow=-115,
        expression="grin",
    ),
    # Bewegung
    "walk1": walk_pose(0.15),
    "walk2": walk_pose(0.65),
    "run": Pose(
        torso=14, head=-4, lift=0.02,
        l_shoulder=-35, l_elbow=-60, r_shoulder=40, r_elbow=-70,
        l_hip=42, l_knee=-15, r_hip=-35, r_knee=-70,
    ),
    "jump": Pose(
        torso=-4, head=-8, lift=0.06,
        l_shoulder=140, l_elbow=20, r_shoulder=215, r_elbow=-20,
        l_hip=45, l_knee=-90, r_hip=35, r_knee=-95,
        expression="grin",
    ),
    "sit": Pose(
        torso=-2,
        l_shoulder=30, l_elbow=28, r_shoulder=35, r_elbow=30,
        l_hip=80, l_knee=-85, r_hip=85, r_knee=-88,
    ),
    "lie": Pose(
        rot=90, head=-4,
        l_shoulder=12, l_elbow=10, r_shoulder=-14, r_elbow=-10,
        l_hip=10, l_knee=-8, r_hip=-8, r_knee=6,
        expression="sleepy",
    ),
}


def _lerp_pose(a: Pose, b: Pose, t: float) -> Pose:
    vals = {}
    for f in fields(Pose):
        va, vb = getattr(a, f.name), getattr(b, f.name)
        if isinstance(va, (int, float)):
            vals[f.name] = va + (vb - va) * t
        else:
            vals[f.name] = vb if t >= 0.5 else va
    return Pose(**vals)


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _polar(origin: Point, angle_deg: float, length: float) -> Point:
    a = math.radians(angle_deg)
    return (origin[0] + length * math.sin(a), origin[1] + length * math.cos(a))


# ============================================================
# Charakter zeichnen
# ============================================================


def _tapered(
    draw: ImageDraw.ImageDraw,
    p1: Point,
    p2: Point,
    w1: float,
    w2: float,
    col: tuple[int, int, int],
) -> None:
    """Linie mit verschiedener Dicke an Anfang/Ende und runden Kappen."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    dist = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / dist, dx / dist
    draw.polygon(
        [
            (p1[0] + nx * w1 / 2, p1[1] + ny * w1 / 2),
            (p2[0] + nx * w2 / 2, p2[1] + ny * w2 / 2),
            (p2[0] - nx * w2 / 2, p2[1] - ny * w2 / 2),
            (p1[0] - nx * w1 / 2, p1[1] - ny * w1 / 2),
        ],
        fill=col,
    )
    for p, w in ((p1, w1), (p2, w2)):
        r = w / 2
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=col)


def draw_character(
    draw: ImageDraw.ImageDraw,
    spec: CharacterSpec,
    pose: Pose,
    *,
    foot: Point,
    height: float,
    on_color: tuple[int, int, int] | None = None,
) -> None:
    """Zeichnet den Charakter; `foot` ist der Bodenkontaktpunkt (Mitte)."""
    h = height
    head_r = spec.head_ratio * h / 2
    lw = max(2.0, spec.line_width * h)
    color = on_color or _hex_rgb(spec.line_color)
    dim = _blend(spec.line_color, spec.bg_color, 0.4)
    accent = _hex_rgb(spec.accent_color)

    pelvis = (foot[0], foot[1] - 0.48 * h - pose.lift * h)
    neck = _polar(pelvis, 180 - pose.torso, 0.30 * h)
    shoulder = _polar(pelvis, 180 - pose.torso, 0.28 * h)
    head_c = _polar(neck, 180 - pose.torso - pose.head, 0.04 * h + head_r)

    def paint(inflate: float, mono: tuple[int, int, int] | None) -> None:
        col_main = mono or color
        col_dim = mono or dim
        col_acc = mono or accent

        def arm(a1: float, a2: float, col: tuple[int, int, int]) -> None:
            elbow = _polar(shoulder, a1, 0.17 * h)
            hand = _polar(elbow, a1 + a2, 0.15 * h)
            o = inflate * 2
            _tapered(draw, shoulder, elbow, lw + o, lw * 0.85 + o, col)
            _tapered(draw, elbow, hand, lw * 0.85 + o, lw * 0.7 + o, col)
            r = lw * 0.62 + inflate
            draw.ellipse([hand[0] - r, hand[1] - r, hand[0] + r, hand[1] + r],
                         fill=col)

        def leg(a1: float, a2: float, col: tuple[int, int, int]) -> None:
            knee = _polar(pelvis, a1, 0.25 * h)
            ankle = _polar(knee, a1 + a2, 0.23 * h)
            o = inflate * 2
            _tapered(draw, pelvis, knee, lw * 1.1 + o, lw * 0.95 + o, col)
            _tapered(draw, knee, ankle, lw * 0.95 + o, lw * 0.8 + o, col)
            # Schuh: nach vorne gezogene Ellipse
            sw, sh = lw * 2.1, lw * 1.05
            draw.ellipse(
                [ankle[0] - sw * 0.35 - inflate, ankle[1] - sh * 0.55 - inflate,
                 ankle[0] + sw * 0.65 + inflate, ankle[1] + sh * 0.45 + inflate],
                fill=col,
            )

        # hintere Gliedmaßen zuerst (gedimmt), dann Körper, dann vordere
        arm(pose.l_shoulder, pose.l_elbow, col_dim)
        leg(pose.l_hip, pose.l_knee, col_dim)

        # Torso: unten schmaler, oben breiter (Schultern)
        _tapered(draw, pelvis, neck,
                 lw * 0.95 + inflate * 2, lw * 1.25 + inflate * 2, col_main)

        leg(pose.r_hip, pose.r_knee, col_main)
        arm(pose.r_shoulder, pose.r_elbow, col_main)

        # Kopf: gefüllt, liest sich in jeder Größe sauber
        r = head_r + inflate
        draw.ellipse([head_c[0] - r, head_c[1] - r,
                      head_c[0] + r, head_c[1] + r], fill=col_main)

        _draw_accessory(draw, spec, head_c, head_r, lw, col_acc,
                        inflate=inflate, decorations=inflate == 0)

    # Kontur-Pass: ganze Silhouette leicht aufgepumpt in Konturfarbe,
    # macht die Figur auch auf hellen Hintergründen sichtbar
    ow = spec.outline_width * h
    if ow > 0:
        paint(ow, _hex_rgb(spec.outline_color))
    paint(0.0, None)
    _draw_face(draw, spec, pose.expression, head_c, head_r)


def _draw_face(
    draw: ImageDraw.ImageDraw,
    spec: CharacterSpec,
    expression: str,
    head_c: Point,
    head_r: float,
) -> None:
    """Augen, Brauen und Mund nach Ausdruck; Farben = bg_color auf dem
    gefüllten Kopf. Nach dem Accessoire, damit die Cap nichts verdeckt."""
    fc = _hex_rgb(spec.bg_color)
    x, y = head_c
    hr = head_r
    stroke = max(2, round(hr * 0.10))
    eye_y = y + 0.10 * hr
    eye_xs = (x + 0.22 * hr, x + 0.60 * hr)

    if spec.eyes:
        if expression == "sleepy":
            # geschlossene Augen: kleine Bögen
            for ex in eye_xs:
                r = 0.16 * hr
                draw.arc([ex - r, eye_y - r * 0.4, ex + r, eye_y + r],
                         20, 160, fill=fc, width=stroke)
        else:
            er = hr * (0.18 if expression == "shocked" else 0.13)
            er = max(2.0, er)
            for ex in eye_xs:
                draw.ellipse([ex - er, eye_y - er, ex + er, eye_y + er],
                             fill=fc)

        # Augenbrauen nur bei starken Emotionen
        brow_y = y - 0.14 * hr
        bl = 0.13 * hr
        if expression == "angry":
            for ex in eye_xs:
                draw.line([(ex - bl, brow_y - 0.07 * hr),
                           (ex + bl, brow_y + 0.07 * hr)], fill=fc, width=stroke)
        elif expression == "sad":
            for ex in eye_xs:
                draw.line([(ex - bl, brow_y + 0.06 * hr),
                           (ex + bl, brow_y - 0.04 * hr)], fill=fc, width=stroke)
        elif expression == "shocked":
            for ex in eye_xs:
                draw.line([(ex - bl, brow_y - 0.12 * hr),
                           (ex + bl, brow_y - 0.12 * hr)], fill=fc, width=stroke)

    # Mund vorne unten am Kopf (Charakter schaut nach rechts)
    mx, my = x + 0.40 * hr, y + 0.52 * hr
    if expression in ("smile", "neutral"):
        r = 0.26 * hr if expression == "smile" else 0.18 * hr
        draw.arc([mx - r, my - r * 1.4, mx + r, my + r * 0.6],
                 30, 150, fill=fc, width=stroke)
    elif expression == "grin":
        r = 0.30 * hr
        draw.pieslice([mx - r, my - r * 0.75, mx + r, my + r * 0.75],
                      0, 180, fill=fc)
    elif expression in ("flat", "angry"):
        r = 0.20 * hr
        draw.line([(mx - r, my), (mx + r, my)], fill=fc, width=stroke)
    elif expression == "sad":
        r = 0.22 * hr
        draw.arc([mx - r, my - r * 0.4, mx + r, my + r * 1.6],
                 210, 330, fill=fc, width=stroke)
    elif expression == "shocked":
        rx, ry = 0.16 * hr, 0.22 * hr
        draw.ellipse([mx - rx, my - ry, mx + rx, my + ry], fill=fc)
    elif expression == "sleepy":
        r = 0.12 * hr
        draw.line([(mx - r, my), (mx + r, my)], fill=fc, width=stroke)


def _draw_accessory(
    draw: ImageDraw.ImageDraw,
    spec: CharacterSpec,
    head_c: Point,
    head_r: float,
    lw: float,
    accent: tuple[int, int, int],
    *,
    inflate: float = 0.0,
    decorations: bool = True,
) -> None:
    """`inflate` pumpt die Formen für den Kontur-Pass auf;
    `decorations` schaltet innenliegende Details (Naht, Button) ab."""
    x, y = head_c
    o = inflate
    if spec.accessory == "cap":
        s = head_r * 1.12 + o
        draw.pieslice([x - s, y - s, x + s, y + s], 190, 350, fill=accent)
        # Schild als flaches Oval nach vorne
        draw.ellipse(
            [x + head_r * 0.30 - o, y - head_r * 0.62 - o,
             x + head_r * 1.75 + o, y - head_r * 0.28 + o],
            fill=accent,
        )
        if decorations:
            dark = _blend(spec.accent_color, "#000000", 0.25)
            draw.arc([x - s * 0.55, y - s, x + s * 0.55, y + s * 0.2],
                     220, 320, fill=dark, width=max(2, round(lw * 0.35)))
            br = head_r * 0.12
            draw.ellipse([x - br, y - s - br, x + br, y - s + br], fill=dark)
    elif spec.accessory == "beanie":
        s = head_r * 1.12 + o
        draw.pieslice([x - s, y - s, x + s, y + s], 185, 355, fill=accent)
        pr = head_r * 0.22 + o
        draw.ellipse([x - pr, y - s - pr * 1.2, x + pr, y - s + pr * 0.8],
                     fill=accent)
    elif spec.accessory == "headphones":
        s = head_r * 1.25
        draw.arc([x - s - o, y - s - o, x + s + o, y + s + o], 195, 345,
                 fill=accent, width=max(2, round(lw * 0.8 + 2 * o)))
        pr = head_r * 0.28 + o
        for px in (x - head_r * 1.05, x + head_r * 1.05):
            draw.ellipse([px - pr, y - pr * 1.6, px + pr, y + pr * 0.4],
                         fill=accent)
    elif spec.accessory == "antenna":
        top = (x + head_r * 0.15, y - head_r)
        tip = (x + head_r * 0.3, y - head_r * 1.75)
        draw.line([top, tip], fill=accent, width=max(2, round(lw * 0.7 + 2 * o)))
        pr = head_r * 0.16 + o
        draw.ellipse([tip[0] - pr, tip[1] - pr, tip[0] + pr, tip[1] + pr],
                     fill=accent)


# ============================================================
# Szene / Hintergrund
# ============================================================


def _scene_base(spec: CharacterSpec, w: int, h: int) -> Image.Image:
    """Brand-Hintergrund: vertikaler Verlauf + sanfter Spot hinter dem Charakter."""
    top = _blend(spec.bg_color, "#000000", 0.25)
    mid = _hex_rgb(spec.bg_color)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = abs(y / h - 0.42) * 1.6
        t = min(t, 1.0)
        grad.putpixel((0, y), (
            round(mid[0] + (top[0] - mid[0]) * t),
            round(mid[1] + (top[1] - mid[1]) * t),
            round(mid[2] + (top[2] - mid[2]) * t),
        ))
    img = grad.resize((w, h))

    spot = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(spot)
    cx, cy, r = w / 2, h * 0.62, min(w, h) * 0.55
    steps = 48
    for i in range(steps, 0, -1):
        rr = r * i / steps
        sd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   fill=round(26 * (1 - i / steps) ** 2))
    glow = Image.new("RGB", (w, h), _blend(spec.bg_color, spec.line_color, 0.5))
    img.paste(glow, (0, 0), spot)
    return img


def _draw_particles(
    draw: ImageDraw.ImageDraw, spec: CharacterSpec, w: int, h: int, t: float
) -> None:
    col = _blend(spec.bg_color, spec.accent_color, 0.4)
    for i in range(14):
        speed = 0.012 + (i % 5) * 0.006
        px = ((i * 0.618 + 0.13) % 1.0 + 0.02 * math.sin(t * 0.7 + i)) * w
        py = ((i * 0.382 + 0.41 - t * speed) % 1.0) * h
        r = 2.0 + (i % 3)
        draw.ellipse([px - r, py - r, px + r, py + r], fill=col)


def _draw_ground(
    draw: ImageDraw.ImageDraw, spec: CharacterSpec, w: int, ground_y: float
) -> None:
    draw.line(
        [(w * 0.08, ground_y), (w * 0.92, ground_y)],
        fill=_hex_rgb(spec.accent_color), width=max(3, w // 270),
    )


def _draw_brand_tag(
    draw: ImageDraw.ImageDraw, spec: CharacterSpec, w: int, h: int
) -> None:
    size = max(24, h // 32)
    font = _font(size)
    text = spec.name.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (w - tw) / 2
    y = h * 0.045
    draw.text((x, y), text, font=font, fill=_hex_rgb(spec.line_color))
    bar_y = y + size * 1.35
    draw.line([(x, bar_y), (x + tw, bar_y)],
              fill=_hex_rgb(spec.accent_color), width=max(3, size // 8))


# ============================================================
# Bilder: Pose, Posen-Übersicht, Thumbnail
# ============================================================


def character_image(
    spec: CharacterSpec,
    pose: Pose,
    *,
    size: int = 1080,
    mirror: bool = False,
    ss: int = 3,
) -> Image.Image:
    """Charakter allein auf transparentem Quadrat; `mirror` lässt ihn nach
    links schauen. Posen mit `rot` (z.B. liegend) werden gedreht.

    `ss` = Supersampling-Faktor: intern größer rendern und runterskalieren
    für glatte Kanten (Pillow zeichnet sonst ohne Antialiasing)."""
    big = size * max(1, ss)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    height = big * (0.62 if pose.rot else 0.8)
    foot_y = big * 0.92
    draw_character(draw, spec, pose, foot=(big / 2, foot_y), height=height)
    if pose.rot:
        center = (big / 2, foot_y - height * 0.5)
        img = img.rotate(pose.rot, center=center, resample=Image.BICUBIC)
    if big != size:
        img = img.resize((size, size), Image.LANCZOS)
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


def paste_character(
    canvas: Image.Image,
    spec: CharacterSpec,
    pose: Pose,
    *,
    foot: Point,
    height: float,
    mirror: bool = False,
    ss: int = 3,
) -> None:
    """Charakter mit Fußpunkt-Anker in eine Szene einfügen (mit Alphakanal)."""
    size = int(round(height / (0.62 if pose.rot else 0.8)))
    img = character_image(spec, pose, size=size, mirror=mirror, ss=ss)
    canvas.paste(img, (int(foot[0] - size / 2), int(foot[1] - size * 0.92)), img)


def _draw_shadow(
    draw: ImageDraw.ImageDraw,
    spec: CharacterSpec,
    foot: Point,
    height: float,
) -> None:
    """Weicher Bodenschatten unter dem Charakter."""
    w, h = height * 0.30, height * 0.040
    col = _blend(spec.bg_color, "#000000", 0.45)
    draw.ellipse(
        [foot[0] - w / 2, foot[1] - h / 2, foot[0] + w / 2, foot[1] + h / 2],
        fill=col,
    )


def render_pose_image(
    spec: CharacterSpec,
    pose_name: str,
    out_path: Path,
    *,
    size: int = 1080,
    transparent: bool = False,
    mirror: bool = False,
) -> Path:
    if pose_name not in POSES:
        raise ValueError(f"Unbekannte Pose '{pose_name}'. Verfügbar: {list(POSES)}")
    img = character_image(spec, POSES[pose_name], size=size, mirror=mirror)
    if not transparent:
        bg = Image.new("RGB", (size, size), _hex_rgb(spec.bg_color))
        bg.paste(img, (0, 0), img)
        img = bg
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def render_library(
    spec: CharacterSpec, out_dir: Path, *, size: int = 1080
) -> list[Path]:
    """Alle Posen als transparente PNGs in einen festen Ordner rendern.

    Pro Pose zwei Dateien: `<pose>.png` (schaut nach rechts) und
    `<pose>_left.png` (gespiegelt). Dazu `_uebersicht.png` und ein
    `library.json`-Manifest.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, pose in POSES.items():
        for mirror, suffix in ((False, ""), (True, "_left")):
            img = character_image(spec, pose, size=size, mirror=mirror)
            path = out_dir / f"{name}{suffix}.png"
            img.save(path, "PNG")
            paths.append(path)

    render_pose_sheet(spec, out_dir / "_uebersicht.png")
    manifest = {
        "character": asdict(spec),
        "size": size,
        "poses": list(POSES),
        "files": [p.name for p in paths],
    }
    (out_dir / "library.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return paths


def render_pose_sheet(
    spec: CharacterSpec, out_path: Path, *, cols: int = 4, cell: int = 420
) -> Path:
    names = list(POSES)
    rows = math.ceil(len(names) / cols)
    img = Image.new("RGB", (cols * cell, rows * cell), _hex_rgb(spec.bg_color))
    draw = ImageDraw.Draw(img)
    label_font = _font(cell // 14)
    grid_col = _blend(spec.bg_color, spec.line_color, 0.15)

    sub_size = int(cell * 0.82)
    for i, name in enumerate(names):
        cx = (i % cols) * cell
        cy = (i // cols) * cell
        draw.rectangle([cx, cy, cx + cell, cy + cell], outline=grid_col, width=2)
        sub = character_image(spec, POSES[name], size=sub_size)
        img.paste(sub, (cx + (cell - sub_size) // 2, cy + cell - sub_size), sub)
        draw.text((cx + cell * 0.06, cy + cell * 0.05), name,
                  font=label_font, fill=_hex_rgb(spec.accent_color))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def render_thumbnail(
    spec: CharacterSpec,
    title: str,
    out_path: Path,
    *,
    pose: str = "point",
    width: int = 1280,
    height: int = 720,
) -> Path:
    if pose not in POSES:
        raise ValueError(f"Unbekannte Pose '{pose}'. Verfügbar: {list(POSES)}")
    img = _scene_base(spec, width, height)
    draw = ImageDraw.Draw(img)

    portrait = height > width
    if portrait:
        char_h = height * 0.42
        foot = (width / 2, height * 0.94)
        text_area = (width * 0.08, height * 0.10, width * 0.92)
        title_size = width // 9
        wrap = 14
    else:
        char_h = height * 0.78
        foot = (width * 0.78, height * 0.93)
        text_area = (width * 0.06, height * 0.18, width * 0.58)
        title_size = width // 14
        wrap = 14

    _draw_shadow(draw, spec, foot, char_h)
    paste_character(img, spec, POSES[pose], foot=foot, height=char_h)
    draw = ImageDraw.Draw(img)

    font = _font(title_size)
    x0, y, x1 = text_area
    lines = textwrap.wrap(title, width=wrap) or [title]
    line_h = title_size * 1.18
    for line in lines:
        draw.text((x0, y), line, font=font, fill=_hex_rgb(spec.line_color),
                  stroke_width=max(2, title_size // 24),
                  stroke_fill=_blend(spec.bg_color, "#000000", 0.5))
        y += line_h
    bar_w = title_size * 3
    draw.line([(x0, y + 14), (x0 + bar_w, y + 14)],
              fill=_hex_rgb(spec.accent_color), width=max(4, title_size // 9))

    _draw_brand_tag(draw, spec, width, height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


# ============================================================
# Animierter Video-Hintergrund
# ============================================================

# Gesten-Playlist, die im Hintergrundvideo durchläuft
GESTURE_LOOP = [
    "idle", "wave", "idle", "point", "present",
    "idle", "think", "celebrate", "idle", "shrug",
]
_TRANSITION = 0.5   # Sekunden Überblendung zwischen Posen
_HOLD = 1.4         # Sekunden Haltezeit pro Pose
_WALK_IN = 2.0      # Sekunden Lauf-Intro


def _pose_at(t: float) -> tuple[Pose, float]:
    """Pose + horizontale Position (0..1) zum Zeitpunkt t."""
    if t < _WALK_IN:
        u = _ease(t / _WALK_IN)
        x = -0.12 + (0.5 + 0.12) * u
        pose = walk_pose(t * 1.7)
        # kurz vor Ankunft in idle überblenden
        if t > _WALK_IN - 0.4:
            blend = _ease((t - (_WALK_IN - 0.4)) / 0.4)
            pose = _lerp_pose(pose, POSES["idle"], blend)
        return pose, x

    u = t - _WALK_IN
    seg = _TRANSITION + _HOLD
    k = int(u // seg)
    local = u - k * seg
    cur = POSES[GESTURE_LOOP[k % len(GESTURE_LOOP)]]
    prev = POSES[GESTURE_LOOP[(k - 1) % len(GESTURE_LOOP)]] if k > 0 else POSES["idle"]
    if local < _TRANSITION:
        pose = _lerp_pose(prev, cur, _ease(local / _TRANSITION))
    else:
        pose = cur
    return pose, 0.5


def _breathe(pose: Pose, t: float) -> Pose:
    """Subtile Dauerbewegung, damit der Charakter nie statisch wirkt."""
    sway = math.sin(2 * math.pi * 0.35 * t)
    return replace(
        pose,
        lift=pose.lift + 0.004 * math.sin(2 * math.pi * 0.45 * t),
        l_shoulder=pose.l_shoulder + 1.5 * sway,
        r_shoulder=pose.r_shoulder - 1.5 * sway,
        head=pose.head + 1.2 * math.sin(2 * math.pi * 0.25 * t + 1.0),
    )


def render_background_video(
    spec: CharacterSpec,
    duration: float,
    width: int,
    height: int,
    out_path: Path,
    *,
    fps: int = 30,
    brand_tag: bool = True,
) -> Path:
    """Rendert den animierten Brand-Hintergrund als MP4 (ohne Audio)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base = _scene_base(spec, width, height)
    ground_y = height * (0.80 if height > width else 0.86)
    char_h = height * (0.34 if height > width else 0.52)
    n_frames = max(1, round(duration * fps))

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    try:
        for i in range(n_frames):
            t = i / fps
            frame = base.copy()
            draw = ImageDraw.Draw(frame)
            _draw_particles(draw, spec, width, height, t)
            _draw_ground(draw, spec, width, ground_y)
            pose, x_frac = _pose_at(t)
            pose = _breathe(pose, t)
            char_foot = (x_frac * width, ground_y)
            _draw_shadow(draw, spec, char_foot, char_h)
            paste_character(frame, spec, pose, foot=char_foot, height=char_h, ss=2)
            if brand_tag:
                _draw_brand_tag(draw, spec, width, height)
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    return out_path


__all__ = [
    "ACCESSORIES",
    "EXPRESSIONS",
    "POSES",
    "CharacterSpec",
    "Pose",
    "character_image",
    "draw_character",
    "paste_character",
    "render_background_video",
    "render_library",
    "render_pose_image",
    "render_pose_sheet",
    "render_thumbnail",
    "walk_pose",
]
