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


POSES: dict[str, Pose] = {
    "idle": Pose(),
    "wave": Pose(torso=2, head=-3, r_shoulder=150, r_elbow=35),
    "point": Pose(torso=5, r_shoulder=95, r_elbow=-5, l_shoulder=18, l_elbow=12),
    "present": Pose(torso=3, r_shoulder=60, r_elbow=35, l_shoulder=14),
    "think": Pose(torso=-2, head=9, r_shoulder=55, r_elbow=125, l_shoulder=12),
    "celebrate": Pose(
        torso=-3, head=-6, lift=0.025,
        l_shoulder=160, l_elbow=15, r_shoulder=205, r_elbow=-15,
        l_hip=12, l_knee=-8, r_hip=-12, r_knee=8,
    ),
    "facepalm": Pose(torso=6, head=14, r_shoulder=70, r_elbow=132),
    "shrug": Pose(
        torso=-2, head=6,
        l_shoulder=42, l_elbow=95, r_shoulder=-42, r_elbow=-95,
    ),
}


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


def _lerp_pose(a: Pose, b: Pose, t: float) -> Pose:
    vals = {
        f.name: getattr(a, f.name) + (getattr(b, f.name) - getattr(a, f.name)) * t
        for f in fields(Pose)
    }
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
    lw = max(2, round(spec.line_width * h))
    color = on_color or _hex_rgb(spec.line_color)
    dim = _blend(spec.line_color, spec.bg_color, 0.4)
    accent = _hex_rgb(spec.accent_color)

    pelvis = (foot[0], foot[1] - 0.48 * h - pose.lift * h)
    neck = _polar(pelvis, 180 - pose.torso, 0.30 * h)
    shoulder = _polar(pelvis, 180 - pose.torso, 0.28 * h)
    head_c = _polar(neck, 180 - pose.torso - pose.head, 0.04 * h + head_r)

    def limb(origin: Point, a1: float, l1: float, a2: float, l2: float,
             col: tuple[int, int, int]) -> None:
        mid = _polar(origin, a1, l1)
        end = _polar(mid, a1 + a2, l2)
        draw.line([origin, mid, end], fill=col, width=lw, joint="curve")
        for p in (origin, mid, end):
            r = lw / 2 - 0.5
            draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=col)

    # hintere Gliedmaßen zuerst (gedimmt), dann Körper, dann vordere
    limb(shoulder, pose.l_shoulder, 0.17 * h, pose.l_elbow, 0.15 * h, dim)
    limb(pelvis, pose.l_hip, 0.25 * h, pose.l_knee, 0.23 * h, dim)

    draw.line([pelvis, neck], fill=color, width=lw, joint="curve")

    limb(pelvis, pose.r_hip, 0.25 * h, pose.r_knee, 0.23 * h, color)
    limb(shoulder, pose.r_shoulder, 0.17 * h, pose.r_elbow, 0.15 * h, color)

    # Kopf: gefüllt, liest sich in jeder Größe sauber
    bbox = [head_c[0] - head_r, head_c[1] - head_r,
            head_c[0] + head_r, head_c[1] + head_r]
    draw.ellipse(bbox, fill=color)

    _draw_accessory(draw, spec, head_c, head_r, lw, accent)

    # Augen nach dem Accessoire, damit z.B. die Cap sie nicht verdeckt
    if spec.eyes:
        eye_col = _hex_rgb(spec.bg_color)
        er = max(2.0, head_r * 0.13)
        for ex in (0.22, 0.60):
            p = (head_c[0] + ex * head_r, head_c[1] + 0.10 * head_r)
            draw.ellipse([p[0] - er, p[1] - er, p[0] + er, p[1] + er],
                         fill=eye_col)


def _draw_accessory(
    draw: ImageDraw.ImageDraw,
    spec: CharacterSpec,
    head_c: Point,
    head_r: float,
    lw: int,
    accent: tuple[int, int, int],
) -> None:
    x, y = head_c
    if spec.accessory == "cap":
        s = head_r * 1.12
        draw.pieslice([x - s, y - s, x + s, y + s], 190, 350, fill=accent)
        brim_y = y - head_r * 0.42
        draw.line(
            [(x + head_r * 0.45, brim_y), (x + head_r * 1.7, brim_y - head_r * 0.1)],
            fill=accent, width=max(2, round(lw * 0.9)),
        )
    elif spec.accessory == "beanie":
        s = head_r * 1.12
        draw.pieslice([x - s, y - s, x + s, y + s], 185, 355, fill=accent)
        pr = head_r * 0.22
        draw.ellipse([x - pr, y - s - pr * 1.2, x + pr, y - s + pr * 0.8],
                     fill=accent)
    elif spec.accessory == "headphones":
        s = head_r * 1.25
        draw.arc([x - s, y - s, x + s, y + s], 195, 345,
                 fill=accent, width=max(2, round(lw * 0.8)))
        pr = head_r * 0.28
        for px in (x - head_r * 1.05, x + head_r * 1.05):
            draw.ellipse([px - pr, y - pr * 1.6, px + pr, y + pr * 0.4],
                         fill=accent)
    elif spec.accessory == "antenna":
        top = (x + head_r * 0.15, y - head_r)
        tip = (x + head_r * 0.3, y - head_r * 1.75)
        draw.line([top, tip], fill=accent, width=max(2, round(lw * 0.7)))
        pr = head_r * 0.16
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


def render_pose_image(
    spec: CharacterSpec,
    pose_name: str,
    out_path: Path,
    *,
    size: int = 1080,
    transparent: bool = False,
) -> Path:
    if pose_name not in POSES:
        raise ValueError(f"Unbekannte Pose '{pose_name}'. Verfügbar: {list(POSES)}")
    mode = "RGBA" if transparent else "RGB"
    bg = (0, 0, 0, 0) if transparent else _hex_rgb(spec.bg_color)
    img = Image.new(mode, (size, size), bg)
    draw = ImageDraw.Draw(img)
    draw_character(
        draw, spec, POSES[pose_name],
        foot=(size / 2, size * 0.92), height=size * 0.8,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def render_pose_sheet(
    spec: CharacterSpec, out_path: Path, *, cols: int = 4, cell: int = 420
) -> Path:
    names = list(POSES)
    rows = math.ceil(len(names) / cols)
    img = Image.new("RGB", (cols * cell, rows * cell), _hex_rgb(spec.bg_color))
    draw = ImageDraw.Draw(img)
    label_font = _font(cell // 14)
    grid_col = _blend(spec.bg_color, spec.line_color, 0.15)

    for i, name in enumerate(names):
        cx = (i % cols) * cell
        cy = (i // cols) * cell
        draw.rectangle([cx, cy, cx + cell, cy + cell], outline=grid_col, width=2)
        draw_character(
            draw, spec, POSES[name],
            foot=(cx + cell / 2, cy + cell * 0.86), height=cell * 0.66,
        )
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

    draw_character(draw, spec, POSES[pose], foot=foot, height=char_h)

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
            draw_character(
                draw, spec, pose,
                foot=(x_frac * width, ground_y), height=char_h,
            )
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
    "POSES",
    "CharacterSpec",
    "Pose",
    "draw_character",
    "render_background_video",
    "render_pose_image",
    "render_pose_sheet",
    "render_thumbnail",
    "walk_pose",
]
