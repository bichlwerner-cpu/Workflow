"""Typer-based CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import footage as footage_mod
from .config import Config
from .pipeline import run_pipeline
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
    help="YouTube content pipeline: topic -> script -> TTS -> video.",
)
footage_app = typer.Typer(help="Manage footage assets (download, clip, list).")
app.add_typer(footage_app, name="footage")
console = Console()


@app.command()
def run(
    topic: Annotated[str, typer.Argument(help="Video topic / idea.")],
    duration: Annotated[int, typer.Option(help="Target voiceover duration (s).")] = 90,
    style: Annotated[Style, typer.Option(help="Script style.")] = "explainer",
    language: Annotated[str, typer.Option(help="Language code (de/en/...).")] = "de",
    fmt: Annotated[
        VideoFormat, typer.Option("--format", help="landscape (16:9) or shorts (9:16).")
    ] = VideoFormat.LANDSCAPE,
    background: Annotated[
        Optional[Path],
        typer.Option(help="Footage file or dir to use as background. Default: title card."),
    ] = None,
    music: Annotated[
        Optional[Path],
        typer.Option(help="Background music file. Default: auto-pick from MUSIC_DIR."),
    ] = None,
    word_captions: Annotated[
        bool, typer.Option(help="Use Whisper word-level captions (ASS).")
    ] = False,
) -> None:
    """Run the full pipeline."""
    cfg = Config.load()
    console.print(f"[bold]Topic:[/bold] {topic}")
    console.print(
        f"[bold]Style:[/bold] {style}  [bold]Lang:[/bold] {language}  "
        f"[bold]Dur:[/bold] {duration}s  [bold]Format:[/bold] {fmt.value}"
    )
    if background:
        console.print(f"[bold]Background:[/bold] {background}")
    if word_captions:
        console.print("[bold]Captions:[/bold] Whisper word-level")

    with console.status("Running pipeline (script -> tts -> video)..."):
        result = run_pipeline(
            cfg, topic,
            duration_seconds=duration, style=style, language=language,
            fmt=fmt, background=background, music=music,
            word_captions=word_captions,
        )

    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    console.print(f"\n[bold]{result.script.title}[/bold]")
    console.print(result.script.description)


@app.command()
def script(
    topic: Annotated[str, typer.Argument()],
    duration: Annotated[int, typer.Option()] = 90,
    style: Annotated[Style, typer.Option()] = "explainer",
    language: Annotated[str, typer.Option()] = "de",
    out: Annotated[Path, typer.Option()] = Path("out/script.json"),
) -> None:
    """Generate just the script (no TTS, no video)."""
    cfg = Config.load()
    with console.status("Generating script..."):
        s = generate_script(
            cfg, topic, duration_seconds=duration, style=style, language=language,
        )
    save_script(s, out)
    console.print(f"[green]✓[/green] {out}")
    console.print(f"\n[bold]{s.title}[/bold]\n{s.description}")


@app.command()
def tts(
    script_path: Annotated[Path, typer.Argument()],
    out: Annotated[Path, typer.Option()] = Path("out/voiceover.mp3"),
) -> None:
    """Render voiceover from a script JSON."""
    cfg = Config.load()
    s = load_script(script_path)
    with console.status("Synthesizing voice..."):
        synthesize(cfg, script_to_voiceover_text(s), out)
    console.print(f"[green]✓[/green] {out}")


@app.command()
def video(
    script_path: Annotated[Path, typer.Argument()],
    audio: Annotated[Path, typer.Option()] = Path("out/voiceover.mp3"),
    out: Annotated[Path, typer.Option()] = Path("out/final.mp4"),
    fmt: Annotated[VideoFormat, typer.Option("--format")] = VideoFormat.LANDSCAPE,
) -> None:
    """Assemble video from a script + audio (title-card path, no footage)."""
    Config.load()
    s = load_script(script_path)
    from .video import audio_duration_seconds
    duration = audio_duration_seconds(audio)
    sub_path = write_srt_from_script(s, duration, out.parent / "subtitles.srt")
    with console.status("Rendering video..."):
        render_with_title_card(s, audio, sub_path, out, workdir=out.parent, fmt=fmt)
    console.print(f"[green]✓[/green] {out}")


@app.command()
def voices() -> None:
    """List available ElevenLabs voices."""
    cfg = Config.load()
    table = Table(title="ElevenLabs voices")
    table.add_column("voice_id")
    table.add_column("name")
    for vid, name in list_voices(cfg):
        table.add_row(vid, name)
    console.print(table)


# ---------- footage subcommands ----------


@footage_app.command("download")
def footage_download(
    url: Annotated[str, typer.Argument(help="YouTube URL.")],
    max_height: Annotated[int, typer.Option()] = 1080,
) -> None:
    """Download a YouTube video to FOOTAGE_DIR.

    Reminder: respect copyright. Use only for content you have rights to,
    public domain, CC-licensed, or fair-use commentary in your jurisdiction.
    """
    cfg = Config.load()
    with console.status(f"Downloading {url}..."):
        path = footage_mod.download(url, cfg.footage_dir, max_height=max_height)
    console.print(f"[green]✓[/green] {path}")


@footage_app.command("clip")
def footage_clip(
    source: Annotated[Path, typer.Argument(help="Source video file.")],
    start: Annotated[str, typer.Option(help="HH:MM:SS or seconds.")],
    end: Annotated[str, typer.Option(help="HH:MM:SS or seconds.")],
    label: Annotated[str, typer.Option(help="Output filename label.")] = "clip",
    fast: Annotated[bool, typer.Option("--fast", help="Stream-copy (faster, keyframe-snapped).")] = False,
) -> None:
    """Cut a clip out of a downloaded video."""
    cfg = Config.load()
    out = cfg.footage_dir / f"{source.stem}__{label}.mp4"
    with console.status(f"Clipping {start} -> {end}..."):
        footage_mod.clip(source, start, end, out, reencode=not fast)
    console.print(f"[green]✓[/green] {out}")


@footage_app.command("list")
def footage_list() -> None:
    """List videos in FOOTAGE_DIR."""
    cfg = Config.load()
    items = footage_mod.list_footage(cfg.footage_dir)
    if not items:
        console.print(f"[yellow]No footage in {cfg.footage_dir}[/yellow]")
        return
    table = Table(title=f"Footage in {cfg.footage_dir}")
    table.add_column("file")
    table.add_column("size")
    for p in items:
        size_mb = p.stat().st_size / (1024 * 1024)
        table.add_row(p.name, f"{size_mb:.1f} MB")
    console.print(table)


if __name__ == "__main__":
    app()
