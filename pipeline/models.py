"""Pydantic models for the video script.

`Outline` and `ScenesPayload` are the structured-output schemas sent to
Claude; `Script` is the assembled artifact persisted to script.json.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .vocab import (ACTIONS, BACKGROUNDS, CAMERAS, EMOTIONS, POSES, PROPS,
                    SHOTS, Action, Background, Camera, Emotion, PoseName,
                    Prop, Shot)


class Actor(BaseModel):
    """Stage direction for one silent on-screen character during a beat."""

    character: str = Field(description="Character key from the cast list.")
    pose: PoseName = Field(default="idle", description="Body pose during this beat.")
    emotion: Emotion = Field(default="neutral", description="Facial expression during this beat.")
    action: Action = Field(default="none", description="Movement: entrances, exits, walks, jump, collapse — or 'none'.")

    # Providers without enforced enums (e.g. Gemini free tier) occasionally
    # emit values outside the vocabulary; coerce instead of failing the video.
    @field_validator("pose", mode="before")
    @classmethod
    def _coerce_pose(cls, v):
        return v if v in POSES else "idle"

    @field_validator("emotion", mode="before")
    @classmethod
    def _coerce_emotion(cls, v):
        return v if v in EMOTIONS else "neutral"

    @field_validator("action", mode="before")
    @classmethod
    def _coerce_action(cls, v):
        return v if v in ACTIONS else "none"


class Line(BaseModel):
    """One narration beat: what the narrator says + what plays on screen."""

    text: str = Field(description="Narrator voiceover for this beat. 6-16 words, punchy spoken rhythm.")
    actors: List[Actor] = Field(
        default_factory=list,
        description="0-2 silent stickman actors. Prefer EXACTLY ONE (the protagonist). Empty list = diagram/prop-only shot. Two only for genuine contrast (you vs. the inner critic).",
    )
    prop: Prop = Field(default="none", description="Floating icon for this beat, or 'none'.")
    camera: Camera = Field(default="normal", description="'shake'/'punch' for shock beats, 'zoom_in'/'zoom_out' for emphasis, else 'normal'.")
    shot: Shot = Field(default="auto", description="Framing: 'closeup' (big head, lip-synced) for emotional/direct lines, 'wide' for movement/metaphor, 'insert' for a pure icon, else 'auto'.")

    @field_validator("prop", mode="before")
    @classmethod
    def _coerce_prop(cls, v):
        return v if v in PROPS else "none"

    @field_validator("camera", mode="before")
    @classmethod
    def _coerce_camera(cls, v):
        return v if v in CAMERAS else "normal"

    @field_validator("shot", mode="before")
    @classmethod
    def _coerce_shot(cls, v):
        return v if v in SHOTS else "auto"

    @field_validator("actors", mode="before")
    @classmethod
    def _limit_actors(cls, v):
        return (v or [])[:2]


class Scene(BaseModel):
    """A continuous beat with a fixed background and 1-3 characters."""

    background: Background = Field(default="void", description="Background preset for this scene.")
    caption: Optional[str] = Field(
        default=None,
        description="Optional short on-screen text (max 6 words), e.g. a key term or number. Use sparingly.",
    )
    lines: List[Line] = Field(description="1-4 narration beats; the visual staging changes with every beat.")

    @field_validator("background", mode="before")
    @classmethod
    def _coerce_background(cls, v):
        return v if v in BACKGROUNDS else "void"


class ChapterPlan(BaseModel):
    title: str = Field(description="Short chapter title (max 6 words).")
    goal: str = Field(description="What the viewer learns/feels in this chapter.")
    open_loop: str = Field(description="The unresolved question that pulls the viewer into the NEXT chapter.")
    beats: List[str] = Field(description="3-6 content beats covered in this chapter.")


class ThumbnailSpec(BaseModel):
    text: str = Field(description="Thumbnail text, 2-4 punchy words, ALL CAPS feel.")
    expression: Emotion = Field(default="shocked", description="Stickman facial expression on the thumbnail.")

    @field_validator("expression", mode="before")
    @classmethod
    def _coerce_expression(cls, v):
        return v if v in EMOTIONS else "shocked"


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
