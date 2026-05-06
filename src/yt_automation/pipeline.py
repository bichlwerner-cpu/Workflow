"""Pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import audio_mix, captions, footage, scene_pack
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
    upload_url: str | None = None


def _resolve_clips(background: Path) -> list[Path]:
    """Return a list of video clips for fast-cut backgrounds.

    Accepts: a single video file, a directory of clips, or a scene-pack
    directory (one with manifest.json, in which case the manifest order
    and motion-score is preserved).
    """
    if background.is_file():
        return [background]
    if not background.is_dir():
        raise FileNotFoundError(background)

    manifest = background / "manifest.json"
    if manifest.exists():
        return [s.path for s in scene_pack.load_pack(background)]

    clips = [
        p for p in background.iterdir()
        if p.suffix.lower() in footage.VIDEO_EXTS
    ]
    if not clips:
        raise ValueError(f"No video files in {background}")
    return sorted(clips)


def render_from_script(
    cfg: Config,
    script: VideoScript,
    *,
    fmt: VideoFormat = VideoFormat.LANDSCAPE,
    background: Path | None = None,
    music: Path | None = None,
    word_captions: bool = False,
    language: str = "de",
    fast_cuts: bool = True,
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
        audio_path = audio_mix.normalize(voice_path, out / "voiceover_norm.mp3")

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
        clips = _resolve_clips(background)
        if fast_cuts and (background.is_dir() or len(clips) > 1):
            bg = footage.prepare_fast_cuts(clips, duration, w, h, workdir=out)
        else:
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


def _maybe_publish(
    cfg: Config, result: PipelineResult, *, publish: bool, privacy: str | None
) -> PipelineResult:
    if not publish:
        return result
    if not cfg.has_youtube_credentials():
        raise RuntimeError(
            f"--publish set but no OAuth client at {cfg.yt_client_secret}. "
            "Drop client_secret.json from Google Cloud there first."
        )
    from . import publish as publish_mod

    upload = publish_mod.upload_from_script(
        cfg, result.video_path, result.script, privacy=privacy,
    )
    result.upload_url = upload.url
    return result


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
    fast_cuts: bool = True,
    publish: bool = False,
    privacy: str | None = None,
) -> PipelineResult:
    """Auto-script via Claude, then render (and optionally upload)."""
    cfg.require_anthropic()
    script = generate_script(
        cfg, topic,
        duration_seconds=duration_seconds, style=style, language=language,
    )
    result = render_from_script(
        cfg, script,
        fmt=fmt, background=background, music=music,
        word_captions=word_captions, language=language, fast_cuts=fast_cuts,
    )
    return _maybe_publish(cfg, result, publish=publish, privacy=privacy)


def run_from_text(
    cfg: Config,
    text_path: Path,
    *,
    language: str = "de",
    fmt: VideoFormat = VideoFormat.SHORTS,
    background: Path | None = None,
    music: Path | None = None,
    word_captions: bool = True,
    fast_cuts: bool = True,
    publish: bool = False,
    privacy: str | None = None,
) -> PipelineResult:
    """Parse a text file into a script, then render (and optionally upload)."""
    script = from_text(text_path)
    result = render_from_script(
        cfg, script,
        fmt=fmt, background=background, music=music,
        word_captions=word_captions, language=language, fast_cuts=fast_cuts,
    )
    return _maybe_publish(cfg, result, publish=publish, privacy=privacy)
