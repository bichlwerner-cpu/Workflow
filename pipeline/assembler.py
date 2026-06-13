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
    sfx_wav: Optional[Path] = None,
    log=print,
) -> Path:
    ensure_ffmpeg()
    W, H, fps = settings.width, settings.height, settings.fps
    crf = int(settings.get("video", "crf", default=19))
    preset = str(settings.get("video", "preset", default="medium"))
    loudnorm = bool(settings.get("audio", "loudnorm", default=True))
    sr = settings.sample_rate

    bgm: Optional[Path] = None
    bgm_setting = settings.get("audio", "bgm_path", default="")
    if bgm_setting:
        candidate = Path(bgm_setting)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.exists():
            bgm = candidate
    if sfx_wav is not None and not Path(sfx_wav).exists():
        sfx_wav = None

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-framerate", str(fps), "-i", "pipe:0",
        "-i", str(voice_wav),
    ]
    bgm_idx = sfx_idx = -1
    nxt = 2
    if bgm is not None:
        cmd += ["-stream_loop", "-1", "-i", str(bgm)]
        bgm_idx, nxt = nxt, nxt + 1
    if sfx_wav is not None:
        cmd += ["-i", str(sfx_wav)]
        sfx_idx, nxt = nxt, nxt + 1

    # --- audio graph ---------------------------------------------------------
    # Voice is the master; music ducks beneath it, SFX sit on top.
    bgm_db = float(settings.get("audio", "bgm_volume_db", default=-22))
    sfx_db = float(settings.get("audio", "sfx_volume_db", default=-3))
    parts: list = []
    if bgm is not None:
        parts.append(f"[1:a]aformat=channel_layouts=stereo,aresample={sr},asplit=2[vo][vokey]")
    else:
        parts.append(f"[1:a]aformat=channel_layouts=stereo,aresample={sr}[vo]")
    mix_labels = ["[vo]"]
    if bgm is not None:
        parts.append(f"[{bgm_idx}:a]aformat=channel_layouts=stereo,aresample={sr},volume={bgm_db}dB[bgv]")
        parts.append("[bgv][vokey]sidechaincompress=threshold=0.04:ratio=10:attack=10:release=500[bgd]")
        mix_labels.append("[bgd]")
    if sfx_wav is not None:
        parts.append(f"[{sfx_idx}:a]aformat=channel_layouts=stereo,aresample={sr},volume={sfx_db}dB[fx]")
        mix_labels.append("[fx]")

    if len(mix_labels) == 1:
        audio_src = mix_labels[0]
    else:
        parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
                     f"duration=first:dropout_transition=0:normalize=0[mix]")
        audio_src = "[mix]"
    audio_graph = ";".join(parts)

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
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
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
