"""Command line interface.

  python -m pipeline produce --topic "Why your brain sabotages you"
  python -m pipeline script  --topic "..."          # script only
  python -m pipeline voice   --slug <slug>          # voiceover only
  python -m pipeline render  --slug <slug>          # video only
  python -m pipeline thumbnail --slug <slug>
  python -m pipeline upload  --slug <slug>
  python -m pipeline list-voices
  python -m pipeline validate
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from .config import OUTPUT_DIR, Settings, load_settings, slugify
from .models import Script


def log(msg: str) -> None:
    ts = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _outdir(slug: str) -> Path:
    d = OUTPUT_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_script(outdir: Path) -> Script:
    path = outdir / "script.json"
    if not path.exists():
        raise SystemExit(f"No script.json in {outdir} — run the script stage first.")
    return Script.model_validate_json(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- stages

def stage_script(settings: Settings, topic: str, outdir: Path, force: bool) -> Script:
    path = outdir / "script.json"
    if path.exists() and not force:
        log("script: script.json exists, skipping (use --force to regenerate)")
        return _load_script(outdir)
    from .script_writer import write_script
    log(f"script: generating for topic: {topic}")
    script = write_script(settings, topic, log=log)
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
    log(f"script: saved {path}")
    return script


def stage_voice(settings: Settings, script: Script, outdir: Path, force: bool):
    from .voiceover import synthesize_script
    if force:
        for f in (outdir / "audio").glob("*.align.json") if (outdir / "audio").exists() else []:
            f.unlink()
    log("voice: synthesizing with ElevenLabs (cached lines are skipped) ...")
    return synthesize_script(settings, script, outdir, log=log)


def stage_timeline(settings: Settings, script: Script, voiced, outdir: Path):
    from .timeline import build_timeline, save_timeline_summary, write_voice_track
    timeline = build_timeline(settings, script, voiced)
    save_timeline_summary(timeline, outdir / "timeline.json")
    write_voice_track(settings, timeline, outdir / "voiceover.wav")
    log(f"timeline: {timeline.duration / 60:.1f} min total")
    return timeline


def stage_subtitles(settings: Settings, timeline, outdir: Path):
    from .subtitles import build_cues, write_ass, write_srt
    cues = build_cues(settings, timeline)
    ass = write_ass(settings, cues, outdir / "subtitles.ass")
    write_srt(cues, outdir / "subtitles.srt")
    log(f"subtitles: {len(cues)} cues")
    return ass


def stage_render(settings: Settings, timeline, outdir: Path, ass_path, force: bool) -> Path:
    out = outdir / "video.mp4"
    if out.exists() and not force:
        log("render: video.mp4 exists, skipping (use --force to re-render)")
        return out
    from .assembler import encode_video
    from .renderer import FrameRenderer
    renderer = FrameRenderer(settings, timeline)
    burn = bool(settings.get("subtitles", "burn_in", default=True))
    log(f"render: {settings.width}x{settings.height}@{settings.fps} "
        f"({timeline.duration / 60:.1f} min, subtitles {'burned' if burn else 'external'})")
    encode_video(settings, renderer.frames(log=log), outdir / "voiceover.wav",
                 out, ass_path if burn else None, log=log)
    log(f"render: saved {out}")
    return out


def stage_thumbnail(settings: Settings, script: Script, outdir: Path) -> Path:
    from .thumbnail import render_thumbnail
    path = render_thumbnail(settings, script, outdir / "thumbnail.png")
    log(f"thumbnail: saved {path}")
    return path


def stage_metadata(settings: Settings, script: Script, timeline, outdir: Path) -> dict:
    from .metadata import build_metadata
    meta = build_metadata(settings, script, timeline, outdir)
    log(f"metadata: \"{meta['title']}\"")
    return meta


def stage_upload(outdir: Path) -> None:
    from .upload import upload_video
    meta = json.loads((outdir / "metadata.json").read_text(encoding="utf-8"))
    upload_video(meta, outdir / "video.mp4", outdir / "thumbnail.png", log=log)


# ------------------------------------------------------------------ commands

def cmd_produce(args) -> None:
    settings = load_settings()
    if not args.topic and not args.slug:
        raise SystemExit("produce needs --topic (new video) or --slug (resume).")
    slug = args.slug or slugify(args.topic)
    outdir = _outdir(slug)
    log(f"=== producing '{slug}' -> {outdir}")

    if args.topic:
        script = stage_script(settings, args.topic, outdir, args.force)
    else:
        script = _load_script(outdir)

    voiced = stage_voice(settings, script, outdir, args.force)
    timeline = stage_timeline(settings, script, voiced, outdir)
    ass = stage_subtitles(settings, timeline, outdir)
    stage_render(settings, timeline, outdir, ass, args.force)
    stage_thumbnail(settings, script, outdir)
    stage_metadata(settings, script, timeline, outdir)

    if args.upload:
        stage_upload(outdir)
    else:
        log("done. Review video.mp4 + thumbnail.png + description.txt, then:")
        log(f"  python -m pipeline upload --slug {slug}")


def cmd_script(args) -> None:
    settings = load_settings()
    slug = args.slug or slugify(args.topic)
    stage_script(settings, args.topic, _outdir(slug), force=True)


def cmd_voice(args) -> None:
    settings = load_settings()
    outdir = _outdir(args.slug)
    script = _load_script(outdir)
    voiced = stage_voice(settings, script, outdir, args.force)
    stage_timeline(settings, script, voiced, outdir)


def cmd_render(args) -> None:
    settings = load_settings()
    outdir = _outdir(args.slug)
    script = _load_script(outdir)
    from .voiceover import load_manifest
    voiced = load_manifest(outdir)
    timeline = stage_timeline(settings, script, voiced, outdir)
    ass = stage_subtitles(settings, timeline, outdir)
    stage_render(settings, timeline, outdir, ass, force=True)


def cmd_thumbnail(args) -> None:
    settings = load_settings()
    outdir = _outdir(args.slug)
    stage_thumbnail(settings, _load_script(outdir), outdir)


def cmd_metadata(args) -> None:
    settings = load_settings()
    outdir = _outdir(args.slug)
    script = _load_script(outdir)
    from .voiceover import load_manifest
    from .timeline import build_timeline
    timeline = build_timeline(settings, script, load_manifest(outdir))
    stage_metadata(settings, script, timeline, outdir)


def cmd_upload(args) -> None:
    stage_upload(_outdir(args.slug))


def cmd_list_voices(args) -> None:
    settings = load_settings()
    from .voiceover import ElevenLabsClient
    voices = ElevenLabsClient(settings).list_voices()
    print(f"{'voice_id':<24} {'category':<12} name")
    print("-" * 60)
    for v in voices:
        print(f"{v.get('voice_id', ''):<24} {v.get('category', ''):<12} {v.get('name', '')}")


def cmd_validate(args) -> None:
    import os
    import shutil
    settings = load_settings()
    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        mark = "OK " if passed else "FAIL"
        print(f"[{mark}] {label}" + (f" — {hint}" if not passed and hint else ""))
        ok = ok and passed

    provider = str(settings.get("llm", "provider", default="gemini")).lower()
    if provider == "claude":
        check("ANTHROPIC_API_KEY set", bool(os.environ.get("ANTHROPIC_API_KEY")),
              "needed for script generation (llm.provider: claude)")
    else:
        check("GEMINI_API_KEY set", bool(os.environ.get("GEMINI_API_KEY")),
              "free key: https://aistudio.google.com/apikey")
    check("ELEVENLABS_API_KEY set", bool(os.environ.get("ELEVENLABS_API_KEY")),
          "needed for voiceover")
    check("ffmpeg on PATH", shutil.which("ffmpeg") is not None,
          "install ffmpeg (apt/brew/choco)")
    check("display font found", settings.font_path() is not None,
          "drop a bold .ttf into assets/fonts/ (see settings.yaml fonts list)")
    check("characters registered", len(settings.characters) > 0)
    for c in settings.characters.values():
        check(f"voice_id for '{c.key}'", bool(c.voice.voice_id))

    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            from .voiceover import ElevenLabsClient
            voices = {v["voice_id"] for v in ElevenLabsClient(settings).list_voices()}
            for c in settings.characters.values():
                check(f"voice '{c.key}' exists in your ElevenLabs account",
                      c.voice.voice_id in voices,
                      "premade voices work even if not listed; verify with a test synth")
        except SystemExit:
            raise
        except Exception as e:
            check("ElevenLabs API reachable", False, str(e))

    sys.exit(0 if ok else 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Stickman Studio — automated long-form YouTube pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("produce", help="full pipeline: script -> voice -> video -> thumbnail -> metadata")
    p.add_argument("--topic", help="video topic (omit to resume an existing --slug)")
    p.add_argument("--slug", help="output folder name (default: derived from topic)")
    p.add_argument("--force", action="store_true", help="regenerate all stages")
    p.add_argument("--upload", action="store_true", help="upload to YouTube when done")
    p.set_defaults(func=cmd_produce)

    p = sub.add_parser("script", help="generate the script only")
    p.add_argument("--topic", required=True)
    p.add_argument("--slug")
    p.set_defaults(func=cmd_script)

    for name, fn, help_text in [
        ("voice", cmd_voice, "synthesize voiceover for an existing script"),
        ("render", cmd_render, "render + encode the video"),
        ("thumbnail", cmd_thumbnail, "generate the thumbnail"),
        ("metadata", cmd_metadata, "generate title/description/tags"),
        ("upload", cmd_upload, "upload video.mp4 to YouTube"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--slug", required=True)
        if name == "voice":
            p.add_argument("--force", action="store_true")
        p.set_defaults(func=fn)

    p = sub.add_parser("list-voices", help="list ElevenLabs voices in your account")
    p.set_defaults(func=cmd_list_voices)

    p = sub.add_parser("validate", help="check keys, ffmpeg, fonts and voice config")
    p.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
