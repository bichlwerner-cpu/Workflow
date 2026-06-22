"""Filmstrip helpers.

Gemini often returns several poses / rotation steps as ONE wide image (a
"filmstrip": N frames side by side). These helpers slice such a sheet into
individual frames and assemble them into a video — a smooth turnaround
(ping-pong) or a pose slideshow — ready as a background for the pipeline.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image


def slice_strip(
    image_path: Path,
    out_dir: Path,
    n: int | None = None,
    *,
    prefix: str = "frame",
    trim: int = 0,
) -> list[Path]:
    """Split a horizontal filmstrip into `n` equal frames.

    If `n` is None it is guessed assuming roughly square frames (W/H). Pass `n`
    explicitly when you know the frame count (more reliable). `trim` cuts a few
    px off each side of every frame to remove seams between frames.
    """
    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    if n is None:
        n = max(1, round(width / height))
    out_dir.mkdir(parents=True, exist_ok=True)

    frame_w = width / n
    frames: list[Path] = []
    for i in range(n):
        left = round(i * frame_w) + trim
        right = round((i + 1) * frame_w) - trim
        frame = img.crop((left, 0, right, height))
        path = out_dir / f"{prefix}_{i:03d}.png"
        frame.save(path)
        frames.append(path)
    return frames


def frames_to_video(
    frames: list[Path],
    out: Path,
    width: int,
    height: int,
    *,
    fps: int = 12,
    pingpong: bool = True,
    fit: str = "cover",
) -> Path:
    """Assemble ordered frames into a WxH mp4 (e.g. a smooth turnaround).

    `pingpong` plays forward then backward for a seamless loop. `fit` is
    "cover" (fill + crop) or "contain" (fit + pad with brand off-white).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    if not frames:
        raise ValueError("no frames to assemble")

    seq = list(frames)
    if pingpong and len(seq) > 2:
        seq = seq + seq[-2:0:-1]  # forward, then back without repeating endpoints

    out.parent.mkdir(parents=True, exist_ok=True)
    list_file = out.parent / "frames.txt"
    dur = 1.0 / fps
    lines: list[str] = []
    for p in seq:
        lines.append(f"file '{p.resolve().as_posix()}'")
        lines.append(f"duration {dur:.4f}")
    lines.append(f"file '{seq[-1].resolve().as_posix()}'")  # concat needs final repeat
    list_file.write_text("\n".join(lines), encoding="utf-8")

    if fit == "contain":
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0xF4EEE6,setsar=1"
        )
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-vf", vf, "-r", "30", "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


def strip_to_video(
    image_path: Path,
    out: Path,
    width: int,
    height: int,
    *,
    n: int | None = None,
    fps: int = 12,
    pingpong: bool = True,
    fit: str = "cover",
    trim: int = 0,
) -> Path:
    """Convenience: slice a filmstrip sheet and assemble it into one mp4."""
    frames = slice_strip(image_path, out.parent / "frames", n=n, trim=trim)
    return frames_to_video(
        frames, out, width, height, fps=fps, pingpong=pingpong, fit=fit
    )
