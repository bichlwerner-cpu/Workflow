"""End-to-end pipeline orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .script import (
    Style,
    VideoScript,
    generate_script,
    save_script,
    script_to_voiceover_text,
)
from .tts import synthesize
from .video import render_video


@dataclass
class PipelineResult:
    script_path: Path
    audio_path: Path
    video_path: Path
    script: VideoScript


def run_pipeline(
    cfg: Config,
    topic: str,
    *,
    duration_seconds: int = 90,
    style: Style = "explainer",
    language: str = "de",
) -> PipelineResult:
    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)

    script = generate_script(
        cfg,
        topic,
        duration_seconds=duration_seconds,
        style=style,
        language=language,
    )
    script_path = out / "script.json"
    save_script(script, script_path)

    audio_path = out / "voiceover.mp3"
    synthesize(cfg, script_to_voiceover_text(script), audio_path)

    video_path = out / "final.mp4"
    render_video(script, audio_path, video_path, workdir=out)

    return PipelineResult(
        script_path=script_path,
        audio_path=audio_path,
        video_path=video_path,
        script=script,
    )
