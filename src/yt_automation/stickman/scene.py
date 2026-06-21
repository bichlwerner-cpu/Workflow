"""Timeline renderer: storyboard beats -> animated frames -> MP4.

A :class:`Beat` is one spoken sentence with an assigned action, an optional big
on-screen keyword, and an intensity (0..1) that drives the "fast & intense"
treatment: a zoom-punch on the cut, a screen flash on the beat boundary, and
camera shake during high-energy moments. Frames are written as PNGs and encoded
with FFmpeg.
"""

from __future__ import annotations

import math
import random
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .actions import get_action
from .character import Character, draw_accessories, get_character
from .render import (
    Theme,
    apply_flash,
    apply_texture,
    apply_vignette_mask,
    build_vignette_mask,
    draw_figure,
    draw_grid,
    draw_ground_shadow,
    draw_keyword,
    draw_motion_lines,
    draw_watermark,
    get_theme,
    make_base_background,
)
from .skeleton import Skeleton, resolve


@dataclass
class Beat:
    text: str
    action: str = "idle"
    keyword: str | None = None
    intensity: float = 0.5
    start: float = 0.0       # filled in by the storyboard builder
    duration: float = 2.0


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    theme: str = "midnight"
    figure_height_frac: float = 0.5
    ground_frac: float = 0.82     # where the feet sit
    supersample: int = 1          # 2 = smoother lines at ~4x cost
    seed: int = 7
    character: str = "halo"       # brand mascot drawn every frame
    watermark: str = ""           # brand handle, bottom-right
    texture: bool = True          # film grain + scanlines


def _ground_root(cfg: RenderConfig, skel: Skeleton, scale: float) -> tuple[float, float]:
    """Pelvis position so the feet land on the ground line, figure centred."""
    foot_drop = (skel.thigh + skel.shin) * scale
    py = cfg.height * cfg.ground_frac - foot_drop
    return (cfg.width * 0.5, py)


def _rotate_point(p, c, deg):
    a = math.radians(deg)
    s, co = math.sin(a), math.cos(a)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * co - dy * s, c[1] + dx * s + dy * co)


def render_storyboard(
    beats: list[Beat],
    out_path: Path,
    cfg: RenderConfig,
    *,
    ffmpeg: str = "ffmpeg",
    progress=None,
) -> Path:
    """Render all beats to ``out_path`` (an .mp4, video only)."""
    if not beats:
        raise ValueError("storyboard has no beats")
    theme = get_theme(cfg.theme)
    skel = Skeleton()
    character = get_character(cfg.character)
    rng = random.Random(cfg.seed)

    ss = max(1, cfg.supersample)
    W, H = cfg.width * ss, cfg.height * ss
    scale = (H * cfg.figure_height_frac) / skel.total_height()
    base_root = _ground_root(RenderConfig(**{**cfg.__dict__, "width": W, "height": H}), skel, scale)

    total = beats[-1].start + beats[-1].duration
    n_frames = max(1, int(round(total * cfg.fps)))

    frames_dir = out_path.parent / (out_path.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Cache the expensive, per-frame-constant pieces.
    vmask = build_vignette_mask(W, H, 0.9)
    vblack = Image.new("RGB", (W, H), (0, 0, 0))
    base_cache: dict[int, Image.Image] = {}

    def base_for(energy: float) -> Image.Image:
        key = int(round(energy * 10))
        if key not in base_cache:
            base_cache[key] = make_base_background(W, H, theme, energy=key / 10)
        return base_cache[key]

    bi = 0
    for fi in range(n_frames):
        t = fi / cfg.fps
        while bi + 1 < len(beats) and t >= beats[bi + 1].start:
            bi += 1
        beat = beats[bi]
        local = t - beat.start
        img = _render_frame(t, local, beat, theme, skel, scale, base_root,
                            W, H, rng, cfg, base_for, vmask, vblack, character)
        if ss > 1:
            img = img.resize((cfg.width, cfg.height), Image.LANCZOS)
        img.save(frames_dir / f"f{fi:05d}.png")
        if progress and fi % cfg.fps == 0:
            progress(fi, n_frames)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(cfg.fps),
        "-i", str(frames_dir / "f%05d.png"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(cfg.fps),
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return out_path


def _render_frame(t, local, beat, theme, skel, scale, base_root, W, H, rng, cfg,
                  base_for, vmask, vblack, character: Character) -> Image.Image:
    action = get_action(beat.action)
    energy = max(action.energy, beat.intensity)

    # zoom-punch: cut lands "hot" then settles in the first ~0.2s
    punch_t = min(1.0, local / 0.22)
    zoom = 1.0 + 0.10 * beat.intensity * (1.0 - punch_t) ** 2

    img = base_for(energy).copy()
    draw_grid(img, theme, t=t, energy=energy)

    frame = action.sample(local, beat.duration)

    # figure root incl. action travel + bob + zoom-punch displacement
    travel = action.travel_x * (local / beat.duration if beat.duration else 1.0)
    root_x = base_root[0] - action.travel_x * 0.5 * W + travel * W + frame.dx * scale
    root_y = base_root[1] + frame.dy * scale

    j = resolve(frame.pose, skel, (root_x, root_y), scale * frame.scale * zoom)

    if frame.rot:
        center = j.pelvis
        j = type(j)(
            pelvis=j.pelvis,
            neck=_rotate_point(j.neck, center, frame.rot),
            head_center=_rotate_point(j.head_center, center, frame.rot),
            head_radius=j.head_radius,
            elbow_l=_rotate_point(j.elbow_l, center, frame.rot),
            hand_l=_rotate_point(j.hand_l, center, frame.rot),
            elbow_r=_rotate_point(j.elbow_r, center, frame.rot),
            hand_r=_rotate_point(j.hand_r, center, frame.rot),
            knee_l=_rotate_point(j.knee_l, center, frame.rot),
            foot_l=_rotate_point(j.foot_l, center, frame.rot),
            knee_r=_rotate_point(j.knee_r, center, frame.rot),
            foot_r=_rotate_point(j.foot_r, center, frame.rot),
        )

    draw_motion_lines(img, j, theme, frame.motion)
    draw_ground_shadow(img, j, theme)
    draw_figure(img, j, color=character.body, glow_color=character.glow if theme.glow else None)
    draw_accessories(img, j, character)

    # kinetic keyword: pop in over first 0.25s, hold
    if beat.keyword:
        kt = min(1.0, local / 0.25)
        ks = 0.6 + 0.4 * (kt * kt * (3 - 2 * kt))
        if local < 0.25:
            ks = 1.15 - 0.15 * kt  # slight overshoot settle
        draw_keyword(img, beat.keyword, theme, scale=ks, alpha=min(1.0, kt * 1.4),
                     y_frac=0.13)

    img = apply_vignette_mask(img, vmask, vblack)

    # screen flash on the cut, scaled by intensity
    flash = max(0.0, (1.0 - local / 0.12)) * 0.5 * beat.intensity
    img = apply_flash(img, theme, flash)

    # camera shake during the hot part of intense beats
    shake_amp = beat.intensity * 14 * ss_factor(cfg) * max(0.0, 1.0 - local / 0.3)
    if shake_amp > 0.5:
        ox = int(rng.uniform(-shake_amp, shake_amp))
        oy = int(rng.uniform(-shake_amp, shake_amp))
        if ox or oy:
            img = img.transform(
                img.size, Image.AFFINE, (1, 0, ox, 0, 1, oy),
                resample=Image.BILINEAR,
            )

    if cfg.texture:
        img = apply_texture(img, grain=0.03, scanlines=True, seed=int(local * 90))
    if cfg.watermark:
        draw_watermark(img, cfg.watermark, theme)
    return img


def ss_factor(cfg: RenderConfig) -> float:
    return max(1, cfg.supersample)
