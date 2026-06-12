"""ElevenLabs voiceover with character-level timestamps and request stitching.

Consistency measures:
  - one fixed voice_id + frozen voice_settings per character (characters.yaml)
  - request stitching: each request passes the last (up to 3) request-ids of
    the SAME voice via `previous_request_ids`, so prosody stays coherent
    across a long video (requires eleven_multilingual_v2 / turbo — NOT v3)
  - previous_text / next_text context for natural sentence flow

The `/with-timestamps` endpoint returns per-character timing which we persist
for (a) word-accurate subtitles and (b) mouth animation synced to the audio.

Synthesized lines are cached by content hash, so re-runs of a video do not
re-bill your ElevenLabs quota.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .config import Settings, VoiceConfig, require_env
from .models import Script

API_BASE = "https://api.elevenlabs.io/v1"
MAX_STITCH_IDS = 3


@dataclass
class VoicedLine:
    """One synthesized narration beat with timing + staging metadata."""

    line_id: str          # e.g. "c02_s001_l03"
    section: str          # "hook" | "chapter:<i>" | "outro"
    chapter_index: int    # -1 hook, 0..n-1 chapters, n outro
    scene_index: int      # scene index within the whole video (global)
    text: str
    actors: List[dict]    # [{character, pose, emotion, action}], 0-2 entries
    prop: str
    camera: str
    wav_path: str
    duration: float
    # parallel arrays from ElevenLabs alignment (relative to line start)
    chars: List[str]
    char_starts: List[float]
    char_ends: List[float]


def _flatten(script: Script):
    """Yield (section, chapter_index, lines-of-scene) in playback order."""
    sections = [("hook", -1, script.hook)]
    for i, ch in enumerate(script.chapters):
        sections.append((f"chapter:{i}", i, ch.scenes))
    sections.append(("outro", len(script.chapters), script.outro))
    global_scene = 0
    for section, ch_idx, scenes in sections:
        for scene in scenes:
            yield section, ch_idx, global_scene, scene
            global_scene += 1


def _pcm_to_wav(pcm: bytes, path: Path, sample_rate: int) -> float:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return len(pcm) / 2 / sample_rate


def _compressed_to_wav(audio: bytes, suffix: str, path: Path, sample_rate: int) -> float:
    """Convert mp3/opus bytes to mono wav via ffmpeg; returns duration."""
    import subprocess
    tmp = path.with_suffix(suffix)
    tmp.write_bytes(audio)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(tmp), "-ac", "1", "-ar", str(sample_rate),
        "-sample_fmt", "s16", str(path),
    ]
    subprocess.run(cmd, check=True)
    tmp.unlink(missing_ok=True)
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


class ElevenLabsClient:
    def __init__(self, settings: Settings):
        self.api_key = require_env("ELEVENLABS_API_KEY")
        self.settings = settings
        self.output_format = settings.get("audio", "output_format", default="pcm_44100")
        self.sample_rate = settings.sample_rate
        self.session = requests.Session()
        self.session.headers.update({"xi-api-key": self.api_key})

    def list_voices(self) -> List[dict]:
        r = self.session.get(f"{API_BASE}/voices", timeout=30)
        r.raise_for_status()
        return r.json().get("voices", [])

    def synthesize_with_timestamps(
        self,
        text: str,
        v: "VoiceConfig",
        previous_request_ids: List[str],
        previous_text: Optional[str],
        next_text: Optional[str],
    ) -> tuple:
        """Returns (audio_bytes, alignment_dict, request_id)."""
        voice_settings: Dict = {
            "stability": v.stability,
            "similarity_boost": v.similarity_boost,
            "style": v.style,
            "use_speaker_boost": v.use_speaker_boost,
        }
        if abs(v.speed - 1.0) > 1e-3:
            voice_settings["speed"] = v.speed
        body: Dict = {
            "text": text,
            "model_id": v.model_id,
            "voice_settings": voice_settings,
        }
        # Per the API docs previous_text is ignored when previous_request_ids
        # is present, so send whichever we have (ids preferred).
        if previous_request_ids:
            body["previous_request_ids"] = previous_request_ids[-MAX_STITCH_IDS:]
        elif previous_text:
            body["previous_text"] = previous_text
        if next_text:
            body["next_text"] = next_text

        url = f"{API_BASE}/text-to-speech/{v.voice_id}/with-timestamps"
        params = {"output_format": self.output_format}

        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                r = self.session.post(url, params=params, json=body, timeout=180)
                if r.status_code in (429, 500, 502, 503):
                    raise requests.HTTPError(f"{r.status_code}: {r.text[:300]}", response=r)
                if r.status_code >= 400:
                    raise SystemExit(
                        f"ElevenLabs error {r.status_code} for voice {v.voice_id}: {r.text[:500]}"
                    )
                payload = r.json()
                audio = base64.b64decode(payload["audio_base64"])
                alignment = payload.get("alignment") or payload.get("normalized_alignment") or {}
                request_id = r.headers.get("request-id", "")
                return audio, alignment, request_id
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                last_err = e
                wait = 2 ** attempt
                print(f"    [voice] transient error ({e}); retrying in {wait}s ...")
                time.sleep(wait)
        raise RuntimeError(f"ElevenLabs request failed after retries: {last_err}")


def synthesize_script(settings: Settings, script: Script, outdir: Path, log=print) -> List[VoicedLine]:
    """Synthesize every narration beat with the narrator voice, in playback order."""
    audio_dir = outdir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / "voice_manifest.json"

    client = ElevenLabsClient(settings)
    narrator = settings.narrator
    if not narrator.voice_id:
        raise SystemExit("No narrator voice configured — set narrator.voice.voice_id "
                         "in config/characters.yaml")
    if "v3" in narrator.model_id:
        log(f"    [voice] WARNING: narrator uses {narrator.model_id} — request stitching "
            f"is unavailable on v3 models; voice consistency may suffer.")

    # Flatten beats with neighbor context (single narrator -> every neighbor counts).
    flat = []
    for section, ch_idx, scene_idx, scene in _flatten(script):
        for li, line in enumerate(scene.lines):
            flat.append((section, ch_idx, scene_idx, li, line))

    chain: List[str] = []  # request-id chain for stitching
    voiced: List[VoicedLine] = []
    n = len(flat)

    for i, (section, ch_idx, scene_idx, li, line) in enumerate(flat):
        line_id = f"c{ch_idx + 1:02d}_s{scene_idx:03d}_l{li:02d}"
        wav_path = audio_dir / f"{line_id}.wav"
        align_path = wav_path.with_suffix(".align.json")

        prev_text = flat[i - 1][4].text if i > 0 else None
        next_text = flat[i + 1][4].text if i + 1 < n else None

        cache_key = hashlib.sha1(json.dumps({
            "voice": narrator.__dict__, "fmt": client.output_format,
            "text": line.text, "prev": prev_text, "next": next_text,
        }, sort_keys=True).encode()).hexdigest()[:16]

        cached = (
            wav_path.exists() and align_path.exists()
            and json.loads(align_path.read_text()).get("cache_key") == cache_key
        )
        if cached:
            align = json.loads(align_path.read_text())
            log(f"    [voice] {i + 1}/{n} {line_id} (cached)")
        else:
            log(f"    [voice] {i + 1}/{n} {line_id} "
                f"\"{line.text[:52]}{'...' if len(line.text) > 52 else ''}\"")
            audio, alignment, request_id = client.synthesize_with_timestamps(
                line.text, narrator, chain, prev_text, next_text,
            )
            if request_id:
                chain.append(request_id)
                del chain[:-MAX_STITCH_IDS]

            if client.output_format.startswith("pcm_"):
                sr = int(client.output_format.split("_")[1])
                duration = _pcm_to_wav(audio, wav_path, sr)
            else:
                suffix = ".mp3" if client.output_format.startswith("mp3") else ".bin"
                duration = _compressed_to_wav(audio, suffix, wav_path, client.sample_rate)

            align = {
                "cache_key": cache_key,
                "duration": duration,
                "chars": alignment.get("characters", []),
                "starts": alignment.get("character_start_times_seconds", []),
                "ends": alignment.get("character_end_times_seconds", []),
            }
            align_path.write_text(json.dumps(align), encoding="utf-8")

        voiced.append(VoicedLine(
            line_id=line_id, section=section, chapter_index=ch_idx,
            scene_index=scene_idx, text=line.text,
            actors=[a.model_dump() for a in line.actors],
            prop=line.prop, camera=line.camera,
            wav_path=str(wav_path), duration=float(align["duration"]),
            chars=align["chars"], char_starts=align["starts"], char_ends=align["ends"],
        ))

    manifest_path.write_text(json.dumps(
        [v.__dict__ for v in voiced], ensure_ascii=False), encoding="utf-8")
    total = sum(v.duration for v in voiced)
    log(f"    [voice] done: {n} lines, {total / 60:.1f} min of speech")
    return voiced


def load_manifest(outdir: Path) -> List[VoicedLine]:
    data = json.loads((outdir / "voice_manifest.json").read_text(encoding="utf-8"))
    return [VoicedLine(**d) for d in data]
