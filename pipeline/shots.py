"""Shot resolution — the editing brain shared by renderer and audio.

Every narration beat becomes exactly one *shot* (a framed camera composition).
The script's director can force a framing via `line.shot`; otherwise we derive
one from the beat's content so the cut rhythm stays lively even on a plain
script. Both the frame renderer and the sound-effect engine call
`resolve_shots()` so that hard cuts, zooms and swooshes land on the same
frames.
"""

from __future__ import annotations

from typing import Dict, List

# Actions that move a character across the stage -> always want a wide shot.
MOVING_ACTIONS = {
    "enter_left", "enter_right", "exit_left", "exit_right",
    "walk_across", "approach", "retreat", "jump", "collapse",
}

SHOT_WIDE = "wide"
SHOT_MEDIUM = "medium"
SHOT_CLOSEUP = "closeup"
SHOT_INSERT = "insert"


def resolve_line(shot: str, actors: List[dict], prop: str, camera: str,
                 text: str, prev: str) -> str:
    """Resolve one beat to a concrete shot type."""
    n = len(actors)
    has_move = any(a.get("action", "none") in MOVING_ACTIONS for a in actors)

    if shot == "closeup":
        return SHOT_CLOSEUP if n >= 1 else SHOT_INSERT
    if shot == "wide":
        return SHOT_WIDE if n >= 1 else SHOT_INSERT
    if shot == "medium":
        return SHOT_MEDIUM if n >= 1 else SHOT_INSERT
    if shot == "insert":
        return SHOT_INSERT

    # --- auto -------------------------------------------------------------
    if n == 0:
        return SHOT_INSERT
    if n >= 2 or has_move:
        base = SHOT_WIDE
    else:
        short = len(text.split()) <= 9
        emphatic = camera in ("shake", "zoom_in", "punch") or short
        base = SHOT_CLOSEUP if emphatic else SHOT_MEDIUM

    # Don't cut from a close-up straight into another close-up: a change of
    # framing is what makes the edit feel sharp.
    if base == SHOT_CLOSEUP and prev == SHOT_CLOSEUP:
        base = SHOT_MEDIUM
    return base


def resolve_shots(timeline) -> Dict[str, str]:
    """Map every line_id in the timeline to its resolved shot type."""
    out: Dict[str, str] = {}
    prev = ""
    for scene in timeline.scenes:
        for tl in scene.lines:
            v = tl.voiced
            shot = resolve_line(
                getattr(v, "shot", "auto"), v.actors, v.prop, v.camera, v.text, prev)
            out[v.line_id] = shot
            prev = shot
    return out
