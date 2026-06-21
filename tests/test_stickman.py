"""Engine tests: skeleton math, poses, actions, frame rendering. No network/ffmpeg."""

from __future__ import annotations

import math

from PIL import Image

from yt_automation.stickman.actions import ACTIONS, action_names, get_action
from yt_automation.stickman.poses import POSES
from yt_automation.stickman.render import draw_figure, get_theme, make_background
from yt_automation.stickman.skeleton import Pose, Skeleton, resolve


def _finite(pt) -> bool:
    return all(math.isfinite(c) for c in pt)


def test_neutral_pose_head_above_feet():
    skel = Skeleton()
    j = resolve(Pose(), skel, root=(500, 500), scale=120)
    assert j.head_center[1] < j.pelvis[1] < j.foot_l[1]
    assert j.head_center[1] < j.foot_r[1]


def test_all_poses_resolve_finite():
    skel = Skeleton()
    for name, pose in POSES.items():
        j = resolve(pose, skel, root=(400, 600), scale=100)
        for pt in (j.head_center, j.pelvis, j.hand_l, j.hand_r, j.foot_l, j.foot_r):
            assert _finite(pt), f"{name} produced non-finite point {pt}"


def test_pose_lerp_endpoints():
    a, b = POSES["stand"], POSES["cheer"]
    assert a.lerp(b, 0.0).torso == a.torso
    assert abs(a.lerp(b, 1.0).arm_r_upper - b.arm_r_upper) < 1e-6


def test_mirror_is_involution():
    p = POSES["point_forward"]
    pm = p.mirrored().mirrored()
    assert abs(pm.arm_r_upper - p.arm_r_upper) < 1e-6
    assert abs(pm.leg_l_upper - p.leg_l_upper) < 1e-6


def test_actions_sample_without_error():
    for name in action_names():
        act = ACTIONS[name]
        for t in (0.0, 0.5, 1.0, 1.7):
            frame = act.sample(t, dur=2.0)
            assert math.isfinite(frame.scale)
            assert math.isfinite(frame.dx)
            assert 0.0 <= frame.motion <= 1.5


def test_get_action_aliases_and_fallback():
    assert get_action("reveal").name == "point"
    assert get_action("anxiety").name == "panic"
    assert get_action("totally-unknown-xyz").name == "idle"
    assert get_action(None).name == "idle"


def test_signature_poses_resolve():
    from yt_automation.stickman.poses import SIGNATURE_POSES
    assert len(SIGNATURE_POSES) >= 4
    for name in SIGNATURE_POSES:
        assert name in POSES
        assert name in ACTIONS                 # also usable as an action
    # signature aliases route correctly
    assert get_action("mindblown").name == "mind_blown"
    assert get_action("cool").name == "lean"


def test_frame_renders_to_image():
    theme = get_theme("midnight")
    img = make_background(360, 640, theme, energy=0.7)
    assert img.size == (360, 640)
    skel = Skeleton()
    scale = (640 * 0.5) / skel.total_height()
    j = resolve(POSES["power"], skel, (180, 380), scale)
    draw_figure(img, j, color=theme.figure, glow_color=theme.accent)
    assert isinstance(img, Image.Image)
    # the figure should put some bright pixels on the dark background
    extrema = img.convert("L").getextrema()
    assert extrema[1] > 200


def test_themes_exist():
    for name in ("midnight", "bloodmoon", "void", "synthwave"):
        assert get_theme(name).name == name
