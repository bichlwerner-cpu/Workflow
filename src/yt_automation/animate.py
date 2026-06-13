"""Lip-sync assembler: turn a voiceover into a talking-mascot video.

Flow:
    voiceover.mp3 + word timings (Whisper)  ->  viseme timeline
    viseme PNGs (one per mouth shape)        ->  FFmpeg concat (exact durations)
    + audio (+ optional captions)            ->  talking-mascot .mp4

Only ~7 frames are rendered (one per mouth shape); they're sequenced by duration,
so render cost is independent of video length. The same timeline is written as
JSON so a human editor can reproduce the lip-sync precisely in their own tool.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .captions import Word
from . import character as C


@dataclass(frozen=True)
class VisemeSeg:
    viseme: str
    start: float
    end: float


# Mouth shapes cycled through while a word is being spoken.
_TALK_CYCLE = ["talk_a", "talk_e", "talk_o", "talk_i", "talk_u"]


def viseme_timeline(words: list[Word], total: float, *, chunk: float = 0.09,
                    gap: float = 0.05) -> list[VisemeSeg]:
    """Build (viseme, start, end) segments: mouth moves on words, rests on silence."""
    segs: list[VisemeSeg] = []

    def add(name: str, a: float, b: float) -> None:
        if b > a + 0.001:
            segs.append(VisemeSeg(name, a, b))

    prev_end = 0.0
    ci = 0
    for w in words:
        if w.start > prev_end + gap:
            add("rest", prev_end, w.start)
        a = max(w.start, prev_end)
        while a < w.end - 0.001:
            b = min(w.end, a + chunk)
            add(_TALK_CYCLE[ci % len(_TALK_CYCLE)], a, b)
            ci += 1
            a = b
        prev_end = max(prev_end, w.end)
    if total > prev_end:
        add("rest", prev_end, total)
    return segs


def _gradient(w: int, h: int, top: str, bottom: str):
    from PIL import Image, ImageColor

    tr = ImageColor.getrgb(top)
    br = ImageColor.getrgb(bottom)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        row = (
            int(tr[0] + (br[0] - tr[0]) * t),
            int(tr[1] + (br[1] - tr[1]) * t),
            int(tr[2] + (br[2] - tr[2]) * t),
        )
        for x in range(w):
            px[x, y] = row
    return img


def render_talk_frames(
    out_dir: Path,
    *,
    pose: str = "explain",
    base_expr: str = "neutral",
    accessory: str | None = "glasses",
    width: int = 1920,
    height: int = 1080,
    bg_top: str = "#243049",
    bg_bottom: str = "#141B2A",
    char_scale: float = 0.84,
    y_off: int = 0,
) -> dict[str, Path]:
    """Render one full-frame PNG per mouth shape (background + positioned mascot)."""
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    bg = _gradient(width, height, bg_top, bg_bottom)
    base = C.EXPRESSIONS[base_expr]
    frames: dict[str, Path] = {}
    for vis in C.VISEMES:
        svg = C.build_svg(C.POSES[pose], C.viseme_expression(vis, base), accessory=accessory)
        char_png = out_dir / f"_char_{vis}.png"
        C.rasterize(svg, char_png, width=720, transparent=True)
        char = Image.open(char_png).convert("RGBA")
        th = int(height * char_scale)
        tw = int(char.width * th / char.height)
        char = char.resize((tw, th))
        frame = bg.copy()
        frame.paste(char, ((width - tw) // 2, height - th - y_off), char)
        fp = out_dir / f"frame_{vis}.png"
        frame.save(fp)
        frames[vis] = fp
    return frames


def assemble(
    frames: dict[str, Path],
    segs: list[VisemeSeg],
    audio: Path,
    out: Path,
    *,
    subtitle: Path | None = None,
    fps: int = 30,
    workdir: Path,
) -> Path:
    """Concat the viseme frames by duration and mux audio (+ optional ASS captions)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    if not segs:
        raise ValueError("empty viseme timeline")

    concat = workdir / "lipsync_concat.txt"
    lines: list[str] = []
    for s in segs:
        lines.append(f"file '{frames[s.viseme].resolve().as_posix()}'")
        lines.append(f"duration {s.end - s.start:.3f}")
    lines.append(f"file '{frames[segs[-1].viseme].resolve().as_posix()}'")  # concat demuxer quirk
    concat.write_text("\n".join(lines), encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio),
    ]
    if subtitle is not None:
        cmd += ["-filter_complex", f"[0:v]ass={subtitle.as_posix()},format=yuv420p[v]",
                "-map", "[v]", "-map", "1:a"]
    else:
        cmd += ["-vf", "format=yuv420p", "-map", "0:v", "-map", "1:a"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps), "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def write_timeline_json(segs: list[VisemeSeg], out: Path) -> Path:
    """Export the lip-sync timeline so an editor can reproduce it exactly."""
    out.parent.mkdir(parents=True, exist_ok=True)
    data = [{"viseme": s.viseme, "start": round(s.start, 3), "end": round(s.end, 3)} for s in segs]
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out
