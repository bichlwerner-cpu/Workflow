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
    """Mix voice + music with sidechain ducking — music dips when voice is present."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[1:a]volume={music_volume},aloop=loop=-1:size=2e9[bg];"
        "[bg][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[ducked];"
        "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[mix]"
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
