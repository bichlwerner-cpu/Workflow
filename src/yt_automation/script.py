"""Generate a structured video script via Claude Opus 4.7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import Config

Style = Literal["explainer", "story", "listicle", "tutorial"]


class ScriptSection(BaseModel):
    heading: str = Field(description="Section heading (1-5 words).")
    voiceover: str = Field(
        description="The exact text to be spoken. Plain prose, no stage directions."
    )
    on_screen_text: str | None = Field(
        default=None,
        description="Optional short caption shown on screen (max 60 chars).",
    )


class VideoScript(BaseModel):
    title: str = Field(description="YouTube title, max 70 chars, hook-driven.")
    description: str = Field(description="YouTube description, 2-4 sentences.")
    tags: list[str] = Field(description="5-10 lowercase YouTube tags.")
    hook: str = Field(description="Opening line, spoken first. Max 15 words.")
    sections: list[ScriptSection] = Field(
        description="3-7 ordered sections that make up the body."
    )
    call_to_action: str = Field(description="Closing line. Max 20 words.")


SYSTEM_PROMPT = """You are a senior YouTube scriptwriter.

You write tight, retention-optimized scripts for short-to-mid-form videos (60-180 seconds).

Hard rules:
- Voiceover text must be natural spoken prose, never bracketed stage directions, never markdown.
- Open with a hook that creates curiosity or stakes within the first sentence.
- Cut filler. Every sentence must earn its place.
- Match the requested language exactly (default German if the topic is German).
- On-screen text is optional and should only appear when it adds information the voiceover does not carry.
- Tags are lowercase, single words or short phrases, comma-free.
"""


def generate_script(
    cfg: Config,
    topic: str,
    *,
    duration_seconds: int = 90,
    style: Style = "explainer",
    language: str = "de",
) -> VideoScript:
    import anthropic  # imported lazily so the free/offline path needs no SDK

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    user_prompt = (
        f"Topic: {topic}\n"
        f"Target duration: {duration_seconds} seconds (~{duration_seconds * 2.5:.0f} words of voiceover).\n"
        f"Style: {style}\n"
        f"Language: {language}\n\n"
        "Produce the full script as structured JSON."
    )

    response = client.messages.parse(
        model=cfg.anthropic_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.anthropic_effort},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
        output_format=VideoScript,
    )

    return response.parsed_output


def save_script(script: VideoScript, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")


def load_script(path: Path) -> VideoScript:
    return VideoScript.model_validate_json(path.read_text(encoding="utf-8"))


def script_to_voiceover_text(script: VideoScript) -> str:
    parts = [script.hook]
    parts.extend(s.voiceover for s in script.sections)
    parts.append(script.call_to_action)
    return "\n\n".join(p.strip() for p in parts if p.strip())


def from_text(path: Path) -> VideoScript:
    """Parse a plain-text script file into a VideoScript.

    Format (alles außer dem Body ist optional):

        # Mein Titel
        description: Optionale Beschreibung
        tags: tag1, tag2, tag3

        Erster Absatz wird zum Hook.

        Mittlere Absätze werden zu Sections.

        Letzter Absatz wird zum Call-to-Action.

    Absätze werden durch Leerzeilen getrennt. Bei nur einem Absatz
    landet alles in einer Section.
    """
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"{path} ist leer.")

    title = path.stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled"
    description = ""
    tags: list[str] = []

    lines = raw.splitlines()
    body_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            body_idx = i + 1
            break
        low = stripped.lower()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
        elif low.startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
        elif low.startswith("description:"):
            description = stripped.split(":", 1)[1].strip()
        elif low.startswith("tags:"):
            tags = [
                t.strip()
                for t in stripped.split(":", 1)[1].split(",")
                if t.strip()
            ]
        else:
            body_idx = i
            break
    else:
        body_idx = len(lines)

    body = "\n".join(lines[body_idx:]).strip()
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        raise ValueError(
            f"{path} enthält keinen Voiceover-Text (nur Header gefunden)."
        )

    if len(paragraphs) == 1:
        hook = ""
        section_paras = [paragraphs[0]]
        cta = ""
    elif len(paragraphs) == 2:
        hook = paragraphs[0]
        section_paras = []
        cta = paragraphs[1]
    else:
        hook = paragraphs[0]
        section_paras = paragraphs[1:-1]
        cta = paragraphs[-1]

    sections = [
        ScriptSection(heading=f"Section {i + 1}", voiceover=text)
        for i, text in enumerate(section_paras)
    ]
    if not sections:
        sections = [ScriptSection(heading="Body", voiceover=hook or cta or paragraphs[0])]
        if len(paragraphs) == 1:
            hook = ""
            cta = ""

    if not description:
        description = title
    if not tags:
        tags = [w.lower() for w in title.split() if w][:5]

    return VideoScript(
        title=title,
        description=description,
        tags=tags,
        hook=hook,
        sections=sections,
        call_to_action=cta,
    )
