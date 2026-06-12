"""Typer-based CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import footage as footage_mod
from . import stickman as stickman_mod
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
stickman_app = typer.Typer(
    help="Konsistenter Brand-Charakter: Posen-Bilder, Thumbnails, Video-Backgrounds."
)
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
    stickman: Annotated[
        bool,
        typer.Option(
            "--stickman",
            help="Animierter Stick-Man-Charakter als Hintergrund (statt Footage).",
        ),
    ] = False,
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
    elif stickman:
        console.print(f"[bold]Background:[/bold] stickman ({cfg.character_file})")

    with console.status("Rendering..."):
        result = run_from_text(
            cfg, text_path,
            language=language, fmt=fmt,
            background=background, stickman=stickman, music=music,
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
    stickman: Annotated[bool, typer.Option("--stickman")] = False,
    music: Annotated[Optional[Path], typer.Option()] = None,
    word_captions: Annotated[bool, typer.Option()] = False,
) -> None:
    """Voll-automatisch: Claude schreibt Skript -> TTS -> Video. Braucht Anthropic-Key."""
    cfg = Config.load()
    with console.status("Pipeline läuft..."):
        result = run_pipeline(
            cfg, topic,
            duration_seconds=duration, style=style, language=language,
            fmt=fmt, background=background, stickman=stickman, music=music,
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
# Stickman subcommands (Brand-Charakter)
# ============================================================


def _load_spec(cfg: Config) -> stickman_mod.CharacterSpec:
    if not cfg.character_file.exists():
        console.print(
            f"[yellow]Kein Charakter unter {cfg.character_file} -- "
            "lege Default an. Anpassen mit `yt-automation stickman init`.[/yellow]"
        )
    return stickman_mod.CharacterSpec.load_or_create(cfg.character_file)


@stickman_app.command("init")
def stickman_init(
    name: Annotated[str, typer.Option(help="Name des Charakters (Brand-Tag).")] = "Stixx",
    line_color: Annotated[str, typer.Option(help="Strichfarbe, Hex.")] = "#F2F2F2",
    accent_color: Annotated[str, typer.Option(help="Akzentfarbe (Accessoire, Linien).")] = "#FF7A59",
    bg_color: Annotated[str, typer.Option(help="Hintergrundfarbe, Hex.")] = "#0F1115",
    accessory: Annotated[
        str,
        typer.Option(help=f"Eins von: {', '.join(stickman_mod.ACCESSORIES)}."),
    ] = "cap",
    eyes: Annotated[bool, typer.Option(help="Augen zeichnen.")] = True,
    force: Annotated[bool, typer.Option("--force", help="Vorhandene Datei überschreiben.")] = False,
) -> None:
    """Charakter-Datei anlegen -- die 'DNA' deiner Brand (einmalig)."""
    cfg = Config.load()
    if cfg.character_file.exists() and not force:
        console.print(
            f"[red]{cfg.character_file} existiert schon.[/red] "
            "Mit --force überschreiben -- aber Achtung: dann ändert sich "
            "dein Charakter in allen zukünftigen Videos."
        )
        raise typer.Exit(1)
    if accessory not in stickman_mod.ACCESSORIES:
        console.print(f"[red]accessory muss eins von {stickman_mod.ACCESSORIES} sein.[/red]")
        raise typer.Exit(1)

    spec = stickman_mod.CharacterSpec(
        name=name, line_color=line_color, accent_color=accent_color,
        bg_color=bg_color, accessory=accessory, eyes=eyes,
    )
    spec.save(cfg.character_file)
    sheet = stickman_mod.render_pose_sheet(spec, cfg.output_dir / "pose_sheet.png")
    console.print(f"[green]✓[/green] Charakter -> {cfg.character_file}")
    console.print(f"[green]✓[/green] Vorschau  -> {sheet}")


@stickman_app.command("sheet")
def stickman_sheet(
    out: Annotated[Optional[Path], typer.Option()] = None,
) -> None:
    """Übersicht aller Posen als ein Bild rendern."""
    cfg = Config.load()
    spec = _load_spec(cfg)
    path = stickman_mod.render_pose_sheet(spec, out or cfg.output_dir / "pose_sheet.png")
    console.print(f"[green]✓[/green] {path}")


@stickman_app.command("pose")
def stickman_pose(
    pose: Annotated[str, typer.Argument(help=f"Eine von: {', '.join(stickman_mod.POSES)}.")],
    size: Annotated[int, typer.Option(help="Kantenlänge in Pixeln (quadratisch).")] = 1080,
    transparent: Annotated[
        bool, typer.Option("--transparent", help="Transparenter Hintergrund (für Canva etc.).")
    ] = False,
    mirror: Annotated[
        bool, typer.Option("--mirror", help="Gespiegelt (schaut nach links).")
    ] = False,
    out: Annotated[Optional[Path], typer.Option()] = None,
) -> None:
    """Einzelne Pose als PNG rendern (Branding, Profilbild, Overlays)."""
    cfg = Config.load()
    spec = _load_spec(cfg)
    suffix = "_transparent" if transparent else ""
    if mirror:
        suffix += "_left"
    path = stickman_mod.render_pose_image(
        spec, pose,
        out or cfg.output_dir / f"pose_{pose}{suffix}.png",
        size=size, transparent=transparent, mirror=mirror,
    )
    console.print(f"[green]✓[/green] {path}")


@stickman_app.command("library")
def stickman_library(
    size: Annotated[int, typer.Option(help="Kantenlänge der PNGs in Pixeln.")] = 1080,
    out: Annotated[
        Optional[Path],
        typer.Option(help="Zielordner. Default: LIBRARY_DIR (./assets/character_library)."),
    ] = None,
) -> None:
    """Komplette Posen-Bibliothek rendern: alle Posen als transparente PNGs,
    jeweils nach rechts und links schauend, an einem festen Ort."""
    cfg = Config.load()
    spec = _load_spec(cfg)
    target = out or cfg.library_dir
    with console.status(f"Rendere {len(stickman_mod.POSES)} Posen x 2 Richtungen..."):
        paths = stickman_mod.render_library(spec, target, size=size)
    console.print(f"[green]✓[/green] {len(paths)} PNGs -> {target}")
    console.print(f"[green]✓[/green] Übersicht -> {target / '_uebersicht.png'}")


@stickman_app.command("storyboard")
def stickman_storyboard(
    audio: Annotated[Path, typer.Argument(help="Voiceover-Audiodatei (mp3/wav/...).")],
    beat: Annotated[
        float, typer.Option(help="Ziel-Dauer pro Bild in Sekunden. 0.5 ≈ 120 Bilder/Minute."),
    ] = 0.5,
    language: Annotated[str, typer.Option(help="Sprachcode für Whisper.")] = "de",
    size: Annotated[int, typer.Option(help="Kantenlänge der PNGs in Pixeln.")] = 1080,
    out: Annotated[
        Optional[Path],
        typer.Option(help="Zielordner. Default: OUTPUT_DIR/storyboard_<audioname>/."),
    ] = None,
) -> None:
    """Voiceover anhören und alle Bilder fürs Video generieren:
    pro Beat ein transparentes Posen-PNG + storyboard.csv/json mit Timings."""
    from .captions import transcribe
    from .storyboard import render_storyboard

    cfg = Config.load()
    spec = _load_spec(cfg)
    target = out or cfg.output_dir / f"storyboard_{audio.stem}"

    with console.status(f"Whisper ({cfg.whisper_model}) transkribiert {audio.name}..."):
        words = transcribe(cfg, audio, language=language)
    if not words:
        console.print("[red]Whisper hat keine Wörter erkannt -- ist das die richtige Datei?[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] {len(words)} Wörter erkannt")

    with console.status("Rendere Storyboard-Bilder..."):
        beats, paths = render_storyboard(
            spec, words, target, beat_seconds=beat, size=size,
        )

    table = Table(title=f"Storyboard ({len(beats)} Bilder)")
    table.add_column("nr", justify="right")
    table.add_column("zeit")
    table.add_column("pose")
    table.add_column("text")
    preview = beats[:8]
    for b in preview:
        table.add_row(f"{b.index:04d}", f"{b.start:6.2f}-{b.end:6.2f}", b.pose, b.text)
    if len(beats) > len(preview):
        table.add_row("...", "...", "...", f"+ {len(beats) - len(preview)} weitere")
    console.print(table)
    console.print(f"[green]✓[/green] {len(paths)} PNGs -> {target}")
    console.print(f"[green]✓[/green] Timings   -> {target / 'storyboard.csv'}")


@stickman_app.command("thumbnail")
def stickman_thumbnail(
    title: Annotated[str, typer.Argument(help="Titel-Text auf dem Thumbnail.")],
    pose: Annotated[str, typer.Option()] = "point",
    fmt: Annotated[
        VideoFormat, typer.Option("--format", help="landscape (1280x720) oder shorts (1080x1920).")
    ] = VideoFormat.LANDSCAPE,
    out: Annotated[Optional[Path], typer.Option()] = None,
) -> None:
    """Gebrandetes Thumbnail mit Charakter + Titel rendern."""
    cfg = Config.load()
    spec = _load_spec(cfg)
    w, h = (1280, 720) if fmt is VideoFormat.LANDSCAPE else (1080, 1920)
    path = stickman_mod.render_thumbnail(
        spec, title,
        out or cfg.output_dir / "thumbnail.png",
        pose=pose, width=w, height=h,
    )
    console.print(f"[green]✓[/green] {path}")


@stickman_app.command("video")
def stickman_video(
    duration: Annotated[float, typer.Option(help="Länge in Sekunden.")] = 30.0,
    fmt: Annotated[VideoFormat, typer.Option("--format")] = VideoFormat.SHORTS,
    out: Annotated[Optional[Path], typer.Option()] = None,
) -> None:
    """Animierten Hintergrund-Clip rendern (ohne Audio), z.B. zum Testen."""
    cfg = Config.load()
    spec = _load_spec(cfg)
    w, h = (1920, 1080) if fmt is VideoFormat.LANDSCAPE else (1080, 1920)
    with console.status(f"Rendere {duration:.0f}s {fmt.value}..."):
        path = stickman_mod.render_background_video(
            spec, duration, w, h,
            out or cfg.output_dir / "stickman_background.mp4",
        )
    console.print(f"[green]✓[/green] {path}")


if __name__ == "__main__":
    app()
