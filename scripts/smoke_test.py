"""Offline smoke test — no API keys, no ffmpeg required.

Builds a tiny synthetic script with fake voice timing, then exercises:
timeline -> renderer (sample frames as PNGs) -> subtitles -> thumbnail.

Run:  python scripts/smoke_test.py
Output lands in output/_smoke/ for visual inspection.
"""

import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import OUTPUT_DIR, load_settings
from pipeline.models import (Chapter, ChapterPlan, Line, Outline, Scene,
                             Script, ThumbnailSpec)
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

    char_keys = list(settings.characters.keys())
    c1, c2 = char_keys[0], char_keys[min(1, len(char_keys) - 1)]

    script = Script(
        topic="smoke test", language="en",
        outline=Outline(
            working_title="Smoke Test", angle="testing",
            title_options=["The Hidden Trick Your Brain Plays On You"],
            description="A test video.", tags=["test"],
            thumbnail=ThumbnailSpec(text="BRAIN TRICK", expression="shocked"),
            chapters=[ChapterPlan(title="The Test Chapter", goal="g", open_loop="o", beats=["b"])],
        ),
        hook=[Scene(background="void", caption="The 7 Second Rule", lines=[
            Line(character=c1, text="Your brain is lying to you right now.",
                 emotion="shocked", pose="pointing", prop="brain", camera="shake"),
            Line(character=c2, text="Oh come on, that sounds dramatic.",
                 emotion="smug", pose="arms_crossed", prop="none", camera="normal"),
        ])],
        chapters=[Chapter(title="The Test Chapter", scenes=[
            Scene(background="chalkboard", caption=None, lines=[
                Line(character=c1, text="Here is the experiment that proves it.",
                     emotion="happy", pose="explaining", prop="lightbulb", camera="zoom_in"),
            ]),
            Scene(background="night", caption="Study: 1971", lines=[
                Line(character=c2, text="Fine. Show me the evidence then.",
                     emotion="thinking", pose="thinking", prop="question_mark", camera="normal"),
            ]),
        ])],
        outro=[Scene(background="gradient_warm", caption=None, lines=[
            Line(character=c1, text="Subscribe before your brain talks you out of it.",
                 emotion="excited", pose="celebrating", prop="star", camera="normal"),
        ])],
    )

    # Fake voiced lines (0.05s per character of text).
    voiced = []
    flat = []
    for si, scene in enumerate(script.all_scenes()):
        for li, line in enumerate(scene.lines):
            flat.append((si, li, line))
    for si, li, line in flat:
        dur = max(1.2, len(line.text) * 0.05)
        wav = outdir / "audio" / f"s{si}_l{li}.wav"
        fake_wav(wav, dur)
        chars, starts, ends = fake_alignment(line.text, dur)
        ch_idx = -1 if si == 0 else (0 if si <= 2 else 1)
        voiced.append(VoicedLine(
            line_id=f"c{ch_idx + 1:02d}_s{si:03d}_l{li:02d}", section="t",
            chapter_index=ch_idx, scene_index=si, character=line.character,
            text=line.text, emotion=line.emotion, pose=line.pose,
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
    samples = [0.2, timeline.scenes[0].lines[0].start + 0.3,
               timeline.scenes[1].start + 0.2, timeline.scenes[2].start + 0.5,
               timeline.scenes[3].start + 0.5]
    for i, t in enumerate(samples):
        img = renderer.frame_at(t)
        img.save(outdir / f"frame_{i}_{t:.1f}s.png")
    print(f"renderer OK: {len(samples)} sample frames written")

    render_thumbnail(settings, script, outdir / "thumbnail.png")
    print("thumbnail OK")
    print(f"\nInspect results in {outdir}")


if __name__ == "__main__":
    main()
