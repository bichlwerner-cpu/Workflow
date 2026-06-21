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

from PIL import Image

from .actions import get_action
from .character import Character, draw_accessories
from .render import (
    apply_vignette_mask,
    build_vignette_mask,
    draw_figure,
    draw_grid,
    draw_keyword,
    get_theme,
    make_base_background,
)
from .scene import Beat
from .skeleton import Pose, Skeleton, resolve

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


def beats_to_shots(beats: list[Beat], cfg: MontageConfig) -> list[Shot]:
    """Split each beat's time window into several still shots with varied framing."""
    rng = random.Random(cfg.seed)
    shots: list[Shot] = []
    ri = 0
    for beat in beats:
        action = get_action(beat.action)
        n = max(1, round(beat.duration / cfg.shot_len))
        dur = beat.duration / n
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
) -> Image.Image:
    theme = get_theme(cfg.theme)
    frac_h = FRAMINGS.get(shot.framing, FRAMINGS["full"])[0]
    scale = (H * frac_h) / skel.total_height()
    root = _root_for(shot.framing, cfg, skel, scale, W, H)

    pose = shot.pose.mirrored() if shot.flip else shot.pose
    j = resolve(pose, skel, root, scale)

    img = base_for(shot.energy).copy()
    draw_grid(img, theme, t=0.0, energy=shot.energy)
    draw_figure(img, j, color=character.body,
                glow_color=character.glow if theme.glow else None)
    draw_accessories(img, j, character)

    if shot.keyword:
        if shot.keyword_big:
            draw_keyword(img, shot.keyword, theme, scale=2.2, alpha=1.0, y_frac=0.40)
        else:
            draw_keyword(img, shot.keyword, theme, scale=1.0, alpha=1.0, y_frac=0.12)

    return apply_vignette_mask(img, vmask, vblack)


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

    list_lines: list[str] = []
    for i, shot in enumerate(shots):
        img = render_shot(shot, character, cfg, base_for=base_for, vmask=vmask,
                          vblack=vblack, W=W, H=H, skel=skel)
        p = frames_dir / f"shot{i:05d}.png"
        img.save(p)
        list_lines.append(f"file '{p.resolve().as_posix()}'")
        list_lines.append(f"duration {max(0.2, shot.duration):.3f}")
        if progress and i % 20 == 0:
            progress(i, len(shots))
    # repeat the last image so its duration is honoured by the concat demuxer
    list_lines.append(f"file '{(frames_dir / f'shot{len(shots)-1:05d}.png').resolve().as_posix()}'")

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
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return out_path
