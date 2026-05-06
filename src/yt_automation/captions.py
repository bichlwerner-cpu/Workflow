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


# BGR hex (ASS uses &HBBGGRR), bright high-contrast colors that survive YouTube compression.
HIGHLIGHT_COLORS = [
    "&H00FFFFFF",  # white
    "&H0000F0FF",  # yellow
    "&H005AC8FF",  # orange
    "&H0066FF66",  # green
    "&H00FF66FF",  # magenta
]


def write_ass(
    words: list[Word],
    out_path: Path,
    *,
    width: int,
    height: int,
    font_size: int | None = None,
    words_per_line: int = 1,
    rotate_colors: bool = True,
) -> Path:
    """Render words to ASS with one chunk on screen at a time.

    Defaults: heavy black outline, large bold font, color rotation per chunk
    for a dynamic TikTok/Reels look.
    """
    if font_size is None:
        font_size = 96 if height > width else 60

    margin_v = int(height * 0.42) if height > width else 80
    outline = 6 if height > width else 4

    style_lines = [
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    ]
    palette = HIGHLIGHT_COLORS if rotate_colors else [HIGHLIGHT_COLORS[0]]
    for i, color in enumerate(palette):
        style_lines.append(
            f"Style: C{i},Arial Black,{font_size},{color},&H000000FF,"
            f"&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{outline},2,2,"
            f"60,60,{margin_v},1"
        )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        + "\n".join(style_lines)
        + "\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )

    lines = [header]

    chunks: list[list[Word]] = []
    for i in range(0, len(words), words_per_line):
        chunks.append(words[i : i + words_per_line])

    for idx, chunk in enumerate(chunks):
        if not chunk:
            continue
        start = chunk[0].start
        end = chunk[-1].end
        text = " ".join(w.text for w in chunk).upper().replace("\n", " ")
        text = text.replace("{", "(").replace("}", ")")
        style = f"C{idx % len(palette)}"
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}\n"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path
