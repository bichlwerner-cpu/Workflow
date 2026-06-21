"""Time-sampled actions built from key poses.

An :class:`Action` is a list of ``(phase, Frame)`` keyframes. One-shot actions
play once across the beat (phase = elapsed/duration, clamped & held); looping
actions (walk/run/idle) cycle at ``cycles_per_sec``. ``Frame`` carries the pose
plus a figure-local transform so an action can also bob, lean, lunge or spin.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import poses as P
from .skeleton import Pose


@dataclass(frozen=True)
class Frame:
    pose: Pose
    dx: float = 0.0       # root offset, unit space (+ = screen right)
    dy: float = 0.0       # root offset, unit space (+ = down)
    scale: float = 1.0    # figure scale multiplier
    rot: float = 0.0      # whole-figure rotation, degrees (cw)
    motion: float = 0.0   # 0..1 speed-streak amount

    def lerp(self, other: "Frame", t: float) -> "Frame":
        return Frame(
            pose=self.pose.lerp(other.pose, t),
            dx=self.dx + (other.dx - self.dx) * t,
            dy=self.dy + (other.dy - self.dy) * t,
            scale=self.scale + (other.scale - self.scale) * t,
            rot=self.rot + (other.rot - self.rot) * t,
            motion=self.motion + (other.motion - self.motion) * t,
        )


def _ease(t: float) -> float:
    """Smoothstep — natural ease-in/out."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _overshoot(t: float, k: float = 1.7) -> float:
    """Back-ease-out: shoots past 1 then settles. Great for 'pop' poses."""
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return 1.0 + (t * t * ((k + 1) * t + k))


@dataclass
class Action:
    name: str
    keyframes: list[tuple[float, Frame]]
    loop: bool = False
    cycles_per_sec: float = 1.6
    energy: float = 0.5
    travel_x: float = 0.0          # net screen-x travel (fraction of width) over the beat
    ease: str = "ease"             # ease | overshoot | linear

    def sample(self, elapsed: float, dur: float) -> Frame:
        if self.loop:
            phase = (elapsed * self.cycles_per_sec) % 1.0
        else:
            raw = elapsed / dur if dur > 0 else 1.0
            if self.ease == "overshoot":
                phase = _overshoot(raw)
            elif self.ease == "linear":
                phase = max(0.0, min(1.0, raw))
            else:
                phase = _ease(raw)
        return self._at(phase)

    def _at(self, phase: float) -> Frame:
        kfs = self.keyframes
        if phase <= kfs[0][0]:
            return kfs[0][1]
        if phase >= kfs[-1][0]:
            return kfs[-1][1]
        for i in range(len(kfs) - 1):
            t0, f0 = kfs[i]
            t1, f1 = kfs[i + 1]
            if t0 <= phase <= t1:
                local = (phase - t0) / (t1 - t0) if t1 > t0 else 0.0
                return f0.lerp(f1, local)
        return kfs[-1][1]


def _f(pose: Pose, **kw) -> Frame:
    return Frame(pose=pose, **kw)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ACTIONS: dict[str, Action] = {
    "idle": Action(
        "idle",
        [(0.0, _f(P.BREATHE_A)), (0.5, _f(P.BREATHE_B)), (1.0, _f(P.BREATHE_A))],
        loop=True, cycles_per_sec=0.55, energy=0.35,
    ),
    "walk": Action(
        "walk",
        [
            (0.0, _f(P.WALK_CONTACT_R, dy=0.0)),
            (0.25, _f(P.WALK_PASS, dy=-0.02)),
            (0.5, _f(P.WALK_CONTACT_L, dy=0.0)),
            (0.75, _f(P.WALK_PASS, dy=-0.02)),
            (1.0, _f(P.WALK_CONTACT_R, dy=0.0)),
        ],
        loop=True, cycles_per_sec=1.5, energy=0.45, travel_x=0.18,
    ),
    "run": Action(
        "run",
        [
            (0.0, _f(P.RUN_A, dy=0.0, motion=0.5)),
            (0.5, _f(P.RUN_B, dy=-0.03, motion=0.9)),
            (1.0, _f(P.RUN_A, dy=0.0, motion=0.5)),
        ],
        loop=True, cycles_per_sec=2.6, energy=0.85, travel_x=0.28,
    ),
    "point": Action(
        "point",
        [(0.0, _f(P.STAND)), (1.0, _f(P.POINT_FORWARD, scale=1.02))],
        ease="overshoot", energy=0.6,
    ),
    "point_up": Action(
        "point_up",
        [(0.0, _f(P.STAND)), (1.0, _f(P.POINT_UP, dy=-0.02))],
        ease="overshoot", energy=0.65,
    ),
    "think": Action(
        "think",
        [(0.0, _f(P.STAND)), (0.6, _f(P.THINK)), (1.0, _f(P.THINK, dx=0.005))],
        energy=0.3,
    ),
    "idea": Action(
        "idea",
        [(0.0, _f(P.THINK)), (1.0, _f(P.IDEA, dy=-0.03, scale=1.04))],
        ease="overshoot", energy=0.8,
    ),
    "shrug": Action(
        "shrug",
        [(0.0, _f(P.STAND)), (0.5, _f(P.SHRUG, dy=-0.01)), (1.0, _f(P.SHRUG))],
        energy=0.4,
    ),
    "cheer": Action(
        "cheer",
        [
            (0.0, _f(P.STAND)),
            (0.45, _f(P.CHEER, dy=-0.05, scale=1.05)),
            (0.7, _f(P.CHEER, dy=-0.02)),
            (1.0, _f(P.CHEER, dy=-0.04, scale=1.04)),
        ],
        ease="overshoot", energy=0.9,
    ),
    "panic": Action(
        "panic",
        [
            (0.0, _f(P.PANIC, rot=-3)),
            (0.5, _f(P.PANIC.mirrored(), rot=3)),
            (1.0, _f(P.PANIC, rot=-3)),
        ],
        loop=True, cycles_per_sec=3.2, energy=0.95,
    ),
    "facepalm": Action(
        "facepalm",
        [(0.0, _f(P.STAND)), (0.7, _f(P.FACEPALM)), (1.0, _f(P.FACEPALM, dx=0.004))],
        energy=0.45,
    ),
    "punch": Action(
        "punch",
        [
            (0.0, _f(P.POWER)),
            (0.35, _f(P.POWER, dx=-0.03)),                        # wind up (load back)
            (0.55, _f(P.PUNCH, dx=0.05, scale=1.03, motion=0.9)),  # impact
            (1.0, _f(P.POWER, dx=0.01)),
        ],
        energy=0.95,
    ),
    "power": Action(
        "power",
        [
            (0.0, _f(P.STAND)),
            (0.4, _f(P.POWER, dy=0.01, scale=1.03)),
            (0.7, _f(P.POWER, dy=-0.005)),
            (1.0, _f(P.POWER, scale=1.02)),
        ],
        ease="overshoot", energy=0.85,
    ),
    "fall": Action(
        "fall",
        [
            (0.0, _f(P.STAND)),
            (0.35, _f(P.STAND, rot=-4)),
            (0.7, _f(P.CROUCH, rot=3, motion=0.5)),
            (1.0, _f(P.COLLAPSE)),
        ],
        energy=0.7,
    ),
    "jump": Action(
        "jump",
        [
            (0.0, _f(P.STAND)),
            (0.2, _f(P.CROUCH, dy=0.06)),
            (0.45, _f(P.JUMP_TUCK, dy=-0.22, motion=0.7)),
            (0.62, _f(P.AIRBORNE, dy=-0.30)),
            (0.85, _f(P.CROUCH, dy=0.05, motion=0.4)),
            (1.0, _f(P.STAND)),
        ],
        energy=0.85,
    ),
    "stomp": Action(
        "stomp",
        [
            (0.0, _f(P.STAND, dy=-0.04)),
            (0.3, _f(P.POWER, dy=-0.06, scale=1.04)),
            (0.45, _f(P.POWER, dy=0.02, scale=1.05, motion=0.8)),
            (1.0, _f(P.POWER)),
        ],
        energy=0.9,
    ),
    # --- signature / character actions ---
    "mind_blown": Action(
        "mind_blown",
        [
            (0.0, _f(P.STAND)),
            (0.45, _f(P.MIND_BLOWN, dy=-0.05, scale=1.06, motion=0.6)),
            (0.7, _f(P.MIND_BLOWN, dy=-0.01)),
            (1.0, _f(P.MIND_BLOWN, dy=-0.03, scale=1.03)),
        ],
        ease="overshoot", energy=0.95,
    ),
    "salute": Action(
        "salute",
        [(0.0, _f(P.STAND)), (0.6, _f(P.SALUTE)), (1.0, _f(P.SALUTE, dx=0.004))],
        energy=0.6,
    ),
    "finger_guns": Action(
        "finger_guns",
        [(0.0, _f(P.STAND)), (1.0, _f(P.FINGER_GUNS, scale=1.02))],
        ease="overshoot", energy=0.75,
    ),
    "mic_drop": Action(
        "mic_drop",
        [
            (0.0, _f(P.POWER)),
            (0.5, _f(P.MIC_DROP, scale=1.03)),
            (0.7, _f(P.MIC_DROP, dy=0.01, motion=0.6)),
            (1.0, _f(P.MIC_DROP)),
        ],
        ease="overshoot", energy=0.9,
    ),
    "lean": Action(
        "lean",
        [(0.0, _f(P.STAND)), (0.6, _f(P.LEAN)), (1.0, _f(P.LEAN, dx=0.004))],
        energy=0.55,
    ),
    "arms_crossed": Action(
        "arms_crossed",
        [(0.0, _f(P.STAND)), (0.6, _f(P.ARMS_CROSSED)), (1.0, _f(P.ARMS_CROSSED))],
        energy=0.6,
    ),
}

# Friendly aliases the script generator may emit.
ALIASES = {
    "explain": "point", "reveal": "point", "warn": "point_up",
    "realize": "idea", "confused": "shrug", "win": "cheer",
    "defeat": "fall", "collapse": "fall", "stressed": "panic",
    "anxiety": "panic", "facepalm": "facepalm", "fight": "punch",
    "strong": "power", "confident": "power", "leap": "jump",
    "emphasis": "stomp", "intense": "stomp", "walk": "walk", "run": "run",
    "idle": "idle", "stand": "idle", "think": "think",
    "mindblown": "mind_blown", "shocked": "mind_blown", "wow": "mind_blown",
    "cool": "lean", "casual": "lean", "fingerguns": "finger_guns",
    "drop": "mic_drop", "micdrop": "mic_drop", "crossed": "arms_crossed",
    "skeptical": "arms_crossed", "respect": "salute",
}


def get_action(name: str | None) -> Action:
    if not name:
        return ACTIONS["idle"]
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    return ACTIONS.get(key, ACTIONS["idle"])


def action_names() -> list[str]:
    return sorted(ACTIONS.keys())
