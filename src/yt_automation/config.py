import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    elevenlabs_api_key: str
    anthropic_model: str
    anthropic_effort: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    output_dir: Path

    @classmethod
    def load(cls) -> "Config":
        anthropic = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        eleven = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not anthropic:
            raise RuntimeError("ANTHROPIC_API_KEY missing (set in .env or environment)")
        if not eleven:
            raise RuntimeError("ELEVENLABS_API_KEY missing (set in .env or environment)")

        out = Path(os.environ.get("OUTPUT_DIR", "./out")).resolve()
        out.mkdir(parents=True, exist_ok=True)

        return cls(
            anthropic_api_key=anthropic,
            elevenlabs_api_key=eleven,
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
            anthropic_effort=os.environ.get("ANTHROPIC_EFFORT", "high"),
            elevenlabs_voice_id=os.environ.get(
                "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
            ),
            elevenlabs_model_id=os.environ.get(
                "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
            ),
            output_dir=out,
        )
