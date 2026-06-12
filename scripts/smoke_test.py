"""Offline smoke test — no API keys, no ffmpeg required.

Builds a tiny synthetic narrator-format script with fake voice timing, then
exercises: timeline -> renderer (sample frames as PNGs) -> subtitles ->
thumbnail.

Run:  python scripts/smoke_test.py
Output lands in output/_smoke/ for visual inspection.
"""

import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, load_settings
from pipeline.models import (Actor, Chapter, ChapterPlan, Line, Outline,
                             Scene, Script, ThumbnailSpec)
from pipeline.renderer import FrameRenderer
from pipeline.subtitles import build_cues, write_ass, write_srt
from pipeline.thumbnail import render_thumbnail
from pipeline.timeline import build_timeline, save_timeline_summary, write_voice_track
from pipeline.voiceover import VoicedLine


def fake_alignment(text: str, duration: float):
    """Spread characters evenly across the duration."""
    chars = list(text)
    n = max(1, len(chars))
    starts = [duration * i / n for i in range(n)]
    ends = [duration * (i + 1) / n for i in range(n)]
    return chars, starts, ends


def fake_wav(path: Path, duration: float, sr: int = 44100):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(duration * sr))


def main():
    settings = load_settings()
    outdir = OUTPUT_DIR / "_smoke"
    (outdir / "audio").mkdir(parents=True, exist_ok=True)

    keys = list(settings.characters.keys())
    c1, c2 = keys[0], keys[min(1, len(keys) - 1)]
    c3 = keys[min(2, len(keys) - 1)]

    script = Script(
        topic="smoke test", language="en",
        outline=Outline(
            working_title="Smoke Test", angle="testing",
            title_options=["The Hidden Trick Your Brain Plays On You"],
            description="A test video.", tags=["test"],
            thumbnail=ThumbnailSpec(text="BRAIN TRICK", expression="shocked"),
            chapters=[ChapterPlan(title="The Test Chapter", goal="g", open_loop="o", beats=["b"])],
        ),
        hook=[Scene(background="mountain", caption="The 7 Second Rule", lines=[
            Line(text="You finally decide to chase the goal you postponed for years.",
                 actors=[Actor(character=c1, pose="pointing", emotion="excited", action="enter_left")],
                 prop="none", camera="normal"),
            Line(text="And right before the summit, your own brain hits the brakes.",
                 actors=[Actor(character=c1, pose="sad", emotion="shocked", action="collapse")],
                 prop="none", camera="shake"),
        ])],
        chapters=[Chapter(title="The Test Chapter", scenes=[
            Scene(background="path_split", caption=None, lines=[
                Line(text="Every morning you stand at the same fork without noticing it.",
                     actors=[Actor(character=c1, pose="thinking", emotion="confused", action="approach")],
                     prop="question_mark", camera="normal"),
            ]),
            Scene(background="wall", caption="Study: 1971", lines=[
                Line(text="Researchers watched two groups slam into the exact same wall.",
                     actors=[Actor(character=c1, pose="explaining", emotion="neutral", action="walk_across"),
                             Actor(character=c3, pose="arms_crossed", emotion="smug", action="none")],
                     prop="none", camera="zoom_in"),
            ]),
            Scene(background="graph", caption="93%", lines=[
                Line(text="Ninety-three percent quit at the identical point on this curve.",
                     actors=[], prop="arrow_down", camera="normal"),
            ]),
        ])],
        outro=[Scene(background="gradient_warm", caption=None, lines=[
            Line(text="Subscribe before your brain talks you out of it again.",
                 actors=[Actor(character=c1, pose="celebrating", emotion="excited", action="jump"),
                         Actor(character=c2, pose="presenting", emotion="happy", action="enter_right")],
                 prop="star", camera="normal"),
        ])],
    )

    # Fake voiced lines (0.05s per character of text).
    voiced = []
    flat = []
    for si, scene in enumerate(script.all_scenes()):
        for li, line in enumerate(scene.lines):
            flat.append((si, li, line))
    n_hook_scenes = len(script.hook)
    n_ch_scenes = sum(len(c.scenes) for c in script.chapters)
    for si, li, line in flat:
        dur = max(1.6, len(line.text) * 0.05)
        wav = outdir / "audio" / f"s{si}_l{li}.wav"
        fake_wav(wav, dur)
        chars, starts, ends = fake_alignment(line.text, dur)
        if si < n_hook_scenes:
            ch_idx = -1
        elif si < n_hook_scenes + n_ch_scenes:
            ch_idx = 0
        else:
            ch_idx = 1
        voiced.append(VoicedLine(
            line_id=f"c{ch_idx + 1:02d}_s{si:03d}_l{li:02d}", section="t",
            chapter_index=ch_idx, scene_index=si, text=line.text,
            actors=[a.model_dump() for a in line.actors],
            prop=line.prop, camera=line.camera, wav_path=str(wav),
            duration=dur, chars=chars, char_starts=starts, char_ends=ends,
        ))

    timeline = build_timeline(settings, script, voiced)
    save_timeline_summary(timeline, outdir / "timeline.json")
    write_voice_track(settings, timeline, outdir / "voiceover.wav")
    print(f"timeline OK: {timeline.duration:.1f}s, {len(timeline.scenes)} scenes, "
          f"{len(timeline.chapters)} chapters")

    cues = build_cues(settings, timeline)
    write_ass(settings, cues, outdir / "subtitles.ass")
    write_srt(cues, outdir / "subtitles.srt")
    print(f"subtitles OK: {len(cues)} cues")

    renderer = FrameRenderer(settings, timeline)
    samples = {
        "hook_enter": timeline.scenes[0].lines[0].start + 0.35,
        "hook_collapse": timeline.scenes[0].lines[1].start + 1.0,
        "path_split": timeline.scenes[1].lines[0].start + 0.6,
        "wall_two_actors": timeline.scenes[2].lines[0].start + 1.0,
        "diagram_shot": timeline.scenes[3].lines[0].start + 0.8,
        "outro_jump": timeline.scenes[4].lines[0].start + 0.4,
    }
    for name, t in samples.items():
        renderer.frame_at(t).save(outdir / f"frame_{name}.png")
    print(f"renderer OK: {len(samples)} sample frames written")

    render_thumbnail(settings, script, outdir / "thumbnail.png")
    print("thumbnail OK")
    print(f"\nInspect results in {outdir}")


if __name__ == "__main__":
    main()
