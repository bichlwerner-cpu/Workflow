"""Footage helpers: download via yt-dlp, clip via FFmpeg, prepare backgrounds.

NOTE: Downloading copyrighted material from YouTube violates YouTube's Terms of
Service, and reusing copyrighted footage in your own uploads infringes on the
rights holders. Use this only for content you have a license for, public-domain
material, Creative Commons sources, or fair-use commentary in jurisdictions
where that applies. You are responsible for the videos you publish.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yt_dlp

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def download(url: str, out_dir: Path, *, max_height: int = 1080) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]"
        ),
        "outtmpl": str(out_dir / "%(id)s_%(title).80s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if path.suffix != ".mp4":
        merged = path.with_suffix(".mp4")
        if merged.exists():
            path = merged
    return path


def clip(
    source: Path,
    start: str,
    end: str,
    out_path: Path,
    *,
    reencode: bool = True,
) -> Path:
    """Cut a clip. `start` / `end` accept HH:MM:SS or seconds.

    `reencode=True` gives frame-accurate cuts; False does fast stream-copy
    that snaps to keyframes (faster, but cuts may be off by 1-2 seconds).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(source)]
    if reencode:
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
        ]
    else:
        cmd += ["-c", "copy"]
    cmd.append(str(out_path))
    subprocess.run(cmd, check=True)
    return out_path


def list_footage(footage_dir: Path) -> list[Path]:
    if not footage_dir.exists():
        return []
    return sorted(p for p in footage_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS)


def _still_to_clip(
    image: Path, out: Path, width: int, height: int, *, duration: float = 3.0, fps: int = 30
) -> Path:
    """Turn a still image (e.g. a FORGE pose) into a static WxH video segment."""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-t", f"{duration:.3f}", "-i", str(image),
            "-vf", vf, "-r", str(fps), "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


def _concat(clips: list[Path], workdir: Path) -> Path:
    """Concat same-spec clips via the FFmpeg concat demuxer."""
    list_file = workdir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in clips),
        encoding="utf-8",
    )
    out = workdir / "concat.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True,
    )
    return out


def _resolve_source(source: Path, width: int, height: int, workdir: Path) -> Path:
    """Normalize a footage source to a single video clip.

    Accepts a video, a still image, or a directory of either. A directory of
    images becomes a slideshow (each still ~3s, cycled); a single image becomes
    one static segment. Videos are used as-is (first match / concat).
    """
    if source.is_dir():
        vids = sorted(p for p in source.iterdir() if p.suffix.lower() in VIDEO_EXTS)
        if vids:
            return vids[0] if len(vids) == 1 else _concat(vids, workdir)
        imgs = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if imgs:
            clips = [
                _still_to_clip(img, workdir / f"still_{i:03d}.mp4", width, height)
                for i, img in enumerate(imgs)
            ]
            return clips[0] if len(clips) == 1 else _concat(clips, workdir)
        raise ValueError(f"No video or image files in {source}")
    if source.suffix.lower() in IMAGE_EXTS:
        return _still_to_clip(source, workdir / "still.mp4", width, height)
    return source


def prepare_background(
    source: Path,
    target_duration: float,
    width: int,
    height: int,
    workdir: Path,
) -> Path:
    """Loop/concat `source` to reach `target_duration`, scaled+cropped to WxH.

    `source` may be a video, a still image (PNG/JPG/WEBP), or a directory of
    either. Images become static WxH segments — this is how generated FORGE pose
    art turns into a video background. Strips audio (we use the voiceover).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    workdir.mkdir(parents=True, exist_ok=True)

    source = _resolve_source(source, width, height, workdir)

    out = workdir / "background.mp4"
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(source),
            "-t", f"{target_duration:.3f}",
            "-vf", vf,
            "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            str(out),
        ],
        check=True,
    )
    return out
