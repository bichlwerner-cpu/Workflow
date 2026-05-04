"""Word-level captions via faster-whisper, rendered as ASS subtitle file.

Generates TikTok/Shorts-style captions: one or two words on screen at a time,
big bold font with stroke, centered. Each word stays on screen for its exact
spoken duration as detected by Whisper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from .config import Config


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


def transcribe(cfg: Config, audio_path: Path, language: str = "de") -> list[Word]:
    """Run Whisper with word timestamps. CPU/int8 by default for portability."""
    model = WhisperModel(cfg.whisper_model, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )
    words: list[Word] = []
    for seg in segments:
        if not seg.words:
            continue
        for w in seg.words:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append(Word(text=text, start=float(w.start), end=float(w.end)))
    return words


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - (h * 3600 + m * 60)
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(
    words: list[Word],
    out_path: Path,
    *,
    width: int,
    height: int,
    font_size: int | None = None,
    words_per_line: int = 1,
) -> Path:
    """Render words to ASS with one chunk highlighted at a time."""
    if font_size is None:
        font_size = 90 if height > width else 60

    margin_v = int(height * 0.42) if height > width else 80

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,5,2,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    chunks: list[list[Word]] = []
    for i in range(0, len(words), words_per_line):
        chunks.append(words[i : i + words_per_line])

    for chunk in chunks:
        if not chunk:
            continue
        start = chunk[0].start
        end = chunk[-1].end
        text = " ".join(w.text for w in chunk).upper().replace("\n", " ")
        text = text.replace("{", "(").replace("}", ")")
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}\n"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path
