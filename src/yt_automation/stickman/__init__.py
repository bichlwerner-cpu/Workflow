"""Procedural stickman animation engine.

Build a storyboard of :class:`~.scene.Beat` objects (one per spoken sentence),
then call :func:`~.scene.render_storyboard` to produce an animated MP4 with a
dark, neon, fast-paced look. Poses live in :mod:`.poses`, motion in
:mod:`.actions`, drawing in :mod:`.render`.
"""

from .actions import ACTIONS, action_names, get_action
from .render import THEMES, Theme, get_theme
from .scene import Beat, RenderConfig, render_storyboard
from .skeleton import Pose, Skeleton

__all__ = [
    "Beat",
    "RenderConfig",
    "render_storyboard",
    "Skeleton",
    "Pose",
    "Theme",
    "THEMES",
    "get_theme",
    "ACTIONS",
    "get_action",
    "action_names",
]
