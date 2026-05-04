"""Text-to-speech with switchable provider (edge-tts default, ElevenLabs optional)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .config import Config


def synthesize(cfg: Config, text: str, out_path: Path) -> Path:
    """Render `text` to `out_path` (mp3) using the configured provider."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.tts_provider == "elevenlabs":
        return _synthesize_elevenlabs(cfg, text, out_path)
    return _synthesize_edge(cfg, text, out_path)


def list_voices(cfg: Config, *, language: str | None = None) -> list[tuple[str, str]]:
    """Return [(voice_id, label), ...] for the active provider."""
    if cfg.tts_provider == "elevenlabs":
        return _list_voices_elevenlabs(cfg)
    return _list_voices_edge(language=language)


# ---------- edge-tts (free, default) ----------


def _synthesize_edge(cfg: Config, text: str, out_path: Path) -> Path:
    import edge_tts

    async def _run() -> None:
        comm = edge_tts.Communicate(text=text, voice=cfg.edge_voice)
        await comm.save(str(out_path))

    asyncio.run(_run())
    return out_path


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
