"""Montage + brand character tests. No network/ffmpeg."""

from __future__ import annotations

from PIL import Image

from yt_automation.stickman.character import (
    PRESETS,
    character_names,
    draw_accessories,
    get_character,
)
from yt_automation.stickman.montage import (
    FRAMINGS,
    MontageConfig,
    Shot,
    beats_to_shots,
    render_shot,
)
from yt_automation.stickman.render import (
    build_vignette_mask,
    draw_figure,
    get_theme,
    make_base_background,
)
from yt_automation.stickman.poses import POSES
from yt_automation.stickman.scene import Beat
from yt_automation.stickman.skeleton import Skeleton, resolve


def test_character_presets_resolve():
    assert get_character(None).name == "Iko"
    assert get_character("boss").headwear == "crown"
    assert get_character("nope-xyz").name == "Iko"  # fallback
    assert set(character_names()) == set(PRESETS.keys())


def test_draw_accessories_marks_pixels():
    theme = get_theme("midnight")
    skel = Skeleton()
    img = make_base_background(360, 640, theme, energy=0.6)
    j = resolve(POSES["stand"], skel, (180, 380), (640 * 0.5) / skel.total_height())
    before = img.copy()
    draw_figure(img, j, color=(240, 244, 255), glow_color=theme.accent)
    draw_accessories(img, j, get_character("iko"))  # headband + shades
    assert img.tobytes() != before.tobytes()


def test_beats_to_shots_cover_durations():
    beats = [
        Beat("a sentence here", action="point", keyword="A", intensity=0.9, start=0.0, duration=4.0),
        Beat("another one", action="run", keyword=None, intensity=0.6, start=4.0, duration=2.0),
    ]
    cfg = MontageConfig(shot_len=1.8)
    shots = beats_to_shots(beats, cfg)
    assert len(shots) >= 3
    total = sum(s.duration for s in shots)
    assert abs(total - 6.0) < 1e-6                 # shots tile the beats exactly
    assert all(s.framing in FRAMINGS for s in shots)
    # keyword only on the first shot of a beat
    assert shots[0].keyword == "A"
    assert sum(1 for s in shots if s.keyword == "A") == 1


def test_render_shot_image_size_and_brightness():
    W, H = 360, 640
    theme = get_theme("midnight")
    skel = Skeleton()
    vmask = build_vignette_mask(W, H, 0.9)
    vblack = Image.new("RGB", (W, H), (0, 0, 0))
    cache: dict[int, Image.Image] = {}

    def base_for(e: float) -> Image.Image:
        k = int(round(e * 10))
        return cache.setdefault(k, make_base_background(W, H, theme, energy=k / 10))

    cfg = MontageConfig(width=W, height=H, theme="midnight")
    shot = Shot(pose=POSES["power"], duration=2.0, framing="full",
                keyword="WAIT", keyword_big=True, energy=0.9)
    img = render_shot(shot, get_character("iko"), cfg, base_for=base_for,
                      vmask=vmask, vblack=vblack, W=W, H=H, skel=skel)
    assert img.size == (W, H)
    assert img.convert("L").getextrema()[1] > 200   # the figure is visible
