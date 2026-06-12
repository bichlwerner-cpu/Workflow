"""Final video assembly with ffmpeg.

Raw RGB frames are piped into ffmpeg's stdin while the voice track, optional
background music (sidechain-ducked under the voice) and optional burned-in
subtitles are mixed in. Output: H.264 + AAC mp4, loudness-normalized to
YouTube's -14 LUFS reference.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator, Optional

from .config import ROOT, Settings


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            "ffmpeg not found on PATH. Install it first "
            "(e.g. `sudo apt install ffmpeg` or `brew install ffmpeg`)."
        )


def _ass_filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    p = path.as_posix()
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def encode_video(
    settings: Settings,
    frames: Iterator[bytes],
    voice_wav: Path,
    out_path: Path,
    ass_path: Optional[Path] = None,
    log=print,
) -> Path:
    ensure_ffmpeg()
    W, H, fps = settings.width, settings.height, settings.fps
    crf = int(settings.get("video", "crf", default=19))
    preset = str(settings.get("video", "preset", default="medium"))
    loudnorm = bool(settings.get("audio", "loudnorm", default=True))

    bgm: Optional[Path] = None
    bgm_setting = settings.get("audio", "bgm_path", default="")
    if bgm_setting:
        candidate = Path(bgm_setting)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.exists():
            bgm = candidate

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-framerate", str(fps), "-i", "pipe:0",
        "-i", str(voice_wav),
    ]
    if bgm is not None:
        cmd += ["-stream_loop", "-1", "-i", str(bgm)]

    # --- audio graph ---------------------------------------------------------
    bgm_db = float(settings.get("audio", "bgm_volume_db", default=-24))
    if bgm is not None:
        audio_graph = (
            f"[2:a]aformat=channel_layouts=stereo,volume={bgm_db}dB[bg];"
            f"[1:a]aformat=channel_layouts=stereo,asplit=2[vo][sc];"
            f"[bg][sc]sidechaincompress=threshold=0.04:ratio=10:attack=10:release=500[duck];"
            f"[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]"
        )
        audio_src = "[mix]"
    else:
        audio_graph = "[1:a]aformat=channel_layouts=stereo[mix]"
        audio_src = "[mix]"

    if loudnorm:
        audio_graph += f";{audio_src}loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        audio_src = "[aout]"

    cmd += ["-filter_complex", audio_graph]

    # --- video filters -------------------------------------------------------
    vf = []
    if ass_path is not None:
        vf.append(f"ass='{_ass_filter_path(ass_path)}'")
    vf.append("format=yuv420p")
    cmd += ["-vf", ",".join(vf)]

    cmd += [
        "-map", "0:v", "-map", audio_src,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path),
    ]

    log(f"    [encode] ffmpeg -> {out_path.name}")
    stderr_log = out_path.with_suffix(".ffmpeg.log")
    with open(stderr_log, "wb") as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        assert proc.stdin is not None
        try:
            for frame in frames:
                proc.stdin.write(frame)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
        code = proc.wait()
    if code != 0:
        raise RuntimeError(
            f"ffmpeg failed with exit code {code} — see {stderr_log}"
        )
    stderr_log.unlink(missing_ok=True)
    return out_path
