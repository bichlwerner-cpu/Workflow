"""Footage helpers: download via yt-dlp, clip via FFmpeg, prepare backgrounds.

NOTE: Downloading copyrighted material from YouTube violates YouTube's Terms of
Service, and reusing copyrighted footage in your own uploads infringes on the
rights holders. Use this only for content you have a license for, public-domain
material, Creative Commons sources, or fair-use commentary in jurisdictions
where that applies. You are responsible for the videos you publish.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

import yt_dlp

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


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


def prepare_background(
    source: Path,
    target_duration: float,
    width: int,
    height: int,
    workdir: Path,
) -> Path:
    """Loop or concat `source` to reach `target_duration`, scaled+cropped to WxH.

    Strips audio (we use the synthesized voiceover instead).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    workdir.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        clips = [p for p in source.iterdir() if p.suffix.lower() in VIDEO_EXTS]
        if not clips:
            raise ValueError(f"No video files in {source}")
        if len(clips) == 1:
            source = clips[0]
        else:
            list_file = workdir / "concat.txt"
            list_file.write_text(
                "\n".join(f"file '{p.resolve().as_posix()}'" for p in sorted(clips)),
                encoding="utf-8",
            )
            concat_out = workdir / "concat.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-an", "-pix_fmt", "yuv420p",
                    str(concat_out),
                ],
                check=True,
            )
            source = concat_out

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


def prepare_fast_cuts(
    clips: list[Path],
    target_duration: float,
    width: int,
    height: int,
    workdir: Path,
    *,
    cut_min: float = 1.5,
    cut_max: float = 2.5,
    seed: int | None = None,
) -> Path:
    """Build a background by stitching short random slices of `clips`.

    Optimized for retention: a new visual every cut_min..cut_max seconds.
    Each slice is scaled+cropped to WxH; audio stripped; output concat.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    if not clips:
        raise ValueError("prepare_fast_cuts requires at least one clip")
    workdir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps=30"
    )

    slices_dir = workdir / "slices"
    slices_dir.mkdir(exist_ok=True)
    for old in slices_dir.glob("*.mp4"):
        old.unlink()

    slice_paths: list[Path] = []
    elapsed = 0.0
    idx = 0
    pool = list(clips)
    rng.shuffle(pool)
    pool_pos = 0

    while elapsed < target_duration:
        clip = pool[pool_pos % len(pool)]
        pool_pos += 1

        clip_duration = _probe_duration(clip)
        if clip_duration <= 0.5:
            continue

        slice_len = rng.uniform(cut_min, cut_max)
        slice_len = min(slice_len, target_duration - elapsed, clip_duration)
        if slice_len < 0.4:
            break

        max_start = max(0.0, clip_duration - slice_len)
        start = rng.uniform(0.0, max_start) if max_start > 0 else 0.0

        out = slices_dir / f"slice_{idx:04d}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}",
                "-t", f"{slice_len:.3f}",
                "-i", str(clip),
                "-vf", vf,
                "-an",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        slice_paths.append(out)
        elapsed += slice_len
        idx += 1

    list_file = workdir / "fastcut_concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in slice_paths),
        encoding="utf-8",
    )
    out_path = workdir / "background.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def _probe_duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0
