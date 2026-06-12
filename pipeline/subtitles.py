"""Subtitles from ElevenLabs character alignment.

Produces:
  - subtitles.ass — styled captions for burn-in, optional per-word karaoke
    highlight (the spoken word lights up in the accent color)
  - subtitles.srt — plain subtitles to upload as YouTube closed captions
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import Settings
from .timeline import Timeline
from .utils import hex_to_rgb

_WORD_BREAK = set(" \t\n")


@dataclass
class Word:
    text: str
    start: float  # absolute seconds
    end: float


@dataclass
class Cue:
    words: List[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _words_from_line(tl) -> List[Word]:
    v = tl.voiced
    if not v.chars:
        return [Word(text=v.text, start=tl.start, end=tl.end)]
    words: List[Word] = []
    buf, w_start, w_end = "", 0.0, 0.0
    for ch, s, e in zip(v.chars, v.char_starts, v.char_ends):
        if ch in _WORD_BREAK:
            if buf:
                words.append(Word(buf, tl.start + w_start, tl.start + w_end))
                buf = ""
            continue
        if not buf:
            w_start = s
        buf += ch
        w_end = e
    if buf:
        words.append(Word(buf, tl.start + w_start, tl.start + w_end))
    return words


def build_cues(settings: Settings, timeline: Timeline) -> List[Cue]:
    max_words = int(settings.get("subtitles", "max_words_per_cue", default=5))
    max_chars = int(settings.get("subtitles", "max_chars_per_cue", default=36))

    cues: List[Cue] = []
    for scene in timeline.scenes:
        for tl in scene.lines:
            current: List[Word] = []
            for w in _words_from_line(tl):
                if current:
                    too_long = (len(current) >= max_words
                                or len(" ".join(x.text for x in current)) + len(w.text) + 1 > max_chars
                                or w.start - current[-1].end > 0.6)
                    if too_long:
                        cues.append(Cue(current))
                        current = []
                current.append(w)
            if current:
                cues.append(Cue(current))
    return cues


# ------------------------------------------------------------------------- ASS

def _ass_color(rgb, alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def _ass_ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def write_ass(settings: Settings, cues: List[Cue], path: Path) -> Path:
    accent = hex_to_rgb(settings.accent)
    karaoke = bool(settings.get("subtitles", "karaoke", default=True))
    font = settings.get("subtitles", "font_name", default="DejaVu Sans")
    size = int(settings.get("subtitles", "font_size", default=60))
    margin_v = int(settings.get("subtitles", "margin_v", default=72))

    # With karaoke, the "sung" word takes PrimaryColour (accent) while the
    # rest stays SecondaryColour (white). Without karaoke, primary is white.
    primary = _ass_color(accent if karaoke else (255, 255, 255))
    secondary = _ass_color((255, 255, 255))

    header = f"""[Script Info]
Title: Stickman Studio captions
ScriptType: v4.00+
PlayResX: {settings.width}
PlayResY: {settings.height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{primary},{secondary},&H00101014,&H96000000,-1,0,0,0,100,100,1,0,1,4,1,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for i, cue in enumerate(cues):
        end = cue.end + 0.08
        if i + 1 < len(cues):
            end = min(end, cues[i + 1].start - 0.01)
        end = max(end, cue.start + 0.2)
        if karaoke:
            parts = []
            for j, w in enumerate(cue.words):
                nxt = cue.words[j + 1].start if j + 1 < len(cue.words) else end
                dur_cs = max(1, int(round((nxt - w.start) * 100)))
                parts.append(f"{{\\k{dur_cs}}}{_ass_escape(w.text)}")
            text = " ".join(parts)
        else:
            text = _ass_escape(cue.text)
        events.append(f"Dialogue: 0,{_ass_ts(cue.start)},{_ass_ts(end)},Cap,,0,0,0,,{text}")

    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------------- SRT

def _srt_ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues: List[Cue], path: Path) -> Path:
    blocks = []
    for i, cue in enumerate(cues, 1):
        end = cue.end + 0.08
        if i < len(cues):
            end = min(end, cues[i].start - 0.01)
        blocks.append(f"{i}\n{_srt_ts(cue.start)} --> {_srt_ts(max(end, cue.start + 0.2))}\n{cue.text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path
