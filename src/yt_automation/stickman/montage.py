"""Montage mode: many *still* shots of the brand character, hard-cut to the VO.

No animation — each shot is a single static image of the consistent character in
a pose and camera framing. A fast rotation of framings (full / close / left /
right / medium / hero) cut on the beat makes it feel kinetic while staying "just
images stitched together". Built for high-retention 4-6 minute videos.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .actions import get_action
from .character import Character, draw_accessories
from .render import (
    apply_texture,
    apply_vignette_mask,
    build_vignette_mask,
    draw_figure,
    draw_ground_shadow,
    draw_keyword,
    draw_midground,
    draw_progress_bar,
    draw_watermark,
    get_theme,
    load_font,
    make_base_background,
)
from . import poses as P
from .scene import Beat
from .skeleton import Pose, Skeleton, resolve

_BG_VARIANTS = ["grid", "rays", "dots", "grid", "rays"]

# framing -> (figure-height fraction, root x fraction, root y fraction or None=ground)
FRAMINGS: dict[str, tuple[float, float, float | None]] = {
    "wide":    (0.40, 0.50, None),
    "full":    (0.52, 0.50, None),
    "full_l":  (0.50, 0.33, None),
    "full_r":  (0.50, 0.67, None),
    "low":     (0.60, 0.50, None),
    "hero":    (0.64, 0.50, None),
    "medium":  (0.86, 0.50, 1.02),
    "close":   (1.45, 0.50, 1.28),
    "close_l": (1.40, 0.40, 1.26),
}

# rotation that keeps consecutive cuts visually different
_ROTATION = ["full", "close", "full_l", "medium", "full_r", "low", "close_l", "hero", "wide"]


@dataclass
class Shot:
    pose: Pose
    duration: float
    framing: str = "full"
    keyword: str | None = None
    keyword_big: bool = False
    energy: float = 0.5
    flip: bool = False
    bg_variant: str = "grid"
    seed: int = 0


@dataclass
class MontageConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    theme: str = "midnight"
    ground_frac: float = 0.82
    shot_len: float = 1.9          # average seconds per cut (smaller = faster)
    captions: bool = True
    seed: int = 7
    # branding / polish
    handle: str = ""               # watermark + outro handle
    channel_name: str = ""         # intro card title
    tagline: str = ""              # intro card subtitle
    cta_title: str = "FOLLOW"      # outro card title
    intro: bool = True
    outro: bool = True
    lead_in: float = 0.9           # intro card duration (audio padded to match)
    tail: float = 1.7              # outro card duration
    progress_bar: bool = True
    texture: bool = True


def beats_to_shots(beats: list[Beat], cfg: MontageConfig) -> list[Shot]:
    """Split each beat's time window into several still shots with varied framing."""
    rng = random.Random(cfg.seed)
    shots: list[Shot] = []
    ri = 0
    for bi, beat in enumerate(beats):
        action = get_action(beat.action)
        n = max(1, round(beat.duration / cfg.shot_len))
        dur = beat.duration / n
        variant = _BG_VARIANTS[bi % len(_BG_VARIANTS)]
        for k in range(n):
            # sample the action pose at a lively phase so each shot differs
            phase = 0.4 + 0.55 * ((k + 0.5) / n)
            pose = action.sample(phase * max(beat.duration, 0.01), beat.duration).pose
            framing = _ROTATION[ri % len(_ROTATION)]
            ri += 1
            first = (k == 0)
            shots.append(Shot(
                pose=pose,
                duration=dur,
                framing=framing,
                keyword=beat.keyword if first else None,
                keyword_big=bool(first and beat.intensity >= 0.82),
                energy=max(action.energy, beat.intensity),
                flip=(rng.random() < 0.18),
                bg_variant=variant,
                seed=ri,
            ))
    return shots


def _root_for(framing: str, cfg: MontageConfig, skel: Skeleton, scale: float,
              W: int, H: int) -> tuple[float, float]:
    frac_h, fx, fy = FRAMINGS.get(framing, FRAMINGS["full"])
    x = W * fx
    if fy is None:
        y = H * cfg.ground_frac - (skel.thigh + skel.shin) * scale
    else:
        y = H * fy
    return (x, y)


def render_shot(
    shot: Shot, character: Character, cfg: MontageConfig,
    *, base_for, vmask, vblack, W: int, H: int, skel: Skeleton,
    handle: str = "", progress: float | None = None, texture: bool = True,
) -> Image.Image:
    theme = get_theme(cfg.theme)
    frac_h = FRAMINGS.get(shot.framing, FRAMINGS["full"])[0]
    scale = (H * frac_h) / skel.total_height()
    root = _root_for(shot.framing, cfg, skel, scale, W, H)

    pose = shot.pose.mirrored() if shot.flip else shot.pose
    j = resolve(pose, skel, root, scale)

    img = base_for(shot.energy).copy()
    draw_midground(img, theme, variant=shot.bg_variant, energy=shot.energy, seed=shot.seed)
    draw_ground_shadow(img, j, theme)
    draw_figure(img, j, color=character.body,
                glow_color=character.glow if theme.glow else None)
    draw_accessories(img, j, character)

    # alternate keyword colour for kinetic variety
    kw_accent = theme.accent if (shot.seed % 2 == 0) else theme.accent2
    if shot.keyword:
        if shot.keyword_big:
            draw_keyword(img, shot.keyword, theme, scale=2.2, alpha=1.0, y_frac=0.40,
                         accent=kw_accent)
        else:
            draw_keyword(img, shot.keyword, theme, scale=1.05, alpha=1.0, y_frac=0.11,
                         accent=kw_accent)

    img = apply_vignette_mask(img, vmask, vblack)
    if texture:
        img = apply_texture(img, grain=0.03, scanlines=True, seed=shot.seed)
    if handle:
        draw_watermark(img, handle, theme)
    if progress is not None:
        draw_progress_bar(img, theme, progress)
    return img


def render_card(
    kind: str, title: str, subtitle: str, character: Character, cfg: MontageConfig,
    *, base_for, vmask, vblack, W: int, H: int, skel: Skeleton, handle: str = "",
) -> Image.Image:
    """A branded intro/outro still: big title + hero character + subtitle."""
    theme = get_theme(cfg.theme)
    img = base_for(0.85).copy()
    draw_midground(img, theme, variant="rays", energy=0.85, seed=1)

    pose = P.CHEER if kind == "outro" else P.IDEA
    scale = (H * 0.40) / skel.total_height()
    root = (W * 0.5, H * 0.82 - (skel.thigh + skel.shin) * scale)
    j = resolve(pose, skel, root, scale)
    draw_ground_shadow(img, j, theme)
    draw_figure(img, j, color=character.body, glow_color=character.glow)
    draw_accessories(img, j, character)

    # big title (auto-fit) high on the frame
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    txt = title.upper()
    size = int(H * 0.085)
    font = load_font(size)
    tw = d.textbbox((0, 0), txt, font=font)[2]
    if tw > W * 0.9:
        size = int(size * W * 0.9 / tw)
        font = load_font(size)
    bb = d.textbbox((0, 0), txt, font=font)
    x = (W - (bb[2] - bb[0])) // 2 - bb[0]
    y = int(H * 0.16)
    d.text((x + 4, y + 4), txt, font=font, fill=(0, 0, 0, 200))
    d.text((x, y), txt, font=font, fill=theme.accent + (255,))
    if subtitle:
        ssize = int(H * 0.034)
        sf = load_font(ssize)
        sw = d.textbbox((0, 0), subtitle, font=sf)[2]
        if sw > W * 0.9:
            ssize = int(ssize * W * 0.9 / sw)
            sf = load_font(ssize)
        sb = d.textbbox((0, 0), subtitle, font=sf)
        sx = (W - (sb[2] - sb[0])) // 2 - sb[0]
        d.text((sx, y + int(size * 1.15)), subtitle, font=sf, fill=theme.figure + (220,))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

    img = apply_vignette_mask(img, vmask, vblack)
    img = apply_texture(img, grain=0.03, scanlines=True, seed=2)
    if handle:
        draw_watermark(img, handle, theme)
    return img


def render_montage(
    shots: list[Shot],
    character: Character,
    cfg: MontageConfig,
    *,
    audio_path: Path,
    out_path: Path,
    captions_ass: Path | None = None,
    ffmpeg: str = "ffmpeg",
    progress=None,
) -> Path:
    """Render every still, then hard-cut them together over the voiceover."""
    if not shots:
        raise ValueError("no shots to render")
    theme = get_theme(cfg.theme)
    skel = Skeleton()
    W, H = cfg.width, cfg.height

    vmask = build_vignette_mask(W, H, 0.9)
    vblack = Image.new("RGB", (W, H), (0, 0, 0))
    base_cache: dict[int, Image.Image] = {}

    def base_for(energy: float) -> Image.Image:
        key = int(round(energy * 10))
        if key not in base_cache:
            base_cache[key] = make_base_background(W, H, theme, energy=key / 10)
        return base_cache[key]

    frames_dir = out_path.parent / (out_path.stem + "_shots")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    # total timeline (incl. intro/outro cards) for the stepped progress bar
    total = sum(s.duration for s in shots)
    total += cfg.lead_in if cfg.intro else 0.0
    total += cfg.tail if cfg.outro else 0.0
    total = max(total, 0.1)

    entries: list[tuple[Path, float]] = []   # (png path, duration)
    idx = 0
    cum = 0.0

    def _save(img: Image.Image, dur: float) -> None:
        nonlocal idx, cum
        p = frames_dir / f"shot{idx:05d}.png"
        img.save(p)
        entries.append((p, dur))
        idx += 1
        cum += dur

    if cfg.intro:
        card = render_card("intro", cfg.channel_name or "PSYCHOLOGY",
                           cfg.tagline, character, cfg, base_for=base_for,
                           vmask=vmask, vblack=vblack, W=W, H=H, skel=skel,
                           handle=cfg.handle)
        _save(card, cfg.lead_in)

    for i, shot in enumerate(shots):
        frac = (cum + shot.duration / 2) / total if cfg.progress_bar else None
        img = render_shot(shot, character, cfg, base_for=base_for, vmask=vmask,
                          vblack=vblack, W=W, H=H, skel=skel, handle=cfg.handle,
                          progress=frac, texture=cfg.texture)
        _save(img, shot.duration)
        if progress and i % 20 == 0:
            progress(i, len(shots))

    if cfg.outro:
        card = render_card("outro", cfg.cta_title, cfg.handle, character, cfg,
                           base_for=base_for, vmask=vmask, vblack=vblack,
                           W=W, H=H, skel=skel, handle=cfg.handle)
        _save(card, cfg.tail)

    list_lines: list[str] = []
    for p, dur in entries:
        list_lines.append(f"file '{p.resolve().as_posix()}'")
        list_lines.append(f"duration {max(0.2, dur):.3f}")
    # repeat the last image so its duration is honoured by the concat demuxer
    list_lines.append(f"file '{entries[-1][0].resolve().as_posix()}'")

    list_file = frames_dir / "shots.txt"
    list_file.write_text("\n".join(list_lines), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-i", str(audio_path),
    ]
    if captions_ass is not None:
        cmd += ["-vf", f"ass={captions_ass.as_posix()}"]
    cmd += [
        "-map", "0:v", "-map", "1:a",
        "-r", str(cfg.fps), "-fps_mode", "cfr",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return out_path
