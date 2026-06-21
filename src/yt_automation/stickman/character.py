"""Brand character: a consistent stickman mascot with a recognisable trademark.

The whole point of a personal brand is one instantly-recognisable look that
appears on every single frame. A :class:`Character` bundles the figure colour,
glow colour, and a signature accessory (headwear / eyewear / prop) that
:func:`draw_accessories` paints on top of the base figure. Pick one trademark
and keep it forever — that's the recognisability.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

from .skeleton import Joints

HEADWEAR = ["none", "headband", "cap", "beanie", "crown", "horns", "antenna"]
EYEWEAR = ["none", "shades", "glasses", "visor"]
PROPS = ["none", "bowtie", "scarf"]


@dataclass(frozen=True)
class Character:
    name: str = "Iko"
    body: tuple[int, int, int] = (240, 244, 255)
    glow: tuple[int, int, int] = (0, 224, 255)
    accent: tuple[int, int, int] = (255, 42, 109)
    headwear: str = "headband"
    eyewear: str = "shades"
    prop: str = "none"


PRESETS: dict[str, Character] = {
    "iko":   Character("Iko", glow=(0, 224, 255), accent=(255, 42, 109),
                       headwear="headband", eyewear="shades"),
    "halo":  Character("Halo", glow=(120, 200, 255), accent=(255, 215, 0),
                       headwear="antenna", eyewear="none"),
    "boss":  Character("Boss", glow=(255, 80, 80), accent=(255, 200, 40),
                       headwear="crown", eyewear="shades"),
    "sage":  Character("Sage", glow=(150, 90, 255), accent=(0, 255, 180),
                       headwear="none", eyewear="glasses"),
    "rookie": Character("Rookie", glow=(0, 240, 255), accent=(255, 120, 0),
                        headwear="cap", eyewear="none"),
    "cyber": Character("Cyber", glow=(0, 255, 180), accent=(255, 0, 160),
                       headwear="none", eyewear="visor"),
}


def get_character(name: str | None) -> Character:
    if not name:
        return PRESETS["iko"]
    return PRESETS.get(name.strip().lower(), PRESETS["iko"])


def character_names() -> list[str]:
    return list(PRESETS.keys())


def _paint(d: ImageDraw.ImageDraw, j: Joints, ch: Character) -> None:
    """Paint every accessory stroke once (used for both crisp layer and glow)."""
    hx, hy = j.head_center
    r = j.head_radius
    a = ch.accent + (255,)
    lw = max(2, int(r * 0.22))

    # ---- headwear ----
    if ch.headwear == "headband":
        y0 = hy - r * 0.32
        d.line([(hx - r * 1.06, y0), (hx + r * 1.06, y0)], fill=a, width=int(r * 0.5))
        d.line([(hx - r * 0.9, y0), (hx - r * 1.5, y0 + r * 0.5)], fill=a, width=lw)
        d.line([(hx - r * 0.9, y0), (hx - r * 1.4, y0 + r * 0.95)], fill=a, width=lw)
    elif ch.headwear == "cap":
        d.pieslice([hx - r * 1.05, hy - r * 1.05, hx + r * 1.05, hy + r * 1.05],
                   start=180, end=360, fill=a)
        d.polygon([(hx, hy - r * 0.05), (hx + r * 1.7, hy - r * 0.28),
                   (hx + r * 1.7, hy + r * 0.02), (hx, hy + r * 0.25)], fill=a)
    elif ch.headwear == "beanie":
        d.pieslice([hx - r * 1.05, hy - r * 1.2, hx + r * 1.05, hy + r * 0.9],
                   start=180, end=360, fill=a)
        d.line([(hx - r * 1.05, hy - r * 0.25), (hx + r * 1.05, hy - r * 0.25)],
               fill=a, width=int(r * 0.4))
        d.ellipse([hx - r * 0.18, hy - r * 1.55, hx + r * 0.18, hy - r * 1.2], fill=a)
    elif ch.headwear == "crown":
        by = hy - r * 0.7
        d.polygon([(hx - r, by), (hx - r * 0.6, by - r * 0.8), (hx - r * 0.2, by),
                   (hx + r * 0.2, by - r), (hx + r * 0.6, by), (hx + r, by - r * 0.8),
                   (hx + r, by + r * 0.2), (hx - r, by + r * 0.2)], fill=a)
    elif ch.headwear == "horns":
        for sx in (-1, 1):
            d.polygon([(hx + sx * r * 0.5, hy - r * 0.8), (hx + sx * r * 1.1, hy - r * 1.5),
                       (hx + sx * r * 0.95, hy - r * 0.7)], fill=a)
    elif ch.headwear == "antenna":
        top, bulb = (hx, hy - r), (hx + r * 0.15, hy - r * 2.1)
        d.line([top, bulb], fill=a, width=lw)
        d.ellipse([bulb[0] - r * 0.32, bulb[1] - r * 0.32,
                   bulb[0] + r * 0.32, bulb[1] + r * 0.32], fill=a)

    # ---- eyewear ----
    if ch.eyewear == "shades":
        top, bot, left, right = hy - r * 0.12, hy + r * 0.30, hx - r * 0.92, hx + r * 0.92
        d.rounded_rectangle([left, top, right, bot], radius=int(r * 0.18),
                            fill=(12, 14, 22, 255), outline=a, width=max(2, int(r * 0.14)))
        d.line([(left, (top + bot) / 2), (right, (top + bot) / 2)],
               fill=ch.accent + (180,), width=max(1, int(r * 0.08)))
    elif ch.eyewear == "glasses":
        for sx in (-1, 1):
            cx = hx + sx * r * 0.42
            d.ellipse([cx - r * 0.42, hy - r * 0.18, cx + r * 0.42, hy + r * 0.5],
                      outline=a, width=lw)
        d.line([(hx - r * 0.05, hy + r * 0.12), (hx + r * 0.05, hy + r * 0.12)],
               fill=a, width=lw)
    elif ch.eyewear == "visor":
        d.rounded_rectangle([hx - r * 0.98, hy - r * 0.05, hx + r * 0.98, hy + r * 0.32],
                            radius=int(r * 0.16), fill=ch.accent + (235,))

    # ---- prop ----
    nx, ny = j.neck
    if ch.prop == "bowtie":
        s = r * 0.5
        d.polygon([(nx, ny), (nx - s, ny - s * 0.7), (nx - s, ny + s * 0.7)], fill=a)
        d.polygon([(nx, ny), (nx + s, ny - s * 0.7), (nx + s, ny + s * 0.7)], fill=a)
        d.ellipse([nx - s * 0.25, ny - s * 0.25, nx + s * 0.25, ny + s * 0.25], fill=a)
    elif ch.prop == "scarf":
        d.line([(nx - r * 0.6, ny), (nx + r * 0.6, ny)], fill=a, width=int(r * 0.4))
        d.line([(nx + r * 0.3, ny), (nx + r * 0.6, ny + r * 1.2)], fill=a,
               width=int(r * 0.35))


def draw_accessories(img: Image.Image, j: Joints, ch: Character) -> None:
    """Paint the character's signature accessory (with glow) over the figure."""
    if ch.headwear == "none" and ch.eyewear == "none" and ch.prop == "none":
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    _paint(ImageDraw.Draw(layer), j, ch)
    if layer.getbbox() is None:
        return
    glow = layer.filter(ImageFilter.GaussianBlur(max(3, int(j.head_radius * 0.28))))
    out = Image.alpha_composite(img.convert("RGBA"), glow)
    out = Image.alpha_composite(out, layer)
    img.paste(out.convert("RGB"), (0, 0))
