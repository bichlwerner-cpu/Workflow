"""Mix voiceover with background music using FFmpeg sidechain ducking."""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def pick_music(music_dir: Path) -> Path | None:
    if not music_dir.exists():
        return None
    candidates = [p for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTS]
    if not candidates:
        return None
    return random.choice(candidates)


def mix(
    voice_path: Path,
    music_path: Path,
    out_path: Path,
    *,
    music_volume: float = 0.25,
) -> Path:
    """Mix voice + music with sidechain ducking and YouTube-target loudnorm.

    Music is looped, ducked when the voice is present, then the final mix is
    loudness-normalized to I=-14 LUFS / TP=-1.5 dB (YouTube playback target).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[1:a]volume={music_volume},aloop=loop=-1:size=2e9[bg];"
        "[bg][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[ducked];"
        "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[premix];"
        "[premix]loudnorm=I=-14:TP=-1.5:LRA=11[mix]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_path),
        "-i",
        str(music_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[mix]",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def normalize(voice_path: Path, out_path: Path) -> Path:
    """Loudnorm-only pass for cases without background music."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path
