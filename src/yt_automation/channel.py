"""Channel orchestration: turn a topic into a finished, uploadable episode.

Pipeline per episode::

    topic -> StickScript -> per-beat TTS (+ word timings)
          -> concat voiceover -> mix music
          -> stickman animation (timed to each beat)
          -> word-by-word captions -> final compose
          -> thumbnail + metadata.json

:func:`produce_batch` runs this for several topics and lays out a publish
schedule, so the whole channel can be filled with one command.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import audio_mix, captions
from .config import Config
from .content.psychology import StickScript, generate_stickscript
from .stickman.render import get_theme, load_font
from .stickman.scene import Beat, RenderConfig, render_storyboard
from .stickman.skeleton import Skeleton, resolve
from .tts import synthesize_with_marks
from .video import VideoFormat, audio_duration_seconds, dimensions, render_with_footage


# ---------------------------------------------------------------------------
# Channel configuration / presets
# ---------------------------------------------------------------------------


@dataclass
class ChannelConfig:
    name: str = "Mind Mechanics"
    handle: str = "@mindmechanics"
    language: str = "en"
    theme: str = "midnight"
    fmt: VideoFormat = VideoFormat.SHORTS
    fps: int = 30
    gap: float = 0.14                 # silence between beats (seconds)
    supersample: int = 1
    words_per_caption: int = 1
    caption_margin_frac: float = 0.10   # caption distance from bottom (lower third)
    # brand mascot + montage (long-form, still-image cut) settings
    character: str = "halo"             # recurring character preset (the brand)
    shot_len: float = 1.9               # avg seconds per hard cut in montage mode
    # optional TTS overrides applied on top of .env Config
    tts_provider: str | None = None
    voice: str | None = None
    # publishing
    category_id: str = "27"           # YouTube "Education"
    privacy: str = "private"          # private | unlisted | public
    publish_per_day: int = 1
    cta: str = "Follow for daily psychology."
    tagline: str = "the psychology they never taught you"   # intro card subtitle

    def hashtags(self, tags: list[str]) -> list[str]:
        seen, out = set(), []
        for t in ["psychology", "shorts", "mindset", *tags]:
            h = "#" + re.sub(r"[^a-z0-9]", "", t.lower())
            if h not in seen and len(h) > 1:
                seen.add(h)
                out.append(h)
        return out[:6]


PRESETS: dict[str, ChannelConfig] = {
    "psychology_en": ChannelConfig(
        name="Mind Mechanics", handle="@mindmechanics", language="en",
        theme="midnight", voice="en-US-AndrewMultilingualNeural",
    ),
    "psychology_de": ChannelConfig(
        name="Kopfsache", handle="@kopfsache", language="de",
        theme="void", voice="de-DE-KillianNeural", cta="Folge für tägliche Psychologie.",
    ),
    "dark_intense": ChannelConfig(
        name="The Mind Game", handle="@themindgame", language="en",
        theme="bloodmoon", voice="en-US-BrianMultilingualNeural", gap=0.10,
    ),
}


def get_preset(name: str) -> ChannelConfig:
    return dataclasses.replace(PRESETS.get(name, PRESETS["psychology_en"]))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class EpisodeResult:
    slug: str
    directory: Path
    script: StickScript
    video_path: Path
    audio_path: Path
    thumbnail_path: Path
    metadata_path: Path
    duration: float


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "episode"


def _apply_channel_to_config(cfg: Config, ch: ChannelConfig) -> Config:
    changes = {}
    if ch.tts_provider:
        changes["tts_provider"] = ch.tts_provider
    if ch.voice and (ch.tts_provider or cfg.tts_provider) == "edge":
        changes["edge_voice"] = ch.voice
    return dataclasses.replace(cfg, **changes) if changes else cfg


# ---------------------------------------------------------------------------
# Audio: per-beat synthesis + timing
# ---------------------------------------------------------------------------


def _silence(path: Path, seconds: float, ffmpeg: str = "ffmpeg") -> Path:
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=44100:cl=mono", "-t", f"{seconds:.3f}",
         "-c:a", "libmp3lame", "-q:a", "5", str(path)],
        check=True, capture_output=True,
    )
    return path


def pad_and_polish_audio(
    audio_path: Path, out: Path, *, lead_in: float, tail: float, ffmpeg: str = "ffmpeg"
) -> tuple[Path, float]:
    """Loudness-normalise, add a lead-in/tail and fade in/out.

    Gives the video a clean opener (intro card runs over the lead-in silence),
    a graceful ending (outro card over the tail) and consistent loudness — a
    recognisable jump in perceived production quality. Returns (path, duration).
    """
    body = audio_duration_seconds(audio_path)
    total = lead_in + body + tail
    delay_ms = int(lead_in * 1000)
    fade_out_start = max(0.0, total - 0.7)
    af = (
        "loudnorm=I=-15:TP=-1.5:LRA=11,"
        f"adelay=delays={delay_ms}:all=1,"
        f"apad=pad_dur={tail:.3f},"
        "afade=t=in:st=0:d=0.4,"
        f"afade=t=out:st={fade_out_start:.3f}:d=0.7"
    )
    subprocess.run(
        [ffmpeg, "-y", "-i", str(audio_path), "-af", af,
         "-c:a", "libmp3lame", "-q:a", "2", str(out)],
        check=True, capture_output=True,
    )
    return out, total


def _concat_audio(clips: list[Path], out: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Concatenate audio clips via the concat filter (decode+re-encode, robust)."""
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    n = len(clips)
    fc = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    subprocess.run(
        [ffmpeg, "-y", *inputs, "-filter_complex", fc, "-map", "[a]",
         "-c:a", "libmp3lame", "-q:a", "2", str(out)],
        check=True, capture_output=True,
    )
    return out


def build_timed_beats(
    cfg: Config,
    script: StickScript,
    ch: ChannelConfig,
    workdir: Path,
) -> tuple[list[Beat], Path, list[captions.Word]]:
    """Synthesize each beat, stitch the voiceover, and return timed render beats.

    Returns ``(render_beats, voiceover_path, caption_words)``.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    sil = _silence(workdir / "_gap.mp3", ch.gap) if ch.gap > 0 else None

    render_beats: list[Beat] = []
    caption_words: list[captions.Word] = []
    clips: list[Path] = []
    cursor = 0.0

    for i, sb in enumerate(script.beats):
        clip = workdir / f"beat_{i:02d}.mp3"
        _, marks = synthesize_with_marks(cfg, sb.text, clip)
        speech = audio_duration_seconds(clip)
        start = cursor
        # captions: real word marks if we have them, else even distribution
        if marks:
            for w in captions.words_from_marks(marks):
                caption_words.append(
                    captions.Word(w.text, start + w.start, start + min(w.end, speech))
                )
        else:
            caption_words.extend(captions.even_words(sb.text, start, start + speech))

        dur = speech + (ch.gap if ch.gap > 0 else 0.0)
        render_beats.append(Beat(
            text=sb.text, action=sb.action, keyword=sb.keyword,
            intensity=sb.resolved_intensity(), start=start, duration=dur,
        ))
        clips.append(clip)
        if sil is not None:
            clips.append(sil)
        cursor += dur

    voice = _concat_audio(clips, workdir / "voiceover.mp3")
    return render_beats, voice, caption_words


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------


def render_thumbnail(script: StickScript, ch: ChannelConfig, out: Path) -> Path:
    """1280x720 thumbnail: big title + a hero stickman pose on the theme."""
    from PIL import Image, ImageDraw

    from .stickman import poses
    from .stickman.character import draw_accessories, get_character
    from .stickman.render import apply_vignette, draw_figure, make_background

    W, H = 1280, 720
    theme = get_theme(ch.theme)
    character = get_character(ch.character)
    img = make_background(W, H, theme, energy=0.7)

    skel = Skeleton()
    scale = (H * 0.56) / skel.total_height()
    root = (W * 0.83, H * 0.9 - (skel.thigh + skel.shin) * scale)
    hero = poses.IDEA
    j = resolve(hero, skel, root, scale)
    draw_figure(img, j, color=character.body, glow_color=character.glow)
    draw_accessories(img, j, character)
    img = apply_vignette(img, 0.92)

    draw = ImageDraw.Draw(img, "RGBA")
    # Pack the title into <=3 lines, then auto-fit so the widest line stays in
    # the left ~60% of the frame and never collides with the hero figure.
    # Drop parentheticals — thumbnails read better with just the punchy core.
    thumb_text = re.sub(r"\s*\(.*?\)\s*", " ", script.title).strip() or script.title
    words = thumb_text.upper().split()
    lines, line = [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if len(trial) > 12 and line:
            lines.append(line)
            line = w
        else:
            line = trial
    if line:
        lines.append(line)
    lines = lines[:3]

    margin_x = int(W * 0.06)
    max_w = int(W * 0.60)
    size = 132
    while size > 40:
        font = load_font(size)
        widest = max(draw.textbbox((0, 0), ln, font=font)[2] for ln in lines)
        if widest <= max_w:
            break
        size -= 4
    font = load_font(size)

    line_h = int(size * 1.06)
    y = int((H - line_h * len(lines)) / 2) - int(H * 0.04)
    for ln in lines:
        draw.text((margin_x + 5, y + 5), ln, font=font, fill=(0, 0, 0, 210))
        draw.text((margin_x, y), ln, font=font, fill=theme.accent + (255,))
        y += line_h

    draw.rectangle([margin_x, y + 10, margin_x + 240, y + 26], fill=theme.accent2 + (255,))
    hf = load_font(34)
    draw.text((margin_x, H - 70), ch.handle, font=hf, fill=theme.figure + (220,))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=92)
    return out


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def build_metadata(script: StickScript, ch: ChannelConfig, *, duration: float,
                   publish_at: datetime | None) -> dict:
    tags = list(dict.fromkeys(script.tags))[:15]
    hashtags = ch.hashtags(tags)
    desc = (
        f"{script.description}\n\n{ch.cta}\n\n"
        + " ".join(hashtags)
        + "\n\nEducational psychology content. Not medical or mental-health advice."
    )
    return {
        "channel": ch.name,
        "handle": ch.handle,
        "title": script.title,
        "description": desc,
        "tags": tags,
        "hashtags": hashtags,
        "categoryId": ch.category_id,
        "privacyStatus": ch.privacy,
        "language": ch.language,
        "durationSeconds": round(duration, 2),
        "publishAt": publish_at.isoformat() if publish_at else None,
        "madeForKids": False,
    }


# ---------------------------------------------------------------------------
# Episode + batch
# ---------------------------------------------------------------------------


def produce_episode(
    cfg: Config,
    *,
    channel: ChannelConfig,
    topic: str | None = None,
    angle: str | None = None,
    source: str = "auto",
    out_dir: Path | None = None,
    publish_at: datetime | None = None,
    grain: bool = True,
    watermark: bool = True,
    progress=None,
) -> EpisodeResult:
    cfg = _apply_channel_to_config(cfg, channel)
    script = generate_stickscript(
        cfg, topic, angle=angle, source=source, theme=channel.theme  # type: ignore[arg-type]
    )

    base = out_dir or (cfg.output_dir / "episodes")
    ep_dir = base / _slug(script.title)
    work = ep_dir / "work"
    ep_dir.mkdir(parents=True, exist_ok=True)

    render_beats, voice_path, caption_words = build_timed_beats(cfg, script, channel, work)

    # music bed (optional, auto-picked + ducked)
    music = audio_mix.pick_music(cfg.music_dir)
    if music is not None and music.exists():
        audio_path = audio_mix.mix(voice_path, music, work / "audio_mixed.mp3")
    else:
        audio_path = voice_path

    duration = audio_duration_seconds(audio_path)
    # clamp final beat so the animation matches the (possibly music-padded) audio
    if render_beats:
        last = render_beats[-1]
        render_beats[-1] = dataclasses.replace(
            last, duration=max(0.4, duration - last.start)
        )

    from .stickman.character import get_character

    char = get_character(channel.character)
    w, h = dimensions(channel.fmt)
    rcfg = RenderConfig(
        width=w, height=h, fps=channel.fps, theme=channel.theme,
        supersample=channel.supersample, character=channel.character,
        watermark=channel.handle if watermark else "", texture=grain,
    )
    bg_path = render_storyboard(render_beats, work / "stickman_bg.mp4", rcfg, progress=progress)

    ass_path = captions.write_ass_karaoke(
        caption_words, work / "captions.ass", width=w, height=h,
        accent=char.glow, margin_v_frac=channel.caption_margin_frac,
    )

    video_path = ep_dir / "video.mp4"
    render_with_footage(bg_path, audio_path, ass_path, video_path)

    thumb = render_thumbnail(script, channel, ep_dir / "thumbnail.jpg")

    meta = build_metadata(script, channel, duration=duration, publish_at=publish_at)
    meta["files"] = {"video": video_path.name, "thumbnail": thumb.name}
    meta_path = ep_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (ep_dir / "script.json").write_text(
        script.model_dump_json(indent=2), encoding="utf-8"
    )

    return EpisodeResult(
        slug=ep_dir.name, directory=ep_dir, script=script, video_path=video_path,
        audio_path=audio_path, thumbnail_path=thumb, metadata_path=meta_path,
        duration=duration,
    )


@dataclass
class Polish:
    """Toggle the production-polish layers (all on by default)."""

    intro: bool = True
    outro: bool = True
    progress: bool = True
    grain: bool = True
    watermark: bool = True
    captions: bool = True
    signature_poses: bool = True


def produce_longform(
    cfg: Config,
    *,
    channel: ChannelConfig,
    topic: str | None = None,
    angle: str | None = None,
    minutes: int = 5,
    source: str = "auto",
    out_dir: Path | None = None,
    publish_at: datetime | None = None,
    polish: "Polish | None" = None,
    progress=None,
) -> EpisodeResult:
    """Produce a 4-6 min montage video: many still shots of the brand character,
    hard-cut to the voiceover, with music + captions. No animation."""
    from .content.psychology import generate_longform
    from .stickman.character import get_character
    from .stickman.montage import MontageConfig, beats_to_shots, render_montage

    polish = polish or Polish()

    cfg = _apply_channel_to_config(cfg, channel)
    script = generate_longform(
        cfg, topic, angle=angle, minutes=minutes, source=source, theme=channel.theme,  # type: ignore[arg-type]
    )

    base = out_dir or (cfg.output_dir / "episodes")
    ep_dir = base / _slug(script.title)
    work = ep_dir / "work"
    ep_dir.mkdir(parents=True, exist_ok=True)

    render_beats, voice_path, caption_words = build_timed_beats(cfg, script, channel, work)

    music = audio_mix.pick_music(cfg.music_dir)
    if music is not None and music.exists():
        mixed = audio_mix.mix(voice_path, music, work / "audio_mixed.mp3")
    else:
        mixed = voice_path

    body = audio_duration_seconds(mixed)
    if render_beats:
        last = render_beats[-1]
        render_beats[-1] = dataclasses.replace(last, duration=max(0.4, body - last.start))

    lead_in = 0.9 if polish.intro else 0.0
    tail = 1.7 if polish.outro else 0.3
    audio_path, duration = pad_and_polish_audio(
        mixed, work / "audio_final.mp3", lead_in=lead_in, tail=tail
    )
    # shift captions to sit after the intro card / lead-in
    caption_words = [captions.Word(wd.text, wd.start + lead_in, wd.end + lead_in)
                     for wd in caption_words]

    char = get_character(channel.character)
    w, h = dimensions(channel.fmt)
    mcfg = MontageConfig(
        width=w, height=h, fps=channel.fps, theme=channel.theme,
        shot_len=channel.shot_len, captions=polish.captions,
        handle=channel.handle, channel_name=channel.name, tagline=channel.tagline,
        cta_title="FOLLOW", intro=polish.intro, outro=polish.outro,
        lead_in=lead_in, tail=tail, progress_bar=polish.progress,
        texture=polish.grain, watermark=polish.watermark,
        signature_poses=polish.signature_poses,
    )
    shots = beats_to_shots(render_beats, mcfg)

    ass_path = None
    if polish.captions:
        ass_path = captions.write_ass_karaoke(
            caption_words, work / "captions.ass", width=w, height=h,
            accent=char.glow, margin_v_frac=channel.caption_margin_frac,
        )

    video_path = ep_dir / "video.mp4"
    render_montage(
        shots, char, mcfg,
        audio_path=audio_path, out_path=video_path, captions_ass=ass_path,
        progress=progress,
    )

    thumb = render_thumbnail(script, channel, ep_dir / "thumbnail.jpg")
    meta = build_metadata(script, channel, duration=duration, publish_at=publish_at)
    meta["files"] = {"video": video_path.name, "thumbnail": thumb.name}
    meta["format"] = "longform-montage"
    meta["shots"] = len(shots)
    meta_path = ep_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (ep_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

    return EpisodeResult(
        slug=ep_dir.name, directory=ep_dir, script=script, video_path=video_path,
        audio_path=audio_path, thumbnail_path=thumb, metadata_path=meta_path,
        duration=duration,
    )


def produce_batch(
    cfg: Config,
    *,
    channel: ChannelConfig,
    count: int,
    topics: list[str] | None = None,
    source: str = "auto",
    start_date: datetime | None = None,
    progress=None,
) -> list[EpisodeResult]:
    """Produce ``count`` episodes and schedule them ``publish_per_day`` apart."""
    from .content.psychology import TOPICS

    if topics:
        plan: list[tuple[str, str | None]] = [(t, None) for t in topics[:count]]
    else:
        plan = [(t, a) for t, a in TOPICS[:count]]
    if not plan:
        return []

    start = start_date or (datetime.now(timezone.utc) + timedelta(days=1))
    step_hours = max(1, 24 // max(1, channel.publish_per_day))

    results: list[EpisodeResult] = []
    for i, (topic, angle) in enumerate(plan):
        publish_at = start + timedelta(hours=step_hours * i)
        if progress:
            progress(i, len(plan), topic)
        results.append(produce_episode(
            cfg, channel=channel, topic=topic, angle=angle, source=source,
            publish_at=publish_at,
        ))
    return results
