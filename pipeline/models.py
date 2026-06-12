"""Pydantic models for the video script.

`Outline` and `ScenesPayload` are the structured-output schemas sent to
Claude; `Script` is the assembled artifact persisted to script.json.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .vocab import Background, Camera, Emotion, PoseName, Prop


class Line(BaseModel):
    """One spoken dialogue line by one character."""

    character: str = Field(description="Character key from the cast list.")
    text: str = Field(description="The spoken words. 6-30 words, conversational.")
    emotion: Emotion = Field(description="Facial expression while speaking.")
    pose: PoseName = Field(description="Body pose while speaking.")
    prop: Prop = Field(description="Floating icon shown next to the speaker, or 'none'.")
    camera: Camera = Field(description="'shake' for shock beats, 'zoom_in' for emphasis, else 'normal'.")


class Scene(BaseModel):
    """A continuous beat with a fixed background and 1-3 characters."""

    background: Background = Field(description="Background preset for this scene.")
    caption: Optional[str] = Field(
        default=None,
        description="Optional short on-screen text (max 6 words), e.g. a key term or number. Use sparingly.",
    )
    lines: List[Line] = Field(description="2-6 dialogue lines.")


class ChapterPlan(BaseModel):
    title: str = Field(description="Short chapter title (max 6 words).")
    goal: str = Field(description="What the viewer learns/feels in this chapter.")
    open_loop: str = Field(description="The unresolved question that pulls the viewer into the NEXT chapter.")
    beats: List[str] = Field(description="3-6 content beats covered in this chapter.")


class ThumbnailSpec(BaseModel):
    text: str = Field(description="Thumbnail text, 2-4 punchy words, ALL CAPS feel.")
    expression: Emotion = Field(description="Stickman facial expression on the thumbnail.")


class Outline(BaseModel):
    working_title: str
    angle: str = Field(description="The unique angle/promise of this video in one sentence.")
    title_options: List[str] = Field(description="5 click-optimized title variants, each under 60 characters, no clickbait lies.")
    description: str = Field(description="YouTube description: 2-3 sentence teaser. No timestamps (added automatically).")
    tags: List[str] = Field(description="12-18 YouTube tags.")
    thumbnail: ThumbnailSpec
    chapters: List[ChapterPlan]


class Chapter(BaseModel):
    title: str
    scenes: List[Scene]


class ScenesPayload(BaseModel):
    """Schema for the per-section generation calls (hook / chapter / outro)."""

    scenes: List[Scene]


class Script(BaseModel):
    """The full screenplay for one video."""

    topic: str
    language: str
    outline: Outline
    hook: List[Scene]
    chapters: List[Chapter]
    outro: List[Scene]

    def all_scenes(self) -> List[Scene]:
        out: List[Scene] = list(self.hook)
        for ch in self.chapters:
            out.extend(ch.scenes)
        out.extend(self.outro)
        return out

    def word_count(self) -> int:
        return sum(len(l.text.split()) for s in self.all_scenes() for l in s.lines)
