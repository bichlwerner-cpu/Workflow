"""Render a 1080p MP4 from a title card, voiceover MP3 and SRT subtitles via FFmpeg."""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .script import VideoScript, script_to_voiceover_text

WIDTH, HEIGHT = 1920, 1080
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


def render_title_card(script: VideoScript, out_path: Path) -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _font(96)
    subtitle_font = _font(40)

    wrapped = textwrap.wrap(script.title, width=28)
    line_height = 110
    total_height = line_height * len(wrapped)
    y = (HEIGHT - total_height) // 2 - 60
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=title_font, fill=FG_COLOR)
        y += line_height

    bar_w = 200
    draw.rectangle(
        [(WIDTH - bar_w) // 2, y + 30, (WIDTH + bar_w) // 2, y + 38],
        fill=ACCENT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _audio_duration_seconds(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def write_srt(script: VideoScript, audio_duration: float, out_path: Path) -> Path:
    """Distribute spoken text across audio duration, weighted by character count."""
    chunks = [script.hook]
    chunks.extend(s.voiceover for s in script.sections)
    chunks.append(script.call_to_action)
    chunks = [c.strip() for c in chunks if c.strip()]

    total_chars = sum(len(c) for c in chunks) or 1
    cursor = 0.0
    lines: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        share = len(chunk) / total_chars
        duration = audio_duration * share
        start = cursor
        end = min(audio_duration, cursor + duration)
        cursor = end
        lines.append(str(i))
        lines.append(f"{_srt_time(start)} --> {_srt_time(end)}")
        lines.append(_wrap_subtitle(chunk))
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap_subtitle(text: str, width: int = 42) -> str:
    return "\n".join(textwrap.wrap(text, width=width)) or text


def render_video(
    script: VideoScript,
    audio_path: Path,
    out_path: Path,
    *,
    workdir: Path,
) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found in PATH")

    title_card = render_title_card(script, workdir / "title.png")
    duration = _audio_duration_seconds(audio_path)
    srt_path = write_srt(script, duration, workdir / "subtitles.srt")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    subtitles_filter = (
        f"subtitles='{srt_path.as_posix()}':"
        "force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=80'"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(title_card),
        "-i",
        str(audio_path),
        "-vf",
        subtitles_filter,
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-r",
        "30",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


__all__ = [
    "render_title_card",
    "render_video",
    "write_srt",
    "script_to_voiceover_text",
]
