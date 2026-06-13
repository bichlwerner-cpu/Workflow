import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


TTSProvider = Literal["edge", "elevenlabs"]
ScriptProvider = Literal["claude", "gemini"]


@dataclass(frozen=True)
class Config:
    # TTS
    tts_provider: TTSProvider
    edge_voice: str
    elevenlabs_api_key: str  # may be empty when not used
    elevenlabs_voice_id: str
    elevenlabs_model_id: str

    # Script LLM (only required for auto-script commands)
    script_provider: ScriptProvider
    anthropic_api_key: str  # may be empty
    anthropic_model: str
    anthropic_effort: str
    gemini_api_key: str  # may be empty
    gemini_model: str
    gemini_image_model: str  # Nano Banana (Pro) image model

    # Whisper
    whisper_model: str

    # Mascot brand
    mascot_palette: str
    mascot_accessory: str  # "" = none

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
        if provider not in ("edge", "elevenlabs"):
            raise RuntimeError(
                f"TTS_PROVIDER must be 'edge' or 'elevenlabs', got '{provider}'"
            )

        script_provider = os.environ.get("SCRIPT_PROVIDER", "claude").strip().lower()
        if script_provider not in ("claude", "gemini"):
            raise RuntimeError(
                f"SCRIPT_PROVIDER must be 'claude' or 'gemini', got '{script_provider}'"
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
            script_provider=script_provider,  # type: ignore[arg-type]
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
            anthropic_effort=os.environ.get("ANTHROPIC_EFFORT", "high"),
            gemini_api_key=(
                os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY", "")
            ).strip(),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_image_model=os.environ.get(
                "GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview"
            ),
            whisper_model=os.environ.get("WHISPER_MODEL", "base"),
            mascot_palette=os.environ.get("MASCOT_PALETTE", "purple").strip().lower(),
            mascot_accessory=os.environ.get("MASCOT_ACCESSORY", "glasses").strip().lower(),
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

    def require_gemini(self) -> None:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is empty. Set GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "as an environment secret / in .env. The same key powers both the "
                "Gemini script generator and the Nano Banana image generator."
            )

    def require_script_llm(self) -> None:
        if self.script_provider == "gemini":
            self.require_gemini()
        else:
            self.require_anthropic()

    def require_elevenlabs(self) -> None:
        if not self.elevenlabs_api_key:
            raise RuntimeError(
                "TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is empty. "
                "Either fill in ELEVENLABS_API_KEY in .env, or set "
                "TTS_PROVIDER=edge for the free Microsoft voices."
            )
