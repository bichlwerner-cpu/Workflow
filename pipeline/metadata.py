"""YouTube metadata: title, description with chapter timestamps, tags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .config import Settings
from .models import Script
from .timeline import Timeline
from .utils import fmt_timestamp


def build_metadata(settings: Settings, script: Script, timeline: Timeline, outdir: Path) -> dict:
    outline = script.outline

    chapters: List[str] = ["0:00 Intro"]
    for ch in timeline.chapters:
        if ch.show_card:
            chapters.append(f"{fmt_timestamp(ch.start)} {ch.title}")

    footer = str(settings.get("youtube", "description_footer", default="") or "").strip()
    parts = [outline.description.strip(), "", "Chapters:", *chapters]
    if footer:
        parts += ["", footer]
    description = "\n".join(parts)

    meta = {
        "title": outline.title_options[0] if outline.title_options else outline.working_title,
        "title_options": outline.title_options,
        "description": description,
        "tags": outline.tags,
        "category_id": str(settings.get("youtube", "category_id", default="27")),
        "privacy_status": str(settings.get("youtube", "privacy_status", default="private")),
        "made_for_kids": bool(settings.get("youtube", "made_for_kids", default=False)),
        "duration_seconds": round(timeline.duration, 1),
        "word_count": script.word_count(),
    }

    (outdir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "description.txt").write_text(description, encoding="utf-8")
    return meta
