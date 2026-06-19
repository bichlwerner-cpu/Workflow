"""Typer-based CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import footage as footage_mod
from .config import Config
from .pipeline import run_from_text, run_pipeline
from .script import (
    Style,
    generate_script,
    load_script,
    save_script,
    script_to_voiceover_text,
)
from .tts import list_voices, synthesize
from .video import VideoFormat, render_with_title_card, write_srt_from_script

app = typer.Typer(
    add_completion=False,
    help="Automated stickman YouTube channel: topic -> script -> TTS -> "
    "animation -> captions -> video + thumbnail + metadata.",
)
footage_app = typer.Typer(help="Footage assets (download, clip, list).")
channel_app = typer.Typer(help="Automated stickman channel: episodes & batches.")
stickman_app = typer.Typer(help="Stickman animation engine (demo, actions).")
app.add_typer(footage_app, name="footage")
app.add_typer(channel_app, name="channel")
app.add_typer(stickman_app, name="stickman")
console = Console()


# ============================================================
# Free workflow: text -> video
# ============================================================


@app.command(name="from-text")
def from_text_cmd(
    text_path: Annotated[Path, typer.Argument(help="Plain-text Skript-Datei.")],
    fmt: Annotated[
        VideoFormat, typer.Option("--format", help="landscape oder shorts.")
    ] = VideoFormat.SHORTS,
    background: Annotated[
        Optional[Path],
        typer.Option(help="Footage-Datei oder -Verzeichnis als Hintergrund."),
    ] = None,
    music: Annotated[
        Optional[Path],
        typer.Option(help="Musik-Datei. Sonst Auto-Pick aus MUSIC_DIR."),
    ] = None,
    word_captions: Annotated[
        bool, typer.Option(help="Whisper Word-Level Captions.")
    ] = True,
    language: Annotated[str, typer.Option(help="Sprachcode für Whisper.")] = "de",
) -> None:
    """Render ein Video aus einer Plain-Text-Skript-Datei (gratis Workflow)."""
    cfg = Config.load()
    console.print(f"[bold]Skript:[/bold] {text_path}")
    console.print(
        f"[bold]Format:[/bold] {fmt.value}  "
        f"[bold]TTS:[/bold] {cfg.tts_provider}  "
        f"[bold]Captions:[/bold] {'word-level' if word_captions else 'section'}"
    )
    if background:
        console.print(f"[bold]Background:[/bold] {background}")

    with console.status("Rendering..."):
        result = run_from_text(
            cfg, text_path,
            language=language, fmt=fmt,
            background=background, music=music,
            word_captions=word_captions,
        )

    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    console.print(f"\n[bold]{result.script.title}[/bold]")


# ============================================================
# Paid workflow: Claude generates the script
# ============================================================


@app.command()
def run(
    topic: Annotated[str, typer.Argument(help="Video-Thema.")],
    duration: Annotated[int, typer.Option()] = 90,
    style: Annotated[Style, typer.Option()] = "explainer",
    language: Annotated[str, typer.Option()] = "de",
    fmt: Annotated[VideoFormat, typer.Option("--format")] = VideoFormat.LANDSCAPE,
    background: Annotated[Optional[Path], typer.Option()] = None,
    music: Annotated[Optional[Path], typer.Option()] = None,
    word_captions: Annotated[bool, typer.Option()] = False,
) -> None:
    """Voll-automatisch: Claude schreibt Skript -> TTS -> Video. Braucht Anthropic-Key."""
    cfg = Config.load()
    with console.status("Pipeline läuft..."):
        result = run_pipeline(
            cfg, topic,
            duration_seconds=duration, style=style, language=language,
            fmt=fmt, background=background, music=music,
            word_captions=word_captions,
        )
    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    console.print(f"\n[bold]{result.script.title}[/bold]\n{result.script.description}")


@app.command()
def script(
    topic: Annotated[str, typer.Argument()],
    duration: Annotated[int, typer.Option()] = 90,
    style: Annotated[Style, typer.Option()] = "explainer",
    language: Annotated[str, typer.Option()] = "de",
    out: Annotated[Path, typer.Option()] = Path("out/script.json"),
) -> None:
    """Nur Skript via Claude. Braucht Anthropic-Key."""
    cfg = Config.load()
    cfg.require_anthropic()
    with console.status("Generiere Skript..."):
        s = generate_script(
            cfg, topic, duration_seconds=duration, style=style, language=language,
        )
    save_script(s, out)
    console.print(f"[green]✓[/green] {out}")
    console.print(f"\n[bold]{s.title}[/bold]\n{s.description}")


# ============================================================
# Building blocks
# ============================================================


@app.command()
def tts(
    script_path: Annotated[Path, typer.Argument(help="script.json (von Claude oder from-text).")],
    out: Annotated[Path, typer.Option()] = Path("out/voiceover.mp3"),
) -> None:
    """Voiceover aus einem Skript-JSON erzeugen."""
    cfg = Config.load()
    s = load_script(script_path)
    with console.status(f"TTS via {cfg.tts_provider}..."):
        synthesize(cfg, script_to_voiceover_text(s), out)
    console.print(f"[green]✓[/green] {out}")


@app.command()
def video(
    script_path: Annotated[Path, typer.Argument()],
    audio: Annotated[Path, typer.Option()] = Path("out/voiceover.mp3"),
    out: Annotated[Path, typer.Option()] = Path("out/final.mp4"),
    fmt: Annotated[VideoFormat, typer.Option("--format")] = VideoFormat.LANDSCAPE,
) -> None:
    """Video bauen: Title-Card-Pfad (kein Footage)."""
    Config.load()
    s = load_script(script_path)
    from .video import audio_duration_seconds
    duration = audio_duration_seconds(audio)
    sub_path = write_srt_from_script(s, duration, out.parent / "subtitles.srt")
    with console.status("Rendering..."):
        render_with_title_card(s, audio, sub_path, out, workdir=out.parent, fmt=fmt)
    console.print(f"[green]✓[/green] {out}")


@app.command()
def voices(
    language: Annotated[
        Optional[str],
        typer.Option(help="Filter nach Sprachcode (z.B. 'de'). Nur edge-tts."),
    ] = None,
) -> None:
    """Verfügbare Stimmen des aktiven TTS-Providers auflisten."""
    cfg = Config.load()
    table = Table(title=f"Voices ({cfg.tts_provider})")
    table.add_column("voice")
    table.add_column("info")
    for vid, info in list_voices(cfg, language=language):
        table.add_row(vid, info)
    console.print(table)


# ============================================================
# Footage subcommands
# ============================================================


@footage_app.command("download")
def footage_download(
    url: Annotated[str, typer.Argument(help="YouTube-URL.")],
    max_height: Annotated[int, typer.Option()] = 1080,
) -> None:
    """YouTube-Video nach FOOTAGE_DIR herunterladen."""
    cfg = Config.load()
    with console.status(f"Lade {url}..."):
        path = footage_mod.download(url, cfg.footage_dir, max_height=max_height)
    console.print(f"[green]✓[/green] {path}")


@footage_app.command("clip")
def footage_clip(
    source: Annotated[Path, typer.Argument(help="Quell-Video.")],
    start: Annotated[str, typer.Option(help="HH:MM:SS oder Sekunden.")],
    end: Annotated[str, typer.Option(help="HH:MM:SS oder Sekunden.")],
    label: Annotated[str, typer.Option(help="Datei-Label.")] = "clip",
    fast: Annotated[bool, typer.Option("--fast")] = False,
) -> None:
    """Clip aus einem Video schneiden."""
    cfg = Config.load()
    out = cfg.footage_dir / f"{source.stem}__{label}.mp4"
    with console.status(f"Schneide {start} -> {end}..."):
        footage_mod.clip(source, start, end, out, reencode=not fast)
    console.print(f"[green]✓[/green] {out}")


@footage_app.command("list")
def footage_list() -> None:
    """Alle Videos in FOOTAGE_DIR auflisten."""
    cfg = Config.load()
    items = footage_mod.list_footage(cfg.footage_dir)
    if not items:
        console.print(f"[yellow]Kein Footage in {cfg.footage_dir}[/yellow]")
        return
    table = Table(title=f"Footage in {cfg.footage_dir}")
    table.add_column("file")
    table.add_column("size")
    for p in items:
        size_mb = p.stat().st_size / (1024 * 1024)
        table.add_row(p.name, f"{size_mb:.1f} MB")
    console.print(table)


# ============================================================
# Stickman channel (psychology, fast-paced, animated)
# ============================================================


@channel_app.command("episode")
def channel_episode(
    topic: Annotated[Optional[str], typer.Argument(help="Topic. Omit to pick from the bank.")] = None,
    preset: Annotated[str, typer.Option(help="Channel preset.")] = "psychology_en",
    source: Annotated[str, typer.Option(help="auto | curated | template | claude")] = "auto",
    theme: Annotated[Optional[str], typer.Option(help="Override visual theme.")] = None,
    fps: Annotated[Optional[int], typer.Option(help="Override frames per second.")] = None,
    supersample: Annotated[int, typer.Option(help="2 = smoother lines, ~4x slower.")] = 1,
) -> None:
    """Produce one finished stickman episode (video + thumbnail + metadata)."""
    from .channel import get_preset, produce_episode

    cfg = Config.load()
    ch = get_preset(preset)
    if theme:
        ch.theme = theme
    if fps:
        ch.fps = fps
    ch.supersample = supersample

    console.print(f"[bold]Channel:[/bold] {ch.name} ({ch.handle})  "
                  f"[bold]theme:[/bold] {ch.theme}  [bold]source:[/bold] {source}")
    with console.status("Producing episode (script → voice → animation → caption → render)..."):
        res = produce_episode(cfg, channel=ch, topic=topic, source=source)

    console.print(f"\n[bold]{res.script.title}[/bold]")
    console.print(f"[green]✓[/green] Video     -> {res.video_path}")
    console.print(f"[green]✓[/green] Thumbnail -> {res.thumbnail_path}")
    console.print(f"[green]✓[/green] Metadata  -> {res.metadata_path}")
    console.print(f"[green]✓[/green] Duration  -> {res.duration:.1f}s, {len(res.script.beats)} beats")


@channel_app.command("batch")
def channel_batch(
    count: Annotated[int, typer.Option(help="How many episodes to produce.")] = 5,
    preset: Annotated[str, typer.Option()] = "psychology_en",
    source: Annotated[str, typer.Option(help="auto | curated | template | claude")] = "auto",
    supersample: Annotated[int, typer.Option()] = 1,
) -> None:
    """Produce a batch of episodes and lay out a publish schedule."""
    from .channel import get_preset, produce_batch

    cfg = Config.load()
    ch = get_preset(preset)
    ch.supersample = supersample
    console.print(f"[bold]Producing {count} episodes for {ch.name}...[/bold]")

    def _progress(i: int, n: int, topic: str) -> None:
        console.print(f"  [{i + 1}/{n}] {topic}")

    results = produce_batch(cfg, channel=ch, count=count, source=source, progress=_progress)

    table = Table(title=f"{ch.name}: {len(results)} episodes")
    table.add_column("title")
    table.add_column("dur")
    table.add_column("dir")
    for r in results:
        table.add_row(r.script.title, f"{r.duration:.0f}s", str(r.directory))
    console.print(table)


@channel_app.command("topics")
def channel_topics() -> None:
    """List the built-in psychology topic bank."""
    from .content.psychology import list_topics

    table = Table(title="Psychology topic bank")
    table.add_column("#")
    table.add_column("topic")
    table.add_column("angle")
    for i, (t, a) in enumerate(list_topics(), start=1):
        table.add_row(str(i), t, a)
    console.print(table)


@channel_app.command("presets")
def channel_presets() -> None:
    """List channel presets."""
    from .channel import PRESETS

    table = Table(title="Channel presets")
    table.add_column("preset")
    table.add_column("name")
    table.add_column("lang")
    table.add_column("theme")
    table.add_column("voice")
    for key, ch in PRESETS.items():
        table.add_row(key, ch.name, ch.language, ch.theme, ch.voice or "(env)")
    console.print(table)


@channel_app.command("upload")
def channel_upload(
    episode_dir: Annotated[Path, typer.Argument(help="Episode directory (with metadata.json).")],
    client_secret: Annotated[Optional[Path], typer.Option(help="OAuth client_secret.json.")] = None,
    token: Annotated[Optional[Path], typer.Option(help="Cached OAuth token store.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate & print plan only.")] = False,
) -> None:
    """Upload a produced episode to YouTube (or --dry-run to preview)."""
    from .youtube_upload import describe_plan, load_plan, upload_episode

    meta, video, thumb = load_plan(episode_dir)
    console.print(f"[bold]Upload plan for {episode_dir.name}:[/bold]")
    console.print(describe_plan(meta, video, thumb))
    if dry_run:
        console.print("[yellow]--dry-run: nothing uploaded.[/yellow]")
        return
    if not client_secret:
        console.print("[red]--client-secret is required to upload (see README).[/red]")
        raise typer.Exit(1)
    with console.status("Uploading to YouTube..."):
        vid = upload_episode(episode_dir, client_secret=client_secret,
                             token_store=token, dry_run=False)
    console.print(f"[green]✓[/green] https://youtu.be/{vid}")


# ============================================================
# Stickman engine helpers
# ============================================================


@stickman_app.command("demo")
def stickman_demo(
    out: Annotated[Path, typer.Option(help="Output mp4.")] = Path("out/stickman_demo.mp4"),
    theme: Annotated[str, typer.Option()] = "midnight",
    fps: Annotated[int, typer.Option()] = 30,
) -> None:
    """Render a short showcase animation (no TTS, no network)."""
    from .stickman.scene import Beat, RenderConfig, render_storyboard

    beats = [
        Beat("Your brain is lying to you.", action="point", keyword="LIE", intensity=0.85, start=0.0, duration=2.0),
        Beat("Stress hijacks every decision.", action="panic", keyword="STRESS", intensity=0.95, start=2.0, duration=2.0),
        Beat("Procrastination is fear in disguise.", action="facepalm", keyword="FEAR", intensity=0.7, start=4.0, duration=2.0),
        Beat("But awareness flips the switch.", action="idea", keyword="AWARE", intensity=0.85, start=6.0, duration=2.0),
        Beat("Take back control.", action="power", keyword="CONTROL", intensity=0.9, start=8.0, duration=2.0),
    ]
    cfg = RenderConfig(width=1080, height=1920, fps=fps, theme=theme)
    with console.status("Rendering demo..."):
        render_storyboard(beats, out, cfg)
    console.print(f"[green]✓[/green] {out}")


@stickman_app.command("actions")
def stickman_actions() -> None:
    """List the available stickman actions."""
    from .stickman.actions import action_names

    console.print("Actions: " + ", ".join(action_names()))


if __name__ == "__main__":
    app()
