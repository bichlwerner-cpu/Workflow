"""Pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import audio_mix, captions, footage
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
    music: Path | None = None,
    word_captions: bool = False,
) -> PipelineResult:
    """Auto-script via the configured LLM (Claude or Gemini), then render."""
    cfg.require_script_llm()
    script = generate_script(
        cfg, topic,
        duration_seconds=duration_seconds, style=style, language=language,
    )
    return render_from_script(
        cfg, script,
        fmt=fmt, background=background, music=music,
        word_captions=word_captions, language=language,
    )


def run_from_text(
    cfg: Config,
    text_path: Path,
    *,
    language: str = "de",
    fmt: VideoFormat = VideoFormat.SHORTS,
    background: Path | None = None,
    music: Path | None = None,
    word_captions: bool = True,
) -> PipelineResult:
    """Parse a text file into a script, then render. No LLM required."""
    script = from_text(text_path)
    return render_from_script(
        cfg, script,
        fmt=fmt, background=background, music=music,
        word_captions=word_captions, language=language,
    )


def run_talking_mascot(
    cfg: Config,
    text_path: Path,
    *,
    pose: str = "explain",
    base_expr: str = "neutral",
    language: str = "de",
    captions: bool = True,
    music: Path | None = None,
    out: Path | None = None,
) -> PipelineResult:
    """Script -> voiceover -> Whisper timings -> lip-synced talking-mascot MP4.

    No image API needed: uses the code-defined vector mascot. The voice provider
    follows TTS_PROVIDER (free edge-tts by default, ElevenLabs when configured).
    """
    from . import animate, captions as cap, character as ch

    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out or (out_dir / "talking_mascot.mp4")

    script = from_text(text_path)
    save_script(script, out_dir / "script.json")

    voice_path = out_dir / "voiceover.mp3"
    synthesize(cfg, script_to_voiceover_text(script), voice_path)

    # Word timings come from the clean voice; background music is mixed in after.
    words = cap.transcribe(cfg, voice_path, language=language)
    duration = audio_duration_seconds(voice_path)

    if music is None:
        music = audio_mix.pick_music(cfg.music_dir)
    if music is not None and music.exists():
        audio_path = audio_mix.mix(voice_path, music, out_dir / "audio_mixed.mp3")
    else:
        audio_path = voice_path

    ch.use_palette(cfg.mascot_palette)
    frames = animate.render_talk_frames(
        out_dir / "frames",
        pose=pose, base_expr=base_expr,
        accessory=cfg.mascot_accessory or None,
    )
    segs = animate.viseme_timeline(words, duration)
    animate.write_timeline_json(segs, out_dir / "lipsync.json")

    subtitle = None
    if captions:
        subtitle = cap.write_ass(words, out_dir / "captions.ass", width=1920, height=1080)

    animate.assemble(frames, segs, audio_path, out, subtitle=subtitle, workdir=out_dir)

    return PipelineResult(
        script_path=out_dir / "script.json",
        audio_path=audio_path,
        video_path=out,
        script=script,
    )
