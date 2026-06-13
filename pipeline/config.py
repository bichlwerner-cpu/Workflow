"""Configuration loading: settings.yaml, characters.yaml, .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines); never overrides real env vars."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class VoiceConfig:
    voice_id: str
    model_id: str = "eleven_multilingual_v2"
    stability: float = 0.55
    similarity_boost: float = 0.80
    style: float = 0.30
    use_speaker_boost: bool = True
    speed: float = 1.0  # 0.7-1.2; ~1.07 keeps long-form videos feeling brisk


@dataclass
class CharacterConfig:
    key: str
    display_name: str
    persona: str
    color: str = "#1B1B1F"
    accessory: str = "none"  # none | glasses | hat | bowtie | mustache
    hair: str = "none"       # none | spiky | bob | curly
    voice: VoiceConfig = field(default_factory=lambda: VoiceConfig(voice_id=""))


@dataclass
class Settings:
    raw: Dict[str, Any]
    characters: Dict[str, CharacterConfig]
    narrator: VoiceConfig = field(default_factory=lambda: VoiceConfig(voice_id=""))

    # --- convenience accessors -------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.raw
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    @property
    def width(self) -> int:
        return int(self.get("video", "width", default=1920))

    @property
    def height(self) -> int:
        return int(self.get("video", "height", default=1080))

    @property
    def fps(self) -> int:
        return int(self.get("video", "fps", default=30))

    @property
    def sample_rate(self) -> int:
        return int(self.get("audio", "sample_rate", default=44100))

    @property
    def accent(self) -> str:
        return str(self.get("style", "accent", default="#FFD60A"))

    def font_path(self) -> Optional[Path]:
        for candidate in self.get("fonts", default=[]) or []:
            p = Path(candidate)
            if not p.is_absolute():
                p = ROOT / p
            if p.exists():
                return p
        return None


DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "en",
    "video": {
        "width": 1920, "height": 1080, "fps": 30, "supersample": 2.0,
        "crf": 19, "preset": "medium", "target_minutes": 5, "words_per_minute": 170,
    },
    "audio": {
        "output_format": "mp3_44100_128", "sample_rate": 44100,
        "line_gap": 0.06, "scene_gap": 0.22, "chapter_gap": 0.45,
        "lead_in": 0.3, "tail": 1.3,
        "bgm_path": "assets/music/bgm.wav", "bgm_volume_db": -22,
        "sfx": True, "sfx_volume_db": -3, "loudnorm": True,
    },
    "subtitles": {
        "burn_in": True, "karaoke": True, "font_name": "DejaVu Sans",
        "font_size": 78, "margin_v": 110, "outline": 6, "shadow": 3,
        "max_words_per_cue": 4, "max_chars_per_cue": 30,
    },
    "style": {"accent": "#FFD60A", "progress_bar": True, "chapter_cards": True, "watermark": ""},
    "fonts": [],
    "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "max_tokens": 16000},
    "youtube": {
        "category_id": "27", "privacy_status": "private",
        "made_for_kids": False, "description_footer": "",
    },
}


def load_settings(
    settings_path: Path = CONFIG_DIR / "settings.yaml",
    characters_path: Path = CONFIG_DIR / "characters.yaml",
) -> Settings:
    load_dotenv()

    raw: Dict[str, Any] = {}
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    raw = _deep_merge(DEFAULT_SETTINGS, raw)

    if not characters_path.exists():
        raise FileNotFoundError(f"Character registry missing: {characters_path}")
    chars_raw = yaml.safe_load(characters_path.read_text(encoding="utf-8")) or {}

    def parse_voice(voice_raw: Dict[str, Any]) -> VoiceConfig:
        return VoiceConfig(
            voice_id=str(voice_raw.get("voice_id", "")),
            model_id=voice_raw.get("model_id", "eleven_multilingual_v2"),
            stability=float(voice_raw.get("stability", 0.55)),
            similarity_boost=float(voice_raw.get("similarity_boost", 0.80)),
            style=float(voice_raw.get("style", 0.30)),
            use_speaker_boost=bool(voice_raw.get("use_speaker_boost", True)),
            speed=float(voice_raw.get("speed", 1.0)),
        )

    characters: Dict[str, CharacterConfig] = {}
    for key, c in (chars_raw.get("characters") or {}).items():
        characters[key] = CharacterConfig(
            key=key,
            display_name=c.get("display_name", key.title()),
            persona=str(c.get("persona", "")).strip(),
            color=c.get("color", "#1B1B1F"),
            accessory=c.get("accessory", "none") or "none",
            hair=c.get("hair", "none") or "none",
            voice=parse_voice(c.get("voice") or {}),
        )
    if not characters:
        raise ValueError("config/characters.yaml defines no characters.")

    narrator = parse_voice((chars_raw.get("narrator") or {}).get("voice") or {})
    return Settings(raw=raw, characters=characters, narrator=narrator)


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "video"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing environment variable {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value
