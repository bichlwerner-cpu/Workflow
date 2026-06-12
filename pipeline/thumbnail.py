"""Thumbnail generator: 1280x720, high-contrast, consistent channel branding.

Same procedural stickman as the video (drawn extra bold), huge text with the
last word highlighted in the accent color — readable at 120px wide.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .config import Settings
from .models import Script
from .stickman import POSE_LIBRARY, draw_character
from .utils import hex_to_rgb, load_font, mix, text_size

W, H = 1280, 720
SS = 2  # render at 2x, downscale for clean edges

_EXPRESSION_POSE = {
    "shocked": "shocked", "excited": "mind_blown", "happy": "happy",
    "sad": "sad", "angry": "arms_crossed", "thinking": "thinking",
    "confused": "shrug", "smug": "presenting", "curious": "thinking",
    "neutral": "presenting",
}


def render_thumbnail(settings: Settings, script: Script, out_path: Path) -> Path:
    spec = script.outline.thumbnail
    accent = hex_to_rgb(settings.accent)
    cw, ch = W * SS, H * SS
    img = Image.new("RGB", (cw, ch))
    d = ImageDraw.Draw(img)

    # Background: dark vertical gradient tinted by the accent color.
    deep = mix((12, 12, 18), accent, 0.06)
    top = mix((30, 30, 44), accent, 0.10)
    for y in range(ch):
        d.line([(0, y), (cw, y)], fill=mix(top, deep, y / ch))

    # Radial glow behind the character.
    gx, gy = cw * 0.74, ch * 0.55
    glow_steps = 24
    for k in range(glow_steps, 0, -1):
        u = k / glow_steps
        r = ch * 0.55 * u
        d.ellipse([gx - r, gy - r * 0.9, gx + r, gy + r * 0.9],
                  fill=mix(deep, mix(accent, (255, 255, 255), 0.25), (1 - u) * 0.35))

    # The constant main character (first entry in the registry), extra bold.
    main_char = next(iter(settings.characters.values()))
    pose_name = _EXPRESSION_POSE.get(spec.expression, "shocked")
    draw_character(
        d, (cw * 0.74, ch * 0.97), ch * 0.62,
        color=(248, 246, 240), bg_fill=deep,
        pose=POSE_LIBRARY[pose_name],
        emotion=spec.expression, mouth_open=spec.expression in ("shocked", "excited"),
        blink=False, facing=-1, accessory=main_char.accessory,
        hair=main_char.hair, accent=accent,
    )

    # Headline text, auto-sized, last word in accent color.
    words = spec.text.upper().split()
    if not words:
        words = ["WATCH", "THIS"]
    font_path = settings.font_path()
    max_w = int(cw * 0.52)
    size = int(ch * 0.20)
    while size > int(ch * 0.08):
        font = load_font(font_path, size)
        if all(text_size(d, w, font)[0] <= max_w for w in words) and \
                len(words) * size * 1.12 <= ch * 0.82:
            break
        size = int(size * 0.92)
    font = load_font(font_path, size)

    line_h = int(size * 1.12)
    y = (ch - line_h * len(words)) // 2
    x = int(cw * 0.06)
    stroke = max(4, size // 14)
    for i, word in enumerate(words):
        color = accent if i == len(words) - 1 else (250, 250, 250)
        d.text((x, y + i * line_h), word, font=font, fill=color,
               stroke_width=stroke, stroke_fill=(10, 10, 14))

    # Accent bar under the text block.
    bar_y = y + line_h * len(words) + int(size * 0.15)
    d.rectangle([x, bar_y, x + cw * 0.18, bar_y + max(6, size // 12)], fill=accent)

    img = img.resize((W, H), Image.LANCZOS)
    img.save(out_path, "PNG")
    return out_path
