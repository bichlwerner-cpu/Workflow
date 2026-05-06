"""Typer-based CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import footage as footage_mod
from . import scene_pack as scene_pack_mod
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
    help="YouTube content pipeline: text/topic -> script -> TTS -> video.",
)
footage_app = typer.Typer(help="Footage assets (download, clip, list).")
app.add_typer(footage_app, name="footage")
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
        typer.Option(help="Footage-Datei, -Verzeichnis oder Scene-Pack."),
    ] = None,
    music: Annotated[
        Optional[Path],
        typer.Option(help="Musik-Datei. Sonst Auto-Pick aus MUSIC_DIR."),
    ] = None,
    word_captions: Annotated[
        bool, typer.Option(help="Whisper Word-Level Captions.")
    ] = True,
    language: Annotated[str, typer.Option(help="Sprachcode für Whisper.")] = "de",
    fast_cuts: Annotated[
        bool, typer.Option(help="Schnelle Cuts statt einem geloopten Background.")
    ] = True,
    publish: Annotated[
        bool, typer.Option(help="Nach Render direkt zu YouTube hochladen.")
    ] = False,
    privacy: Annotated[
        Optional[str],
        typer.Option(help="Override für Privacy: private/unlisted/public."),
    ] = None,
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
            word_captions=word_captions, fast_cuts=fast_cuts,
            publish=publish, privacy=privacy,
        )

    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    if result.upload_url:
        console.print(f"[green]✓[/green] Upload   -> {result.upload_url}")
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
    fast_cuts: Annotated[bool, typer.Option()] = True,
    publish: Annotated[bool, typer.Option()] = False,
    privacy: Annotated[Optional[str], typer.Option()] = None,
) -> None:
    """Voll-automatisch: Claude schreibt Skript -> TTS -> Video. Braucht Anthropic-Key."""
    cfg = Config.load()
    with console.status("Pipeline läuft..."):
        result = run_pipeline(
            cfg, topic,
            duration_seconds=duration, style=style, language=language,
            fmt=fmt, background=background, music=music,
            word_captions=word_captions, fast_cuts=fast_cuts,
            publish=publish, privacy=privacy,
        )
    console.print(f"[green]✓[/green] Script   -> {result.script_path}")
    console.print(f"[green]✓[/green] Audio    -> {result.audio_path}")
    console.print(f"[green]✓[/green] Video    -> {result.video_path}")
    if result.upload_url:
        console.print(f"[green]✓[/green] Upload   -> {result.upload_url}")
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


@footage_app.command("extract")
def footage_extract(
    source: Annotated[Path, typer.Argument(help="Quell-Video (lokale Datei).")],
    threshold: Annotated[
        Optional[float],
        typer.Option(help="Scene-Detection-Schwelle. Override für SCENE_THRESHOLD."),
    ] = None,
    min_len: Annotated[
        Optional[float], typer.Option(help="Min. Clip-Laenge in Sek.")
    ] = None,
    max_len: Annotated[
        Optional[float], typer.Option(help="Max. Clip-Laenge in Sek.")
    ] = None,
    min_motion: Annotated[
        float, typer.Option(help="Statische Frames filtern (0 = alles behalten).")
    ] = 1.5,
    keep_top: Annotated[
        Optional[int], typer.Option(help="Nur die N bewegtesten Clips behalten.")
    ] = None,
) -> None:
    """Quell-Video in einen Scene-Pack zerlegen (kurze, motion-reiche Clips)."""
    cfg = Config.load()
    th = threshold if threshold is not None else cfg.scene_threshold
    mn = min_len if min_len is not None else cfg.scene_min_len
    mx = max_len if max_len is not None else cfg.scene_max_len

    with console.status(f"Extrahiere Szenen aus {source.name}..."):
        scenes = scene_pack_mod.extract(
            source, cfg.footage_dir,
            threshold=th, min_len=mn, max_len=mx,
            min_motion=min_motion, keep_top=keep_top,
        )
    pack_dir = cfg.footage_dir / source.stem
    console.print(f"[green]✓[/green] {len(scenes)} Szenen -> {pack_dir}")

    table = Table(title="Top Scenes (motion)")
    table.add_column("idx")
    table.add_column("dur")
    table.add_column("motion")
    for s in sorted(scenes, key=lambda x: x.motion_score, reverse=True)[:10]:
        table.add_row(
            f"{s.index:03d}", f"{s.duration:.1f}s", f"{s.motion_score:.2f}"
        )
    console.print(table)


@footage_app.command("packs")
def footage_packs() -> None:
    """Vorhandene Scene-Packs auflisten."""
    cfg = Config.load()
    packs = scene_pack_mod.list_packs(cfg.footage_dir)
    if not packs:
        console.print(f"[yellow]Keine Scene-Packs in {cfg.footage_dir}[/yellow]")
        return
    table = Table(title="Scene-Packs")
    table.add_column("pack")
    table.add_column("scenes")
    for p in packs:
        scenes = scene_pack_mod.load_pack(p)
        table.add_row(p.name, str(len(scenes)))
    console.print(table)


# ============================================================
# Publishing
# ============================================================


@app.command()
def publish(
    video_path: Annotated[Path, typer.Argument(help="MP4 zum Hochladen.")],
    script_path: Annotated[
        Optional[Path],
        typer.Option(help="script.json fuer Title/Description/Tags."),
    ] = None,
    title: Annotated[Optional[str], typer.Option()] = None,
    description: Annotated[Optional[str], typer.Option()] = None,
    tags: Annotated[
        Optional[str], typer.Option(help="Komma-separierte Tags.")
    ] = None,
    privacy: Annotated[Optional[str], typer.Option()] = None,
) -> None:
    """Ein bereits gerendertes Video als Short hochladen."""
    cfg = Config.load()
    if not cfg.has_youtube_credentials():
        console.print(
            f"[red]Kein client_secret unter {cfg.yt_client_secret}.[/red] "
            "Erst in der Google Cloud Console anlegen."
        )
        raise typer.Exit(code=1)

    from . import publish as publish_mod

    if script_path:
        s = load_script(script_path)
        with console.status("Lade hoch..."):
            res = publish_mod.upload_from_script(
                cfg, video_path, s, privacy=privacy,
            )
    else:
        if not (title and description):
            console.print(
                "[red]--script-path ODER (--title und --description) erforderlich.[/red]"
            )
            raise typer.Exit(code=1)
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        with console.status("Lade hoch..."):
            res = publish_mod.upload(
                cfg, video_path,
                title=title, description=description, tags=tag_list,
                privacy=privacy,
            )

    console.print(f"[green]✓[/green] {res.url} ({res.privacy})")


if __name__ == "__main__":
    app()
