"""Voiceover -> nummerierte Posen-Bilder zum manuellen Layering im Editor.

Whisper liefert wortgenaue Timestamps. Die Wörter werden in "Beats"
gruppiert (Standard ~0.5s, an Satzenden wird immer geschnitten), jeder Beat
bekommt eine Pose: erst per Keyword-Matching auf den gesprochenen Text,
sonst rotierend aus neutralen Gesten. Pro Beat wird ein transparentes PNG
gerendert (Dateiname enthält Nummer, Zeitfenster und Pose) plus ein
CSV/JSON-Manifest mit allen Timings.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .stickman import POSES, CharacterSpec, _breathe, character_image


class TimedWord(Protocol):
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Beat:
    index: int
    start: float
    end: float
    text: str
    pose: str


# Reihenfolge zählt: erster Treffer gewinnt. Substring-Match auf den
# kleingeschriebenen Beat-Text, deshalb funktionieren Wortstämme
# ("freu" matcht "freue", "freust", "Freude").
POSE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("wave", ("hallo", "hi ", "hey", "tschüss", "willkommen", "servus", "ciao")),
    ("shocked", ("krass", "wow", "unglaublich", "schock", "plötzlich", "boom",
                 "verrückt", "wahnsinn", "extrem", "explod", "riesig")),
    ("celebrate", ("gewonnen", "geschafft", "erfolg", "sieg", "endlich",
                   "perfekt", "jackpot", "win", "feier", "bester")),
    ("facepalm", ("dumm", "fehler", "falsch", "peinlich", "katastrophe",
                  "fail", "vergessen", "oh nein")),
    ("angry", ("wütend", "sauer", "hass", "ärger", "nervt", "wut", "zornig")),
    ("sad", ("traurig", "leider", "verloren", "schade", "schlimm", "wein",
             "pech", "deprimier", "einsam")),
    ("happy", ("glücklich", "freu", "liebe", "geil", "spaß", "lachen",
               "genial", "wunderbar")),
    ("think", ("warum", "wieso", "denk", "überleg", "frage", "vielleicht",
               "hmm", "grübel", "rätsel", "was wäre")),
    ("shrug", ("egal", "keine ahnung", "wer weiß", "naja", "irgendwie",
               "wahrscheinlich", "angeblich")),
    ("run", ("schnell", "renn", "lauf", "flieh", "sofort", "hetz", "spurt")),
    ("jump", ("spring", "hüpf", "action", "los geht")),
    ("sit", ("sitz", "warte", "chill", "entspann", "gemütlich")),
    ("lie", ("schlaf", "lieg", "müde", "bett", "erschöpft", "umgefallen")),
    ("point_up", ("oben", "hoch", "steigt", "wichtig", "merk dir", "nummer",
                  "platz", "erstens", "zweitens", "drittens", "wächst")),
    ("point_down", ("unten", "runter", "fällt", "sinkt", "weniger",
                    "schrumpft", "verliert")),
    ("point", ("schau", "guck", "hier", "zeig", "genau das", "siehst du")),
    ("explain", ("weil", "denn", "bedeutet", "erklär", "nämlich", "heißt",
                 "funktioniert", "grund")),
]

# Fallback-Rotation für Beats ohne Keyword-Treffer
NEUTRAL_ROTATION = ("explain", "present", "point", "idle", "think")

_SENTENCE_END = (".", "!", "?", ":")


def build_beats(words: list[TimedWord], *, beat_seconds: float = 0.5) -> list[Beat]:
    """Wörter in Beats gruppieren; Posen werden direkt zugewiesen."""
    groups: list[list[TimedWord]] = []
    current: list[TimedWord] = []
    for w in words:
        current.append(w)
        too_long = (current[-1].end - current[0].start) >= beat_seconds
        sentence_end = w.text.rstrip().endswith(_SENTENCE_END)
        if too_long or sentence_end:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    beats: list[Beat] = []
    prev_pose = ""
    for i, group in enumerate(groups):
        text = " ".join(w.text for w in group)
        pose = _pose_for(text, prev_pose, i)
        beats.append(Beat(
            index=i + 1,
            start=group[0].start,
            end=group[-1].end,
            text=text,
            pose=pose,
        ))
        prev_pose = pose
    return beats


def _pose_for(text: str, prev_pose: str, beat_index: int) -> str:
    lowered = f" {text.lower()} "
    for pose, keywords in POSE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return pose
    pose = NEUTRAL_ROTATION[beat_index % len(NEUTRAL_ROTATION)]
    if pose == prev_pose:
        pose = NEUTRAL_ROTATION[(beat_index + 1) % len(NEUTRAL_ROTATION)]
    return pose


def render_storyboard(
    spec: CharacterSpec,
    words: list[TimedWord],
    out_dir: Path,
    *,
    beat_seconds: float = 0.5,
    size: int = 1080,
) -> tuple[list[Beat], list[Path]]:
    """Pro Beat ein transparentes PNG + Manifest (CSV und JSON) schreiben."""
    beats = build_beats(words, beat_seconds=beat_seconds)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for beat in beats:
        # Mini-Variation pro Beat (Atmung), damit gleiche Posen
        # nicht pixelidentisch wiederholt werden
        pose = _breathe(POSES[beat.pose], beat.start * 1.7)
        img = character_image(spec, pose, size=size)
        path = out_dir / (
            f"{beat.index:04d}__{beat.start:06.2f}-{beat.end:06.2f}"
            f"__{beat.pose}.png"
        )
        img.save(path, "PNG")
        paths.append(path)

    with (out_dir / "storyboard.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["nr", "file", "start", "end", "duration", "pose", "text"])
        for beat, path in zip(beats, paths):
            writer.writerow([
                beat.index, path.name,
                f"{beat.start:.2f}", f"{beat.end:.2f}",
                f"{beat.end - beat.start:.2f}",
                beat.pose, beat.text,
            ])

    (out_dir / "storyboard.json").write_text(
        json.dumps(
            [
                {
                    "nr": b.index, "file": p.name,
                    "start": round(b.start, 2), "end": round(b.end, 2),
                    "pose": b.pose, "text": b.text,
                }
                for b, p in zip(beats, paths)
            ],
            indent=2, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return beats, paths


__all__ = [
    "Beat",
    "NEUTRAL_ROTATION",
    "POSE_KEYWORDS",
    "build_beats",
    "render_storyboard",
]
