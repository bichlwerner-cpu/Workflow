"""Render the final MP4: title-card OR footage background + audio + captions.

Two render paths:
  - render_with_title_card: static rendered title image, simple SRT or ASS overlay
  - render_with_footage:   looping/concatenated footage background, ASS overlay
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from enum import Enum
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .script import VideoScript, script_to_voiceover_text


class VideoFormat(str, Enum):
    LANDSCAPE = "landscape"  # 1920x1080
    SHORTS = "shorts"        # 1080x1920


def dimensions(fmt: VideoFormat) -> tuple[int, int]:
    return (1920, 1080) if fmt is VideoFormat.LANDSCAPE else (1080, 1920)


BG_COLOR = (15, 17, 21)
FG_COLOR = (240, 240, 240)
ACCENT = (255, 122, 89)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def render_title_card(script: VideoScript, out_path: Path, fmt: VideoFormat) -> Path:
    w, h = dimensions(fmt)
    img = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_size = 96 if fmt is VideoFormat.LANDSCAPE else 80
    wrap_width = 28 if fmt is VideoFormat.LANDSCAPE else 16
    title_font = _font(title_size)

    wrapped = textwrap.wrap(script.title, width=wrap_width)
    line_height = int(title_size * 1.15)
    total_height = line_height * len(wrapped)
    y = (h - total_height) // 2 - 60
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=title_font, fill=FG_COLOR)
        y += line_height

    bar_w = 200
    draw.rectangle(
        [(w - bar_w) // 2, y + 30, (w + bar_w) // 2, y + 38],
        fill=ACCENT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def audio_duration_seconds(audio_path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found in PATH")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def write_srt_from_script(
    script: VideoScript, audio_duration: float, out_path: Path
) -> Path:
    """Coarse SRT: one cue per script section, weighted by character count."""
    chunks = [script.hook]
    chunks.extend(s.voiceover for s in script.sections)
    chunks.append(script.call_to_action)
    chunks = [c.strip() for c in chunks if c.strip()]

    total_chars = sum(len(c) for c in chunks) or 1
    cursor = 0.0
    lines: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        share = len(chunk) / total_chars
        end = min(audio_duration, cursor + audio_duration * share)
        lines.append(str(i))
        lines.append(f"{_srt_time(cursor)} --> {_srt_time(end)}")
        lines.append("\n".join(textwrap.wrap(chunk, width=42)) or chunk)
        lines.append("")
        cursor = end

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")


def render_with_title_card(
    script: VideoScript,
    audio_path: Path,
    subtitle_path: Path,
    out_path: Path,
    *,
    workdir: Path,
    fmt: VideoFormat = VideoFormat.LANDSCAPE,
) -> Path:
    _check_ffmpeg()
    title_card = render_title_card(script, workdir / "title.png", fmt)

    if subtitle_path.suffix.lower() == ".ass":
        sub_filter = f"ass={subtitle_path.as_posix()}"
    else:
        sub_filter = (
            f"subtitles='{subtitle_path.as_posix()}':"
            "force_style='FontName=DejaVu Sans,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=3,Outline=2,Shadow=0,MarginV=80'"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(title_card),
        "-i", str(audio_path),
        "-vf", sub_filter,
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-r", "30",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def render_with_footage(
    background_path: Path,
    audio_path: Path,
    subtitle_path: Path,
    out_path: Path,
) -> Path:
    """Composite a prepared background video with audio + ASS captions."""
    _check_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if subtitle_path.suffix.lower() == ".ass":
        vf = f"ass={subtitle_path.as_posix()}"
    else:
        vf = f"subtitles='{subtitle_path.as_posix()}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(background_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


__all__ = [
    "VideoFormat",
    "dimensions",
    "audio_duration_seconds",
    "render_title_card",
    "render_with_title_card",
    "render_with_footage",
    "write_srt_from_script",
    "script_to_voiceover_text",
]
