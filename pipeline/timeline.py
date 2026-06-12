"""Timeline: absolute timings for every line/scene/chapter + master voice track.

The timeline is the single source of truth shared by the renderer (what to
draw at time t), the subtitle generator (cue offsets) and the metadata stage
(YouTube chapter timestamps).
"""

from __future__ import annotations

import bisect
import json
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import Settings
from .models import Script
from .voiceover import VoicedLine

# Characters that should not open the mouth (pauses inside a line).
_SILENT_CHARS = set(" \t\n.,;:!?…—-–'\"()")


@dataclass
class TimedLine:
    voiced: VoicedLine
    start: float
    end: float

    def mouth_open(self, t_abs: float) -> bool:
        """True when audible speech happens at absolute time t (lip flap)."""
        t = t_abs - self.start
        starts = self.voiced.char_starts
        if not starts:
            return self.start <= t_abs <= self.end  # no alignment -> always open
        # any voiced character overlapping a small window around t
        lo, hi = t - 0.045, t + 0.045
        i = bisect.bisect_right(starts, hi) - 1
        while i >= 0 and self.voiced.char_ends[i] >= lo:
            if self.voiced.chars[i] not in _SILENT_CHARS:
                return True
            i -= 1
        return False


@dataclass
class TimedScene:
    scene_index: int
    chapter_index: int
    background: str
    caption: Optional[str]
    characters: List[str]          # unique, order of first appearance
    lines: List[TimedLine]
    start: float
    end: float

    def active_line(self, t: float) -> Optional[TimedLine]:
        for tl in self.lines:
            if tl.start <= t <= tl.end:
                return tl
        return None


@dataclass
class TimedChapter:
    index: int                     # -1 = hook, n = outro
    title: str
    start: float
    end: float
    show_card: bool


@dataclass
class Timeline:
    scenes: List[TimedScene]
    chapters: List[TimedChapter]
    duration: float
    _scene_starts: List[float] = field(default_factory=list)

    def __post_init__(self):
        self._scene_starts = [s.start for s in self.scenes]

    def scene_at(self, t: float) -> TimedScene:
        i = bisect.bisect_right(self._scene_starts, t) - 1
        return self.scenes[max(0, i)]

    def chapter_at(self, t: float) -> Optional[TimedChapter]:
        for ch in self.chapters:
            if ch.start <= t < ch.end:
                return ch
        return None


def build_timeline(settings: Settings, script: Script, voiced: List[VoicedLine]) -> Timeline:
    line_gap = float(settings.get("audio", "line_gap", default=0.18))
    scene_gap = float(settings.get("audio", "scene_gap", default=0.55))
    chapter_gap = float(settings.get("audio", "chapter_gap", default=0.9))
    lead_in = float(settings.get("audio", "lead_in", default=0.5))
    tail = float(settings.get("audio", "tail", default=2.0))

    # Group voiced lines by scene_index (they are already in playback order).
    scenes_voiced: List[List[VoicedLine]] = []
    for v in voiced:
        while len(scenes_voiced) <= v.scene_index:
            scenes_voiced.append([])
        scenes_voiced[v.scene_index].append(v)

    all_scenes = script.all_scenes()
    if len(all_scenes) != len(scenes_voiced):
        raise RuntimeError(
            f"Script has {len(all_scenes)} scenes but voice manifest covers "
            f"{len(scenes_voiced)} — re-run the voice stage."
        )

    t = lead_in
    timed_scenes: List[TimedScene] = []
    prev_chapter = None
    for si, (scene, vlines) in enumerate(zip(all_scenes, scenes_voiced)):
        if not vlines:
            continue
        ch_idx = vlines[0].chapter_index
        if prev_chapter is not None:
            t += chapter_gap if ch_idx != prev_chapter else scene_gap
        prev_chapter = ch_idx

        scene_start = t
        timed_lines: List[TimedLine] = []
        for j, v in enumerate(vlines):
            if j > 0:
                t += line_gap
            timed_lines.append(TimedLine(voiced=v, start=t, end=t + v.duration))
            t += v.duration

        chars: List[str] = []
        for v in vlines:
            if v.character not in chars:
                chars.append(v.character)

        timed_scenes.append(TimedScene(
            scene_index=si, chapter_index=ch_idx, background=scene.background,
            caption=scene.caption, characters=chars, lines=timed_lines,
            start=scene_start, end=t,
        ))

    duration = t + tail

    # Chapter spans (hook = -1, outro = len(chapters)).
    chapters: List[TimedChapter] = []
    titles = {-1: "Hook", len(script.chapters): "Outro"}
    titles.update({i: ch.title for i, ch in enumerate(script.chapters)})
    by_chapter: dict = {}
    for s in timed_scenes:
        by_chapter.setdefault(s.chapter_index, []).append(s)
    for idx in sorted(by_chapter):
        group = by_chapter[idx]
        chapters.append(TimedChapter(
            index=idx, title=titles.get(idx, f"Chapter {idx + 1}"),
            start=group[0].start, end=group[-1].end,
            show_card=0 <= idx < len(script.chapters),
        ))
    if chapters:
        chapters[-1].end = duration

    return Timeline(scenes=timed_scenes, chapters=chapters, duration=duration)


def write_voice_track(settings: Settings, timeline: Timeline, out_path: Path) -> Path:
    """Assemble all line WAVs into one sample-accurate mono master track."""
    sr = settings.sample_rate
    total_frames = int(round(timeline.duration * sr))

    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sr)
        cursor = 0
        for scene in timeline.scenes:
            for tl in scene.lines:
                start_frame = int(round(tl.start * sr))
                if start_frame > cursor:
                    out.writeframes(b"\x00\x00" * (start_frame - cursor))
                    cursor = start_frame
                with wave.open(tl.voiced.wav_path, "rb") as src:
                    if src.getframerate() != sr or src.getnchannels() != 1 or src.getsampwidth() != 2:
                        raise RuntimeError(
                            f"{tl.voiced.wav_path}: expected mono 16-bit {sr} Hz "
                            f"(got {src.getnchannels()}ch {src.getsampwidth() * 8}bit "
                            f"{src.getframerate()} Hz). Check audio.output_format."
                        )
                    data = src.readframes(src.getnframes())
                out.writeframes(data)
                cursor += len(data) // 2
        if total_frames > cursor:
            out.writeframes(b"\x00\x00" * (total_frames - cursor))
    return out_path


def save_timeline_summary(timeline: Timeline, path: Path) -> None:
    """Human-inspectable dump of the computed timing."""
    data = {
        "duration": round(timeline.duration, 3),
        "chapters": [
            {"index": c.index, "title": c.title,
             "start": round(c.start, 3), "end": round(c.end, 3)}
            for c in timeline.chapters
        ],
        "scenes": [
            {"index": s.scene_index, "chapter": s.chapter_index,
             "background": s.background, "characters": s.characters,
             "start": round(s.start, 3), "end": round(s.end, 3),
             "lines": [
                 {"id": tl.voiced.line_id, "character": tl.voiced.character,
                  "start": round(tl.start, 3), "end": round(tl.end, 3),
                  "text": tl.voiced.text}
                 for tl in s.lines
             ]}
            for s in timeline.scenes
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
