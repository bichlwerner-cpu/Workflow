"""ElevenLabs text-to-speech."""

from __future__ import annotations

from pathlib import Path

from elevenlabs.client import ElevenLabs

from .config import Config


def synthesize(cfg: Config, text: str, out_path: Path) -> Path:
    client = ElevenLabs(api_key=cfg.elevenlabs_api_key)

    audio_iter = client.text_to_speech.convert(
        voice_id=cfg.elevenlabs_voice_id,
        model_id=cfg.elevenlabs_model_id,
        text=text,
        output_format="mp3_44100_128",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        for chunk in audio_iter:
            if chunk:
                f.write(chunk)

    return out_path


def list_voices(cfg: Config) -> list[tuple[str, str]]:
    client = ElevenLabs(api_key=cfg.elevenlabs_api_key)
    voices = client.voices.get_all()
    return [(v.voice_id, v.name) for v in voices.voices]
