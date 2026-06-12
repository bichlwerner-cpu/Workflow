"""Controlled vocabulary shared by the script writer (LLM schema) and renderer.

The Literal types below are enforced by Claude's structured outputs, so every
value the script writer emits is guaranteed to be drawable by the renderer.
Add a value here only together with rendering support in renderer/stickman.
"""

from typing import Literal, get_args

Emotion = Literal[
    "neutral", "happy", "sad", "shocked", "angry",
    "thinking", "confused", "smug", "curious", "excited",
]

PoseName = Literal[
    "idle", "talking", "explaining", "pointing", "pointing_up",
    "thinking", "shocked", "happy", "sad", "facepalm", "shrug",
    "arms_crossed", "presenting", "walking", "mind_blown", "celebrating",
]

Background = Literal[
    "void", "paper", "chalkboard", "gradient_warm",
    "gradient_cool", "graph", "stage", "night",
]

Prop = Literal[
    "none", "lightbulb", "question_mark", "exclamation", "heart",
    "clock", "arrow_up", "arrow_down", "money", "star", "target",
    "eye", "brain",
]

Camera = Literal["normal", "zoom_in", "shake"]

EMOTIONS = list(get_args(Emotion))
POSES = list(get_args(PoseName))
BACKGROUNDS = list(get_args(Background))
PROPS = list(get_args(Prop))
CAMERAS = list(get_args(Camera))
