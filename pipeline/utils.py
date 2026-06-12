"""Small shared helpers: colors, fonts, text wrapping, timestamps."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from PIL import ImageDraw, ImageFont

RGB = Tuple[int, int, int]


def hex_to_rgb(value: str) -> RGB:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(a: RGB, b: RGB, u: float) -> RGB:
    u = max(0.0, min(1.0, u))
    return tuple(round(a[i] + (b[i] - a[i]) * u) for i in range(3))  # type: ignore[return-value]


def luminance(c: RGB) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


_FONT_CACHE: dict = {}


def load_font(path: Optional[Path], size: int) -> ImageFont.FreeTypeFont:
    key = (str(path), size)
    if key not in _FONT_CACHE:
        if path is not None and Path(path).exists():
            _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
        else:
            _FONT_CACHE[key] = ImageFont.load_default(size=size)
    return _FONT_CACHE[key]


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for w in words:
        trial = f"{current} {w}".strip()
        if current and text_size(draw, trial, font)[0] > max_width:
            lines.append(current)
            current = w
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def fmt_timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
