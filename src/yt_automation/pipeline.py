"""Pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import audio_mix, captions, footage, stickman as stickman_mod
from .config import Config
from .script import (
    Style,
    VideoScript,
    from_text,
    generate_script,
    save_script,
    script_to_voiceover_text,
)
from .tts import synthesize
from .video import (
    VideoFormat,
    audio_duration_seconds,
    dimensions,
    render_with_footage,
    render_with_title_card,
    write_srt_from_script,
)


@dataclass
class PipelineResult:
    script_path: Path
    audio_path: Path
    video_path: Path
    script: VideoScript


def render_from_script(
    cfg: Config,
    script: VideoScript,
    *,
    fmt: VideoFormat = VideoFormat.LANDSCAPE,
    background: Path | None = None,
    stickman: bool = False,
    music: Path | None = None,
    word_captions: bool = False,
    language: str = "de",
) -> PipelineResult:
    """Take a VideoScript and produce the final MP4."""
    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)

    script_path = out / "script.json"
    save_script(script, script_path)

    voice_path = out / "voiceover.mp3"
    synthesize(cfg, script_to_voiceover_text(script), voice_path)

    if music is None:
        music = audio_mix.pick_music(cfg.music_dir)
    if music is not None and music.exists():
        mixed_path = out / "audio_mixed.mp3"
        audio_path = audio_mix.mix(voice_path, music, mixed_path)
    else:
        audio_path = voice_path

    duration = audio_duration_seconds(audio_path)

    if word_captions:
        words = captions.transcribe(cfg, audio_path, language=language)
        w, h = dimensions(fmt)
        subtitle_path = captions.write_ass(
            words, out / "captions.ass", width=w, height=h,
        )
    else:
        subtitle_path = write_srt_from_script(script, duration, out / "subtitles.srt")

    video_path = out / "final.mp4"
    if background is not None:
        w, h = dimensions(fmt)
        bg = footage.prepare_background(background, duration, w, h, workdir=out)
        render_with_footage(bg, audio_path, subtitle_path, video_path)
    elif stickman:
        w, h = dimensions(fmt)
        spec = stickman_mod.CharacterSpec.load_or_create(cfg.character_file)
        bg = stickman_mod.render_background_video(
            spec, duration, w, h, out / "background.mp4",
        )
        render_with_footage(bg, audio_path, subtitle_path, video_path)
    else:
        render_with_title_card(
            script, audio_path, subtitle_path, video_path,
            workdir=out, fmt=fmt,
        )

    return PipelineResult(
        script_path=script_path,
        audio_path=audio_path,
        video_path=video_path,
        script=script,
    )


def run_pipeline(
    cfg: Config,
    topic: str,
    *,
    duration_seconds: int = 90,
    style: Style = "explainer",
    language: str = "de",
    fmt: VideoFormat = VideoFormat.LANDSCAPE,
    background: Path | None = None,
    stickman: bool = False,
    music: Path | None = None,
    word_captions: bool = False,
) -> PipelineResult:
    """Auto-script via Claude, then render."""
    cfg.require_anthropic()
    script = generate_script(
        cfg, topic,
        duration_seconds=duration_seconds, style=style, language=language,
    )
    return render_from_script(
        cfg, script,
        fmt=fmt, background=background, stickman=stickman, music=music,
        word_captions=word_captions, language=language,
    )


def run_from_text(
    cfg: Config,
    text_path: Path,
    *,
    language: str = "de",
    fmt: VideoFormat = VideoFormat.SHORTS,
    background: Path | None = None,
    stickman: bool = False,
    music: Path | None = None,
    word_captions: bool = True,
) -> PipelineResult:
    """Parse a text file into a script, then render. No LLM required."""
    script = from_text(text_path)
    return render_from_script(
        cfg, script,
        fmt=fmt, background=background, stickman=stickman, music=music,
        word_captions=word_captions, language=language,
    )
