"""Pillow renderer: dark, high-contrast, "intense" stickman frames.

Draws a figure from resolved :class:`Joints` plus a styled background and a set
of punchy foreground effects (zoom punch, screen flash, camera shake, motion
lines, kinetic keyword text). Frames are produced one at a time and handed to
FFmpeg by :mod:`.scene`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .skeleton import Joints, Point


@dataclass(frozen=True)
class Theme:
    """Channel look. Colours are RGB tuples."""

    name: str = "midnight"
    bg_top: tuple[int, int, int] = (12, 14, 24)
    bg_bottom: tuple[int, int, int] = (3, 4, 9)
    accent: tuple[int, int, int] = (0, 224, 255)      # neon cyan
    accent2: tuple[int, int, int] = (255, 42, 109)    # hot magenta
    figure: tuple[int, int, int] = (240, 244, 255)
    keyword: tuple[int, int, int] = (255, 255, 255)
    grid: tuple[int, int, int] = (40, 48, 74)
    glow: bool = True


THEMES: dict[str, Theme] = {
    "midnight": Theme(),
    "bloodmoon": Theme(
        name="bloodmoon",
        bg_top=(26, 8, 12),
        bg_bottom=(6, 2, 3),
        accent=(255, 60, 60),
        accent2=(255, 170, 40),
        grid=(70, 24, 28),
    ),
    "void": Theme(
        name="void",
        bg_top=(10, 10, 14),
        bg_bottom=(0, 0, 0),
        accent=(150, 90, 255),
        accent2=(0, 255, 180),
        grid=(38, 34, 56),
    ),
    "synthwave": Theme(
        name="synthwave",
        bg_top=(20, 8, 40),
        bg_bottom=(4, 2, 14),
        accent=(0, 240, 255),
        accent2=(255, 0, 160),
        grid=(60, 24, 90),
    ),
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES["midnight"])


# ----------------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------------

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for cand in _FONT_CANDIDATES:
        if Path(cand).exists():
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default(size)


# ----------------------------------------------------------------------------
# Background
# ----------------------------------------------------------------------------


def _vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return base.resize((w, h))


def make_base_background(
    w: int, h: int, theme: Theme, *, energy: float = 0.5
) -> Image.Image:
    """Gradient + radial accent glow. Expensive (blur) but constant within a
    beat, so callers should cache it per energy level."""
    img = _vertical_gradient(w, h, theme.bg_top, theme.bg_bottom)
    if theme.glow:
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cx, cy = w * 0.5, h * 0.52
        r = int(min(w, h) * (0.42 + 0.06 * energy))
        a = int(60 + 70 * energy)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=theme.accent + (a,))
        glow = glow.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.12)))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    return img


def draw_grid(img: Image.Image, theme: Theme, *, t: float = 0.0, energy: float = 0.5) -> None:
    """Draw the drifting perspective floor grid in place (cheap, per-frame)."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    horizon = int(h * 0.62)
    drift = (t * 60.0) % 60.0
    line_a = int(70 + 50 * energy)
    for i in range(1, 26):
        yy = horizon + (i * 18) + drift
        if yy >= h:
            break
        fade = max(0, 1 - (yy - horizon) / (h - horizon))
        draw.line([(0, yy), (w, yy)], fill=theme.grid + (int(line_a * fade),), width=2)
    cx = w * 0.5
    for gx in range(-12, 13):
        x_top = cx + gx * (w * 0.018)
        x_bot = cx + gx * (w * 0.16)
        draw.line([(x_top, horizon), (x_bot, h)],
                  fill=theme.grid + (int(line_a * 0.7),), width=2)


def make_background(
    w: int, h: int, theme: Theme, *, t: float = 0.0, energy: float = 0.5
) -> Image.Image:
    """Convenience: base background + grid in one call (used by tests/thumbnails)."""
    img = make_base_background(w, h, theme, energy=energy)
    draw_grid(img, theme, t=t, energy=energy)
    return img


def build_vignette_mask(w: int, h: int, strength: float = 0.85) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=int(255 * strength))
    return mask.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.08)))


def apply_vignette(img: Image.Image, strength: float = 0.85) -> Image.Image:
    mask = build_vignette_mask(img.size[0], img.size[1], strength)
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(img, black, mask)


def apply_vignette_mask(img: Image.Image, mask: Image.Image, black: Image.Image) -> Image.Image:
    return Image.composite(img, black, mask)


# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------


def _seg(draw, p0: Point, p1: Point, color, width: int) -> None:
    draw.line([p0, p1], fill=color, width=width, joint="curve")
    r = width / 2.0
    for p in (p0, p1):
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def draw_figure(
    img: Image.Image,
    j: Joints,
    *,
    color=(240, 244, 255),
    weight: float = 1.0,
    glow_color: tuple | None = None,
) -> None:
    """Draw a stickman from resolved joints onto ``img`` (RGB)."""
    limb_w = max(3, int(j.head_radius * 0.52 * weight))
    torso_w = max(4, int(j.head_radius * 0.62 * weight))
    head_w = max(3, int(j.head_radius * 0.34))

    if glow_color is not None:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gw = limb_w + 10
        for a, b in (
            (j.pelvis, j.neck), (j.neck, j.elbow_l), (j.elbow_l, j.hand_l),
            (j.neck, j.elbow_r), (j.elbow_r, j.hand_r),
            (j.pelvis, j.knee_l), (j.knee_l, j.foot_l),
            (j.pelvis, j.knee_r), (j.knee_r, j.foot_r),
        ):
            gd.line([a, b], fill=glow_color + (140,), width=gw, joint="curve")
        gd.ellipse(
            [j.head_center[0] - j.head_radius - 6, j.head_center[1] - j.head_radius - 6,
             j.head_center[0] + j.head_radius + 6, j.head_center[1] + j.head_radius + 6],
            outline=glow_color + (160,), width=gw,
        )
        glow = glow.filter(ImageFilter.GaussianBlur(7))
        img.paste(
            Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB"), (0, 0)
        )

    draw = ImageDraw.Draw(img)
    # legs (drawn first, behind torso)
    _seg(draw, j.pelvis, j.knee_l, color, limb_w)
    _seg(draw, j.knee_l, j.foot_l, color, limb_w)
    _seg(draw, j.pelvis, j.knee_r, color, limb_w)
    _seg(draw, j.knee_r, j.foot_r, color, limb_w)
    # arms
    _seg(draw, j.neck, j.elbow_l, color, limb_w)
    _seg(draw, j.elbow_l, j.hand_l, color, limb_w)
    _seg(draw, j.neck, j.elbow_r, color, limb_w)
    _seg(draw, j.elbow_r, j.hand_r, color, limb_w)
    # torso
    _seg(draw, j.pelvis, j.neck, color, torso_w)
    # head
    r = j.head_radius
    draw.ellipse(
        [j.head_center[0] - r, j.head_center[1] - r,
         j.head_center[0] + r, j.head_center[1] + r],
        outline=color, width=head_w,
    )


# ----------------------------------------------------------------------------
# Foreground effects
# ----------------------------------------------------------------------------


def draw_motion_lines(img: Image.Image, j: Joints, theme: Theme, amount: float) -> None:
    """Speed streaks trailing the hands/feet for fast actions."""
    if amount <= 0.01:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    a = int(180 * min(1.0, amount))
    L = j.head_radius * 2.2 * amount
    for p in (j.hand_l, j.hand_r, j.foot_l, j.foot_r):
        draw.line([(p[0] - L, p[1]), (p[0] - L * 0.2, p[1])],
                  fill=theme.accent + (a,), width=max(2, int(j.head_radius * 0.18)))


def draw_keyword(
    img: Image.Image,
    text: str,
    theme: Theme,
    *,
    scale: float = 1.0,
    alpha: float = 1.0,
    y_frac: float = 0.2,
    underline: bool = True,
    accent=None,
) -> None:
    """Big kinetic keyword — chromatic punch + an accent underline bar."""
    if not text or alpha <= 0.02:
        return
    w, h = img.size
    base = int(h * 0.052)
    size = max(12, int(base * scale))
    txt = text.upper()
    accent = accent or theme.accent

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # shrink to fit the frame width (long words / big emphasis keywords)
    font = load_font(size)
    max_w = w * 0.92
    tw = ld.textbbox((0, 0), txt, font=font)[2] - ld.textbbox((0, 0), txt, font=font)[0]
    if tw > max_w:
        size = max(12, int(size * max_w / tw))
        font = load_font(size)
    bbox = ld.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) // 2 - bbox[0]
    y = int(h * y_frac) - bbox[1]

    a = int(255 * max(0.0, min(1.0, alpha)))
    # accent shadow / chromatic offset for punch
    ld.text((x + 5, y + 5), txt, font=font, fill=theme.accent2 + (int(a * 0.55),))
    ld.text((x - 4, y), txt, font=font, fill=accent + (int(a * 0.6),))
    ld.text((x, y), txt, font=font, fill=theme.keyword + (a,))
    if underline:
        bar_y = y + bbox[3] + int(size * 0.18)
        bar_w = min(int(tw * 0.5), int(w * 0.34))
        cx = w // 2
        ld.rectangle([cx - bar_w // 2, bar_y, cx + bar_w // 2, bar_y + max(4, size // 14)],
                     fill=accent + (a,))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def apply_flash(img: Image.Image, theme: Theme, amount: float) -> Image.Image:
    if amount <= 0.01:
        return img
    a = int(200 * min(1.0, amount))
    overlay = Image.new("RGB", img.size, theme.accent)
    return Image.blend(img, overlay, a / 255.0)


# ----------------------------------------------------------------------------
# Polish: shadow, background variants, texture, watermark, progress bar
# ----------------------------------------------------------------------------


def draw_ground_shadow(img: Image.Image, j: Joints, theme: Theme) -> None:
    """Soft elliptical contact shadow under the feet — grounds the figure."""
    feet_y = max(j.foot_l[1], j.foot_r[1])
    if feet_y > img.size[1] * 1.02:           # feet off-frame (close-up) -> skip
        return
    cx = (j.foot_l[0] + j.foot_r[0]) / 2
    span = abs(j.foot_l[0] - j.foot_r[0])
    rw = max(j.head_radius * 1.6, span * 0.9 + j.head_radius)
    rh = j.head_radius * 0.5
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [cx - rw, feet_y - rh, cx + rw, feet_y + rh], fill=(0, 0, 0, 150)
    )
    layer = layer.filter(ImageFilter.GaussianBlur(int(j.head_radius * 0.35)))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_rays(img: Image.Image, theme: Theme, *, energy: float = 0.6, seed: int = 0) -> None:
    """Radial burst lines behind the subject — high-energy 'reveal' background."""
    w, h = img.size
    cx, cy = w * 0.5, h * 0.46
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(26 + 30 * energy)
    n = 24
    for i in range(n):
        ang = (i / n) * 2 * math.pi + (seed % 7) * 0.12
        x2 = cx + math.cos(ang) * w
        y2 = cy + math.sin(ang) * w
        col = theme.accent if i % 2 == 0 else theme.grid
        d.line([(cx, cy), (x2, y2)], fill=col + (a,), width=max(2, int(w * 0.02)))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_dots(img: Image.Image, theme: Theme, *, energy: float = 0.5, seed: int = 0) -> None:
    """Faint drifting dot field — calmer 'thinking' background."""
    import random as _r
    w, h = img.size
    rng = _r.Random(seed)
    d = ImageDraw.Draw(img, "RGBA")
    a = int(40 + 40 * energy)
    step = int(min(w, h) * 0.11)
    rad = max(2, int(min(w, h) * 0.006))
    for gx in range(step // 2, w, step):
        for gy in range(step // 2, h, step):
            ox = rng.randint(-step // 6, step // 6)
            oy = rng.randint(-step // 6, step // 6)
            d.ellipse([gx + ox - rad, gy + oy - rad, gx + ox + rad, gy + oy + rad],
                      fill=theme.grid + (a,))


def draw_midground(img: Image.Image, theme: Theme, *, variant: str = "grid",
                   t: float = 0.0, energy: float = 0.5, seed: int = 0) -> None:
    """Pick a background motif so consecutive shots don't all look identical."""
    if variant == "rays":
        draw_rays(img, theme, energy=energy, seed=seed)
    elif variant == "dots":
        draw_dots(img, theme, energy=energy, seed=seed)
    else:
        draw_grid(img, theme, t=t, energy=energy)


_GRAIN_CACHE: dict[tuple[int, int, int], Image.Image] = {}


def apply_texture(img: Image.Image, *, grain: float = 0.05, scanlines: bool = True,
                  seed: int = 0) -> Image.Image:
    """Cinematic polish: subtle film grain + faint scanlines."""
    w, h = img.size
    if grain > 0:
        key = (w, h, seed % 6)
        noise = _GRAIN_CACHE.get(key)
        if noise is None:
            noise = Image.effect_noise((w, h), 48).convert("RGB")
            _GRAIN_CACHE[key] = noise
        img = Image.blend(img, noise, grain)
    if scanlines:
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for y in range(0, h, 3):
            d.line([(0, y), (w, y)], fill=(0, 0, 0, 22), width=1)
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return img


def draw_watermark(img: Image.Image, handle: str, theme: Theme) -> None:
    """Small brand handle in the bottom-right — recognisability + anti-repost."""
    if not handle:
        return
    w, h = img.size
    font = load_font(max(14, int(h * 0.022)))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bbox = d.textbbox((0, 0), handle, font=font)
    tw = bbox[2] - bbox[0]
    x, y = w - tw - int(w * 0.04), int(h * 0.035)
    d.text((x + 2, y + 2), handle, font=font, fill=(0, 0, 0, 120))
    d.text((x, y), handle, font=font, fill=theme.figure + (150,))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_progress_bar(img: Image.Image, theme: Theme, fraction: float) -> None:
    """Thin bottom progress bar that advances on every cut (watch-to-the-end)."""
    w, h = img.size
    frac = max(0.0, min(1.0, fraction))
    bar_h = max(4, int(h * 0.006))
    y0 = h - bar_h
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, y0, w, h], fill=theme.grid + (140,))
    d.rectangle([0, y0, int(w * frac), h], fill=theme.accent + (255,))
