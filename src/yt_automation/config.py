import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


TTSProvider = Literal["edge", "elevenlabs", "local"]


@dataclass(frozen=True)
class Config:
    # TTS
    tts_provider: TTSProvider
    edge_voice: str
    elevenlabs_api_key: str  # may be empty when not used
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    local_voice: str         # espeak-ng voice (offline provider)
    local_rate: int          # espeak-ng words-per-minute

    # LLM (only required for auto-script commands)
    anthropic_api_key: str  # may be empty
    anthropic_model: str
    anthropic_effort: str

    # Whisper
    whisper_model: str

    # Paths
    output_dir: Path
    music_dir: Path
    footage_dir: Path

    @classmethod
    def load(cls) -> "Config":
        out = Path(os.environ.get("OUTPUT_DIR", "./out")).resolve()
        out.mkdir(parents=True, exist_ok=True)

        music_dir = Path(os.environ.get("MUSIC_DIR", "./assets/music")).resolve()
        footage_dir = Path(os.environ.get("FOOTAGE_DIR", "./assets/footage")).resolve()
        music_dir.mkdir(parents=True, exist_ok=True)
        footage_dir.mkdir(parents=True, exist_ok=True)

        provider = os.environ.get("TTS_PROVIDER", "edge").strip().lower()
        if provider not in ("edge", "elevenlabs", "local"):
            raise RuntimeError(
                f"TTS_PROVIDER must be 'edge', 'elevenlabs' or 'local', got '{provider}'"
            )

        return cls(
            tts_provider=provider,  # type: ignore[arg-type]
            edge_voice=os.environ.get("EDGE_VOICE", "de-DE-KatjaNeural"),
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", "").strip(),
            elevenlabs_voice_id=os.environ.get(
                "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
            ),
            elevenlabs_model_id=os.environ.get(
                "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
            ),
            local_voice=os.environ.get("LOCAL_VOICE", "en-us"),
            local_rate=int(os.environ.get("LOCAL_RATE", "165")),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
            anthropic_effort=os.environ.get("ANTHROPIC_EFFORT", "high"),
            whisper_model=os.environ.get("WHISPER_MODEL", "base"),
            output_dir=out,
            music_dir=music_dir,
            footage_dir=footage_dir,
        )

    def require_anthropic(self) -> None:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "This command needs an Anthropic API key. Either set "
                "ANTHROPIC_API_KEY in .env, or use `yt-automation from-text` "
                "to skip the auto-script step."
            )

    def require_elevenlabs(self) -> None:
        if not self.elevenlabs_api_key:
            raise RuntimeError(
                "TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is empty. "
                "Either fill in ELEVENLABS_API_KEY in .env, or set "
                "TTS_PROVIDER=edge for the free Microsoft voices."
            )
