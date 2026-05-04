"""Typer-based CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

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
from .video import render_video

app = typer.Typer(
    add_completion=False,
    help="YouTube content pipeline: topic -> script -> TTS -> video.",
)
console = Console()


@app.command()
def run(
    topic: Annotated[str, typer.Argument(help="Video topic / idea.")],
    duration: Annotated[int, typer.Option(help="Target duration in seconds.")] = 90,
    style: Annotated[Style, typer.Option(help="Script style.")] = "explainer",
    language: Annotated[str, typer.Option(help="Language code (de/en/...).")] = "de",
) -> None:
    """Run the full pipeline: script -> TTS -> video."""
    cfg = Config.load()
    console.print(f"[bold]Topic:[/bold] {topic}")
    console.print(f"[bold]Style:[/bold] {style}  [bold]Lang:[/bold] {language}  [bold]Dur:[/bold] {duration}s")

    with console.status("Generating script via Claude..."):
        result = run_pipeline(
            cfg,
            topic,
            duration_seconds=duration,
            style=style,
            language=language,
        )

    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    console.print(f"\n[bold]{result.script.title}[/bold]")
    console.print(result.script.description)


@app.command()
def script(
    topic: Annotated[str, typer.Argument(help="Video topic / idea.")],
    duration: Annotated[int, typer.Option()] = 90,
    style: Annotated[Style, typer.Option()] = "explainer",
    language: Annotated[str, typer.Option()] = "de",
    out: Annotated[Path, typer.Option(help="Output JSON path.")] = Path("out/script.json"),
) -> None:
    """Generate just the script (no TTS, no video)."""
    cfg = Config.load()
    with console.status("Generating script..."):
        s = generate_script(
            cfg, topic, duration_seconds=duration, style=style, language=language
        )
    save_script(s, out)
    console.print(f"[green]✓[/green] {out}")
    console.print(f"\n[bold]{s.title}[/bold]\n{s.description}")


@app.command()
def tts(
    script_path: Annotated[Path, typer.Argument(help="Path to script.json.")],
    out: Annotated[Path, typer.Option(help="Output mp3 path.")] = Path("out/voiceover.mp3"),
) -> None:
    """Render voiceover from a script JSON."""
    cfg = Config.load()
    s = load_script(script_path)
    text = script_to_voiceover_text(s)
    with console.status("Synthesizing voice..."):
        synthesize(cfg, text, out)
    console.print(f"[green]✓[/green] {out}")


@app.command()
def video(
    script_path: Annotated[Path, typer.Argument(help="Path to script.json.")],
    audio: Annotated[Path, typer.Option(help="Voiceover mp3 path.")] = Path("out/voiceover.mp3"),
    out: Annotated[Path, typer.Option(help="Output mp4 path.")] = Path("out/final.mp4"),
) -> None:
    """Assemble the final video from a script + audio."""
    cfg = Config.load()  # noqa: F841 -- ensures env is healthy before ffmpeg
    s = load_script(script_path)
    with console.status("Rendering video..."):
        render_video(s, audio, out, workdir=out.parent)
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


if __name__ == "__main__":
    app()
