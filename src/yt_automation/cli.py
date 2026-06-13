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
    help="YouTube content pipeline: text/topic -> script -> TTS -> video.",
)
footage_app = typer.Typer(help="Footage assets (download, clip, list).")
app.add_typer(footage_app, name="footage")
mascot_app = typer.Typer(help="2D-Brand-Charakter: konsistente Posen/Ausdrücke als Bilder.")
app.add_typer(mascot_app, name="mascot")
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
    """Nur Skript via Claude oder Gemini (SCRIPT_PROVIDER). Braucht den passenden Key."""
    cfg = Config.load()
    cfg.require_script_llm()
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
# Mascot subcommands (consistent 2D character)
# ============================================================


@mascot_app.command("list")
def mascot_list() -> None:
    """Alle verfügbaren Posen, Ausdrücke und Lip-Sync-Mundformen auflisten."""
    from .character import EXPRESSIONS, POSES, VISEMES

    table = Table(title="Mascot-Bibliothek")
    table.add_column("Posen")
    table.add_column("Ausdrücke")
    table.add_column("Visemes (Lip-Sync)")
    rows = max(len(POSES), len(EXPRESSIONS), len(VISEMES))
    poses, exprs, vis = list(POSES), list(EXPRESSIONS), list(VISEMES)
    for i in range(rows):
        table.add_row(
            poses[i] if i < len(poses) else "",
            exprs[i] if i < len(exprs) else "",
            vis[i] if i < len(vis) else "",
        )
    console.print(table)


def _apply_brand(cfg: Config) -> Optional[str]:
    """Set the active palette from config and return the accessory (or None)."""
    from .character import PALETTES, use_palette

    if cfg.mascot_palette in PALETTES:
        use_palette(cfg.mascot_palette)
    return cfg.mascot_accessory or None


@mascot_app.command("sheet")
def mascot_sheet(
    out: Annotated[Path, typer.Option(help="Ziel-PNG.")] = Path("out/mascot/contact_sheet.png"),
    cols: Annotated[int, typer.Option(help="Spalten im Raster.")] = 4,
) -> None:
    """Kontaktblatt aller Posen + Ausdrücke als ein PNG."""
    from .character import contact_sheet

    cfg = Config.load()
    accessory = _apply_brand(cfg)
    with console.status("Rendere Kontaktblatt..."):
        contact_sheet(out, cols=cols, accessory=accessory)
    console.print(f"[green]✓[/green] {out}")


@mascot_app.command("export")
def mascot_export(
    out: Annotated[Path, typer.Option(help="Ziel-Ordner für die Bilder-Bibliothek.")] = Path("out/mascot"),
    width: Annotated[int, typer.Option(help="PNG-Breite in px (Höhe folgt 600:760).")] = 1200,
    full: Annotated[bool, typer.Option("--full", help="Komplette Pose×Ausdruck-Matrix.")] = False,
    svg: Annotated[bool, typer.Option("--svg/--no-svg", help="Editierbare SVG-Quellen mitschreiben.")] = True,
) -> None:
    """Transparente PNGs aller Posen/Ausdrücke/Visemes für den Editor exportieren."""
    from .character import export_library

    cfg = Config.load()
    accessory = _apply_brand(cfg)
    with console.status("Exportiere Bilder-Bibliothek..."):
        files = export_library(out, width=width, full=full, svg_too=svg, accessory=accessory)
    console.print(f"[green]✓[/green] {len(files)} Bilder -> {out}  "
                  f"[dim]({cfg.mascot_palette}{' + ' + cfg.mascot_accessory if accessory else ''})[/dim]")
    console.print("[dim]Transparent, hochauflösend. Für Editor: poses/, expressions/, visemes/[/dim]")


@mascot_app.command("pose")
def mascot_pose(
    pose: Annotated[str, typer.Argument(help="Pose-Name (siehe `mascot list`).")] = "idle",
    expression: Annotated[str, typer.Argument(help="Ausdruck-Name.")] = "neutral",
    out: Annotated[Path, typer.Option(help="Ziel-PNG.")] = Path("out/mascot/pose.png"),
    width: Annotated[int, typer.Option()] = 1200,
    background: Annotated[Optional[str], typer.Option(help="Hex-Farbe, z.B. '#F4F1EA'. Sonst transparent.")] = None,
) -> None:
    """Eine einzelne Pose+Ausdruck als PNG rendern."""
    from .character import EXPRESSIONS, POSES, build_svg, rasterize

    cfg = Config.load()
    accessory = _apply_brand(cfg)
    if pose not in POSES:
        raise typer.BadParameter(f"Pose '{pose}' unbekannt. `mascot list` zeigt alle.")
    if expression not in EXPRESSIONS:
        raise typer.BadParameter(f"Ausdruck '{expression}' unbekannt. `mascot list` zeigt alle.")
    svg = build_svg(POSES[pose], EXPRESSIONS[expression], bg=background, accessory=accessory)
    rasterize(svg, out, width=width, transparent=background is None)
    console.print(f"[green]✓[/green] {out}")


def _render_mascot_ref(cfg: Config, pose_name: str) -> Path:
    """Render a vector mascot pose to a PNG to use as a Gemini reference image."""
    from .character import EXPRESSIONS, POSES, _POSE_FACE, build_svg, rasterize

    accessory = _apply_brand(cfg)
    if pose_name not in POSES:
        raise typer.BadParameter(f"Pose '{pose_name}' unbekannt. `mascot list` zeigt alle.")
    expr = EXPRESSIONS[_POSE_FACE.get(pose_name, "neutral")]
    ref = cfg.output_dir / "figure" / "_ref.png"
    rasterize(build_svg(POSES[pose_name], expr, bg="#FFFFFF", accessory=accessory),
              ref, width=900, transparent=False)
    return ref


@mascot_app.command("gen")
def mascot_gen(
    prompt: Annotated[str, typer.Argument(help="Was soll die Figur tun? (Aktion/Szene)")],
    ref: Annotated[Optional[list[Path]], typer.Option("--ref", help="Referenzbild(er) der Figur (mehrfach möglich).")] = None,
    from_mascot: Annotated[Optional[str], typer.Option("--from-mascot", help="Vektor-Pose als Referenz nutzen, z.B. 'idle'.")] = None,
    out: Annotated[Path, typer.Option(help="Ziel-PNG.")] = Path("out/figure/gen.png"),
) -> None:
    """Ein konsistentes Bild der Figur via Gemini (Nano Banana) erzeugen."""
    from .imagegen import build_prompt, generate_figure

    cfg = Config.load()
    refs = list(ref or [])
    if from_mascot:
        refs.append(_render_mascot_ref(cfg, from_mascot))
    full = build_prompt(prompt) if refs else prompt
    with console.status(f"Gemini {cfg.gemini_image_model}..."):
        generate_figure(cfg, full, out, references=refs or None)
    console.print(f"[green]✓[/green] {out}")


@mascot_app.command("gen-set")
def mascot_gen_set(
    ref: Annotated[Optional[list[Path]], typer.Option("--ref", help="Referenzbild(er) der Figur.")] = None,
    from_mascot: Annotated[Optional[str], typer.Option("--from-mascot", help="Vektor-Pose als Referenz, z.B. 'idle'.")] = None,
    out: Annotated[Path, typer.Option(help="Ziel-Ordner.")] = Path("out/figure"),
    background: Annotated[str, typer.Option(help="Hintergrund-Beschreibung für den Prompt.")] = "plain flat",
) -> None:
    """Komplettes konsistentes Posen-Set aus einer Referenz-Figur erzeugen."""
    from .imagegen import POSE_PROMPTS, generate_pose_set

    cfg = Config.load()
    refs = list(ref or [])
    if from_mascot:
        refs.append(_render_mascot_ref(cfg, from_mascot))
    if not refs:
        raise typer.BadParameter("Mindestens --ref <bild> oder --from-mascot <pose> nötig.")
    console.print(f"[bold]{len(POSE_PROMPTS)} Posen[/bold] via {cfg.gemini_image_model}")
    with console.status("Generiere Set (kostet pro Bild)..."):
        files = generate_pose_set(cfg, refs, out, background=background)
    console.print(f"[green]✓[/green] {len(files)} Bilder -> {out}")


@mascot_app.command("talk")
def mascot_talk(
    text_path: Annotated[Path, typer.Argument(help="Plain-Text-Skript-Datei.")],
    pose: Annotated[str, typer.Option(help="Sprech-Pose, z.B. explain, idle, point_up.")] = "explain",
    expression: Annotated[str, typer.Option(help="Augen/Brauen-Basis (Mund kommt vom Lip-Sync).")] = "neutral",
    captions: Annotated[bool, typer.Option("--captions/--no-captions", help="Word-Captions einbrennen.")] = True,
    language: Annotated[str, typer.Option(help="Sprachcode für Whisper.")] = "de",
    out: Annotated[Path, typer.Option(help="Ziel-MP4.")] = Path("out/talking_mascot.mp4"),
) -> None:
    """Lip-synctes Talking-Mascot-Video: Skript → Voiceover → Mund-Sync → MP4."""
    from .character import EXPRESSIONS, POSES
    from .pipeline import run_talking_mascot

    cfg = Config.load()
    if pose not in POSES:
        raise typer.BadParameter(f"Pose '{pose}' unbekannt. `mascot list` zeigt alle.")
    if expression not in EXPRESSIONS:
        raise typer.BadParameter(f"Ausdruck '{expression}' unbekannt. `mascot list` zeigt alle.")
    console.print(
        f"[bold]TTS:[/bold] {cfg.tts_provider}  [bold]Pose:[/bold] {pose}  "
        f"[bold]Brand:[/bold] {cfg.mascot_palette}+{cfg.mascot_accessory or 'none'}"
    )
    with console.status("Voiceover → Whisper → Lip-Sync → Render..."):
        res = run_talking_mascot(
            cfg, text_path, pose=pose, base_expr=expression,
            language=language, captions=captions, out=out,
        )
    console.print(f"[green]✓[/green] Video    -> {res.video_path}")
    console.print(f"[green]✓[/green] Timeline -> {cfg.output_dir / 'lipsync.json'} [dim](für Editor)[/dim]")


if __name__ == "__main__":
    app()
