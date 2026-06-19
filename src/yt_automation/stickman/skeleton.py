"""Stickman skeleton: forward kinematics + pose model.

A figure is a small set of bones whose *absolute* world angles fully describe a
pose. Angles are in degrees, measured **clockwise from straight up**:

    0   = up        (0, -1)
    90  = right     (+1, 0)
    180 = down      (0, +1)
    270 = left      (-1, 0)

so an endpoint is ``start + length * (sin a, -cos a)``.

Storing absolute angles (instead of joint coordinates) keeps bone lengths
constant when we linearly interpolate between two poses, which is what makes the
animation read as a jointed figure rather than a melting blob.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

Point = tuple[float, float]


@dataclass(frozen=True)
class Skeleton:
    """Bone lengths in abstract units (1 unit == spine length)."""

    spine: float = 1.0
    head_radius: float = 0.34
    neck: float = 0.12          # gap between top of spine and head centre
    upper_arm: float = 0.55
    forearm: float = 0.52
    thigh: float = 0.64
    shin: float = 0.60
    # cosmetic line weights, relative to scale
    limb_weight: float = 0.085
    torso_weight: float = 0.10

    def total_height(self) -> float:
        """Approx height from foot to top of head for a neutral stance."""
        return self.spine + self.neck + 2 * self.head_radius + self.thigh + self.shin


@dataclass(frozen=True)
class Pose:
    """Absolute world angles (degrees) for every bone, plus posture offsets.

    ``pelvis_dx`` / ``pelvis_dy`` shift the root in *unit* space (e.g. crouch,
    jump, lean) and ``squash`` scales vertical extent for anticipation/impact.
    """

    torso: float = 0.0          # pelvis -> neck
    head: float = 0.0           # extra head tilt on top of torso
    arm_l_upper: float = 202.0
    arm_l_fore: float = 200.0
    arm_r_upper: float = 158.0
    arm_r_fore: float = 160.0
    leg_l_upper: float = 191.0
    leg_l_lower: float = 189.0
    leg_r_upper: float = 169.0
    leg_r_lower: float = 171.0
    pelvis_dx: float = 0.0
    pelvis_dy: float = 0.0
    squash: float = 1.0

    def lerp(self, other: "Pose", t: float) -> "Pose":
        t = max(0.0, min(1.0, t))
        out = {}
        for f in fields(self):
            a = getattr(self, f.name)
            b = getattr(other, f.name)
            if f.name in ("torso", "head") or f.name.startswith(("arm_", "leg_")):
                out[f.name] = _angle_lerp(a, b, t)
            else:
                out[f.name] = a + (b - a) * t
        return Pose(**out)

    def mirrored(self) -> "Pose":
        """Flip left<->right so the figure faces the other way."""
        return replace(
            self,
            torso=-self.torso,
            head=-self.head,
            arm_l_upper=-self.arm_r_upper,
            arm_l_fore=-self.arm_r_fore,
            arm_r_upper=-self.arm_l_upper,
            arm_r_fore=-self.arm_l_fore,
            leg_l_upper=-self.leg_r_upper,
            leg_l_lower=-self.leg_r_lower,
            leg_r_upper=-self.leg_l_upper,
            leg_r_lower=-self.leg_l_lower,
            pelvis_dx=-self.pelvis_dx,
        )


@dataclass(frozen=True)
class Joints:
    """Resolved world-space pixel coordinates for one drawn figure."""

    pelvis: Point
    neck: Point
    head_center: Point
    head_radius: float
    elbow_l: Point
    hand_l: Point
    elbow_r: Point
    hand_r: Point
    knee_l: Point
    foot_l: Point
    knee_r: Point
    foot_r: Point


def _dir(angle_deg: float) -> Point:
    a = math.radians(angle_deg)
    return (math.sin(a), -math.cos(a))


def _step(start: Point, angle_deg: float, length: float) -> Point:
    dx, dy = _dir(angle_deg)
    return (start[0] + dx * length, start[1] + dy * length)


def _angle_lerp(a: float, b: float, t: float) -> float:
    """Interpolate the short way around the circle."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * t


def resolve(
    pose: Pose,
    skel: Skeleton,
    root: Point,
    scale: float,
) -> Joints:
    """Forward-kinematics: turn a pose into world-space pixel coordinates.

    ``root`` is where the *pelvis* sits. ``scale`` is pixels per unit.
    """
    sq = pose.squash
    px = root[0] + pose.pelvis_dx * scale
    py = root[1] + pose.pelvis_dy * scale
    pelvis = (px, py)

    neck = _step(pelvis, pose.torso, skel.spine * scale * sq)  # torso 0deg points up
    head_center = _step(neck, pose.torso + pose.head, (skel.neck + skel.head_radius) * scale * sq)

    elbow_l = _step(neck, pose.arm_l_upper, skel.upper_arm * scale)
    hand_l = _step(elbow_l, pose.arm_l_fore, skel.forearm * scale)
    elbow_r = _step(neck, pose.arm_r_upper, skel.upper_arm * scale)
    hand_r = _step(elbow_r, pose.arm_r_fore, skel.forearm * scale)

    knee_l = _step(pelvis, pose.leg_l_upper, skel.thigh * scale * sq)
    foot_l = _step(knee_l, pose.leg_l_lower, skel.shin * scale * sq)
    knee_r = _step(pelvis, pose.leg_r_upper, skel.thigh * scale * sq)
    foot_r = _step(knee_r, pose.leg_r_lower, skel.shin * scale * sq)

    return Joints(
        pelvis=pelvis,
        neck=neck,
        head_center=head_center,
        head_radius=skel.head_radius * scale * sq,
        elbow_l=elbow_l,
        hand_l=hand_l,
        elbow_r=elbow_r,
        hand_r=hand_r,
        knee_l=knee_l,
        foot_l=foot_l,
        knee_r=knee_r,
        foot_r=foot_r,
    )
