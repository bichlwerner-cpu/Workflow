"""Text-to-speech with switchable provider (edge-tts default, ElevenLabs optional)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass(frozen=True)
class WordMark:
    """A spoken word with its time window (seconds), relative to the clip start."""

    text: str
    start: float
    end: float


def synthesize(cfg: Config, text: str, out_path: Path) -> Path:
    """Render `text` to `out_path` (mp3) using the configured provider."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.tts_provider == "elevenlabs":
        return _synthesize_elevenlabs(cfg, text, out_path)
    if cfg.tts_provider == "local":
        return _synthesize_local(cfg, text, out_path)
    return _synthesize_edge(cfg, text, out_path)


def synthesize_with_marks(
    cfg: Config, text: str, out_path: Path
) -> tuple[Path, list[WordMark]]:
    """Like :func:`synthesize` but also returns word-level timings.

    edge-tts streams exact ``WordBoundary`` events, so we get word timings for
    free (no Whisper needed). ElevenLabs has no boundary stream here, so its
    marks come back empty and callers should fall back to even distribution.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.tts_provider == "elevenlabs":
        _synthesize_elevenlabs(cfg, text, out_path)
        return out_path, []
    if cfg.tts_provider == "local":
        _synthesize_local(cfg, text, out_path)
        return out_path, []
    return _synthesize_edge_marks(cfg, text, out_path)


def list_voices(cfg: Config, *, language: str | None = None) -> list[tuple[str, str]]:
    """Return [(voice_id, label), ...] for the active provider."""
    if cfg.tts_provider == "elevenlabs":
        return _list_voices_elevenlabs(cfg)
    if cfg.tts_provider == "local":
        return _list_voices_local(language=language)
    return _list_voices_edge(language=language)


def _list_voices_local(*, language: str | None = None) -> list[tuple[str, str]]:
    import re
    import shutil
    import subprocess

    if not shutil.which("espeak-ng"):
        return []
    out = subprocess.run(
        ["espeak-ng", "--voices"], capture_output=True, text=True, check=True
    ).stdout
    items: list[tuple[str, str]] = []
    for line in out.splitlines()[1:]:
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 4:
            continue
        lang_code, voice_id, name = parts[1], parts[3], " ".join(parts[4:]) or parts[3]
        if language and not lang_code.lower().startswith(language.lower()):
            continue
        items.append((voice_id, f"{lang_code} · {name}"))
    items.sort()
    return items


# ---------- edge-tts (free, default) ----------


def _synthesize_edge(cfg: Config, text: str, out_path: Path) -> Path:
    import edge_tts

    async def _run() -> None:
        comm = edge_tts.Communicate(text=text, voice=cfg.edge_voice)
        await comm.save(str(out_path))

    asyncio.run(_run())
    return out_path


def _synthesize_edge_marks(
    cfg: Config, text: str, out_path: Path
) -> tuple[Path, list[WordMark]]:
    import edge_tts

    marks: list[WordMark] = []

    async def _run() -> None:
        comm = edge_tts.Communicate(text=text, voice=cfg.edge_voice)
        with out_path.open("wb") as f:
            async for chunk in comm.stream():
                ctype = chunk.get("type")
                if ctype == "audio":
                    f.write(chunk["data"])
                elif ctype == "WordBoundary":
                    start = chunk["offset"] / 1e7          # 100ns ticks -> s
                    dur = chunk["duration"] / 1e7
                    marks.append(
                        WordMark(text=str(chunk["text"]), start=start, end=start + dur)
                    )

    asyncio.run(_run())
    return out_path, marks


def _list_voices_edge(*, language: str | None = None) -> list[tuple[str, str]]:
    import edge_tts

    async def _run() -> list[dict]:
        return await edge_tts.list_voices()

    voices = asyncio.run(_run())
    items: list[tuple[str, str]] = []
    for v in voices:
        short = v.get("ShortName", "")
        locale = v.get("Locale", "")
        gender = v.get("Gender", "")
        if language and not locale.lower().startswith(language.lower()):
            continue
        items.append((short, f"{locale} · {gender}"))
    items.sort()
    return items


# ---------- local espeak-ng (free, fully offline) ----------


def _synthesize_local(cfg: Config, text: str, out_path: Path) -> Path:
    """Offline TTS via espeak-ng. No network, no API key. Robotic but reliable.

    Produces a WAV with espeak-ng, then transcodes to the requested container
    (mp3) with FFmpeg so the rest of the pipeline is provider-agnostic.
    """
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("espeak-ng"):
        raise RuntimeError(
            "TTS_PROVIDER=local needs the 'espeak-ng' binary on PATH "
            "(install: apt-get install espeak-ng / brew install espeak-ng)."
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        subprocess.run(
            ["espeak-ng", "-v", cfg.local_voice, "-s", str(cfg.local_rate),
             "-w", str(wav_path), text],
            check=True, capture_output=True,
        )
        if out_path.suffix.lower() == ".wav":
            shutil.move(str(wav_path), str(out_path))
        else:
            if not shutil.which("ffmpeg"):
                raise RuntimeError("ffmpeg not found in PATH (needed to encode mp3)")
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav_path),
                 "-c:a", "libmp3lame", "-q:a", "3", str(out_path)],
                check=True, capture_output=True,
            )
    finally:
        wav_path.unlink(missing_ok=True)
    return out_path


# ---------- ElevenLabs (paid) ----------


def _synthesize_elevenlabs(cfg: Config, text: str, out_path: Path) -> Path:
    cfg.require_elevenlabs()
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=cfg.elevenlabs_api_key)
    audio_iter = client.text_to_speech.convert(
        voice_id=cfg.elevenlabs_voice_id,
        model_id=cfg.elevenlabs_model_id,
        text=text,
        output_format="mp3_44100_128",
    )
    with out_path.open("wb") as f:
        for chunk in audio_iter:
            if chunk:
                f.write(chunk)
    return out_path


def _list_voices_elevenlabs(cfg: Config) -> list[tuple[str, str]]:
    cfg.require_elevenlabs()
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=cfg.elevenlabs_api_key)
    voices = client.voices.get_all()
    return [(v.voice_id, v.name) for v in voices.voices]
