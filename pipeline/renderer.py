"""Frame renderer: composes every video frame from the timeline.

Each narration beat is a *shot* (see pipeline/shots.py): a framed composition —
wide (full-body action on a metaphor stage), medium (waist-up), close-up (big
lip-synced head) or insert (a single icon). Consecutive beats hard-cut between
shots, each with its own zoom move plus a snap "punch" on the cut, so the
screen never sits still.

Frames are drawn at `supersample`x resolution for clean anti-aliased lines,
then a camera transform (zoom, punch, shake, drift) crops + scales down to the
output size in a single resize. Frames are yielded as raw RGB bytes piped
straight into ffmpeg — no intermediate image files.
"""

from __future__ import annotations

import math
from typing import Dict, Iterator, List, Optional, Tuple

from PIL import Image, ImageDraw

from .config import Settings
from .shots import (SHOT_CLOSEUP, SHOT_INSERT, SHOT_MEDIUM, SHOT_WIDE,
                    resolve_shots)
from .stickman import (COLLAPSED, animate_pose, draw_character, is_blinking,
                       lerp_pose)
from .timeline import TimedLine, TimedScene, Timeline
from .utils import RGB, hex_to_rgb, load_font, luminance, mix, text_size, wrap_text

INK_DARK = (27, 27, 31)
INK_LIGHT = (245, 241, 232)

CARD_SECONDS = 1.7
PROP_POP_SECONDS = 0.30
SHAKE_SECONDS = 0.55
PUNCH_SECONDS = 0.12        # length of the snap when a new shot cuts in

# Per-shot framing: (character scale / canvas-height, ground anchor / height).
SHOT_FRAMING = {
    SHOT_WIDE:    (0.50, 0.88),
    SHOT_MEDIUM:  (0.92, 1.30),
    SHOT_CLOSEUP: (2.00, 2.20),
}


def _seeded(seq: int) -> float:
    """Cheap deterministic pseudo-random in [0,1)."""
    x = math.sin(seq * 127.1 + 311.7) * 43758.5453
    return x - math.floor(x)


class FrameRenderer:
    def __init__(self, settings: Settings, timeline: Timeline):
        self.settings = settings
        self.timeline = timeline
        self.W = settings.width
        self.H = settings.height
        self.fps = settings.fps
        ss = float(settings.get("video", "supersample", default=2.0))
        self.cw, self.ch = int(self.W * ss), int(self.H * ss)
        self.accent = hex_to_rgb(settings.accent)
        self.font_path = settings.font_path()
        self.progress_bar = bool(settings.get("style", "progress_bar", default=True))
        self.chapter_cards = bool(settings.get("style", "chapter_cards", default=True))
        self.watermark = str(settings.get("style", "watermark", default="") or "")

        self._bg_cache: Dict[str, Tuple[Image.Image, RGB, bool]] = {}
        self._closeup_cache: Dict[int, Image.Image] = {}
        self._vignette: Optional[Image.Image] = None
        self._dim: Optional[Image.Image] = None
        self._char_phase = {key: 2 * math.pi * _seeded(i + 1)
                            for i, key in enumerate(sorted(settings.characters))}

        # Resolve every beat to a concrete shot + give it a stable index so the
        # camera can alternate push/pull and the cut rhythm stays varied.
        self.shots: Dict[str, str] = resolve_shots(timeline)
        self._line_index: Dict[str, int] = {}
        k = 0
        for scene in timeline.scenes:
            for tl in scene.lines:
                self._line_index[tl.voiced.line_id] = k
                k += 1

    def _shot_for(self, tl: TimedLine) -> str:
        return self.shots.get(tl.voiced.line_id, SHOT_WIDE)

    # ----------------------------------------------------------- backgrounds
    def _vignette_overlay(self) -> Image.Image:
        if self._vignette is None:
            small = Image.new("L", (160, 90), 0)
            for y in range(90):
                for x in range(160):
                    dist = math.hypot((x - 80) / 80, (y - 45) / 45)
                    small.putpixel((x, y), int(70 * max(0.0, dist - 0.55) ** 1.6))
            mask = small.resize((self.cw, self.ch), Image.BILINEAR)
            overlay = Image.new("RGBA", (self.cw, self.ch), (10, 10, 14, 0))
            overlay.putalpha(mask)
            self._vignette = overlay
        return self._vignette

    def _dim_overlay(self) -> Image.Image:
        if self._dim is None:
            self._dim = Image.new("RGBA", (self.cw, self.ch), (8, 8, 12, 120))
        return self._dim

    def _vertical_gradient(self, top: RGB, bottom: RGB) -> Image.Image:
        strip = Image.new("RGB", (1, 256))
        strip.putdata([mix(top, bottom, i / 255) for i in range(256)])
        return strip.resize((self.cw, self.ch), Image.BILINEAR)

    def background(self, preset: str) -> Tuple[Image.Image, RGB, bool]:
        """Returns (image, base_fill, is_dark)."""
        if preset in self._bg_cache:
            return self._bg_cache[preset]

        cw, ch = self.cw, self.ch
        if preset == "chalkboard":
            base: RGB = (42, 59, 51)
            img = Image.new("RGB", (cw, ch), base)
            d = ImageDraw.Draw(img)
            for i in range(220):  # chalk dust
                x, y = _seeded(i * 2) * cw, _seeded(i * 2 + 1) * ch
                r = 1 + _seeded(i + 999) * 2.5
                d.ellipse([x, y, x + r, y + r], fill=mix(base, INK_LIGHT, 0.12))
        elif preset == "night":
            base = (22, 33, 62)
            img = self._vertical_gradient((13, 20, 40), (34, 48, 84))
            d = ImageDraw.Draw(img)
            for i in range(140):
                x, y = _seeded(i * 3) * cw, _seeded(i * 3 + 1) * ch * 0.7
                r = 1 + _seeded(i + 77) * 2.5
                d.ellipse([x, y, x + r, y + r], fill=(220, 224, 240))
        elif preset == "stage":
            base = (40, 40, 56)
            img = self._vertical_gradient((24, 24, 34), (58, 58, 78))
            d = ImageDraw.Draw(img)
            spot_w, spot_h = cw * 0.62, ch * 0.5
            cx, sy = cw / 2, ch * 0.88
            for kk in range(5, 0, -1):
                u = kk / 5
                d.ellipse([cx - spot_w * u / 2, sy - spot_h * u / 2,
                           cx + spot_w * u / 2, sy + spot_h * u / 2],
                          fill=mix(base, (96, 96, 120), 1 - u))
        elif preset == "gradient_warm":
            base = (255, 226, 184)
            img = self._vertical_gradient((255, 239, 208), (255, 198, 158))
        elif preset == "gradient_cool":
            base = (216, 232, 250)
            img = self._vertical_gradient((228, 240, 255), (188, 213, 242))
        elif preset == "graph":
            base = (250, 247, 240)
            img = Image.new("RGB", (cw, ch), base)
            d = ImageDraw.Draw(img)
            grid = mix(base, INK_DARK, 0.08)
            step = ch // 12
            for x in range(0, cw, step):
                d.line([(x, 0), (x, ch)], fill=grid, width=2)
            for y in range(0, ch, step):
                d.line([(0, y), (cw, y)], fill=grid, width=2)
            axis = mix(base, INK_DARK, 0.45)
            d.line([(cw * 0.07, ch * 0.1), (cw * 0.07, ch * 0.9), (cw * 0.95, ch * 0.9)],
                   fill=axis, width=max(3, ch // 300), joint="curve")
        elif preset == "paper":
            base = (250, 247, 240)
            img = Image.new("RGB", (cw, ch), base)
            d = ImageDraw.Draw(img)
            dot = mix(base, INK_DARK, 0.10)
            step = ch // 18
            for y in range(step, ch, step):
                for x in range(step, cw, step):
                    d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=dot)
        elif preset in ("mountain", "path_split", "wall", "pit"):
            base = (250, 247, 240)
            img = Image.new("RGB", (cw, ch), base)
            d = ImageDraw.Draw(img)
            ink = mix(base, INK_DARK, 0.75)
            soft = mix(base, INK_DARK, 0.22)
            gy = ch * 0.84
            lw = max(4, ch // 220)
            if preset == "mountain":
                d.polygon([(cw * 0.52, gy), (cw * 0.78, ch * 0.16), (cw * 1.02, gy)],
                          fill=mix(base, INK_DARK, 0.10), outline=ink, width=lw)
                d.line([(cw * 0.78, ch * 0.16), (cw * 0.78, ch * 0.09)], fill=ink, width=lw)
                d.polygon([(cw * 0.78, ch * 0.09), (cw * 0.84, ch * 0.115), (cw * 0.78, ch * 0.14)],
                          fill=self.accent)
                d.line([(0, gy), (cw, gy)], fill=ink, width=lw)
            elif preset == "path_split":
                for tx in (cw * 0.13, cw * 0.87):
                    d.line([(cw * 0.5, ch * 0.92), (tx, ch * 0.50)], fill=soft, width=int(ch * 0.045))
                post_x, post_y = cw * 0.5, ch * 0.50
                d.line([(post_x, post_y), (post_x, post_y - ch * 0.16)], fill=ink, width=lw * 2)
                for kk, side in enumerate((-1, 1)):
                    by = post_y - ch * (0.15 - 0.055 * kk)
                    d.polygon([(post_x, by - ch * 0.022), (post_x, by + ch * 0.022),
                               (post_x + side * cw * 0.085, by + ch * 0.022),
                               (post_x + side * cw * 0.105, by),
                               (post_x + side * cw * 0.085, by - ch * 0.022)], fill=self.accent)
                d.line([(0, gy), (cw, gy)], fill=ink, width=lw)
            elif preset == "wall":
                x0, x1 = cw * 0.455, cw * 0.545
                top = ch * 0.30
                d.rectangle([x0, top, x1, gy], fill=mix(base, INK_DARK, 0.16), outline=ink, width=lw)
                rows = 9
                for r in range(1, rows):
                    y = top + (gy - top) * r / rows
                    d.line([(x0, y), (x1, y)], fill=ink, width=max(2, lw // 2))
                    xm = (x0 + x1) / 2 if r % 2 else x0 + (x1 - x0) * 0.25
                    d.line([(xm, y), (xm, y + (gy - top) / rows)], fill=ink, width=max(2, lw // 2))
                d.line([(0, gy), (cw, gy)], fill=ink, width=lw)
            else:  # pit
                d.line([(0, gy), (cw * 0.40, gy)], fill=ink, width=lw)
                d.line([(cw * 0.60, gy), (cw, gy)], fill=ink, width=lw)
                d.polygon([(cw * 0.40, gy), (cw * 0.45, ch * 0.99),
                           (cw * 0.55, ch * 0.99), (cw * 0.60, gy)],
                          fill=mix(base, (0, 0, 0), 0.82))
        else:  # "void" and any fallback
            base = (250, 247, 240)
            img = Image.new("RGB", (cw, ch), base)

        img.paste(self._vignette_overlay(), (0, 0), self._vignette_overlay())
        is_dark = luminance(base) < 0.45
        self._bg_cache[preset] = (img, base, is_dark)
        return self._bg_cache[preset]

    def _closeup_backdrop(self, palette: int) -> Image.Image:
        """Deliberate 'talking-head' backdrop: dark gradient + glow behind head."""
        if palette in self._closeup_cache:
            return self._closeup_cache[palette]
        cw, ch = self.cw, self.ch
        tops = [(44, 34, 30), (26, 34, 48), (30, 26, 40)]
        bots = [(18, 14, 13), (11, 15, 24), (12, 11, 18)]
        top = mix(tops[palette % 3], self.accent, 0.05)
        bot = bots[palette % 3]
        img = self._vertical_gradient(top, bot)
        d = ImageDraw.Draw(img)
        gx, gy = cw * 0.5, ch * 0.42
        glow = mix(top, mix(self.accent, (255, 255, 255), 0.4), 0.5)
        for kk in range(26, 0, -1):
            u = kk / 26
            r = ch * 0.62 * u
            d.ellipse([gx - r, gy - r, gx + r, gy + r],
                      fill=mix(bot, glow, (1 - u) * 0.30))
        img.paste(self._vignette_overlay(), (0, 0), self._vignette_overlay())
        self._closeup_cache[palette] = img
        return img

    # --------------------------------------------------------------- staging
    def _ink_for(self, color: RGB, base: RGB) -> RGB:
        """Guarantee stroke/background contrast on any background preset."""
        if abs(luminance(color) - luminance(base)) < 0.25:
            return INK_LIGHT if luminance(base) < 0.45 else INK_DARK
        return color

    @staticmethod
    def _smooth(u: float) -> float:
        u = max(0.0, min(1.0, u))
        return u * u * (3 - 2 * u)

    def _actor_kinematics(self, action: str, slot: float, t_in: float, dur: float,
                          base_facing: int) -> Tuple[float, bool, int, float, float, bool]:
        """Position/motion of one actor: (x_frac, moving, facing, jump_y, collapse_u, visible)."""
        enter_t = min(0.9, dur * 0.45)
        x, moving, facing, visible = slot, False, base_facing, True

        if action == "enter_left" and t_in < enter_t:
            u = self._smooth(t_in / enter_t)
            x, moving, facing = -0.12 + (slot + 0.12) * u, True, 1
        elif action == "enter_right" and t_in < enter_t:
            u = self._smooth(t_in / enter_t)
            x, moving, facing = 1.12 - (1.12 - slot) * u, True, -1
        elif action in ("exit_left", "exit_right"):
            t0 = dur - enter_t
            if t_in > t0:
                u = self._smooth((t_in - t0) / enter_t)
                if action == "exit_left":
                    x, facing = slot - (slot + 0.12) * u, -1
                else:
                    x, facing = slot + (1.12 - slot) * u, 1
                moving = True
                visible = -0.11 < x < 1.11
        elif action == "walk_across":
            u = self._smooth(t_in / dur)
            x, moving, facing = 0.14 + 0.72 * u, u < 0.995, 1
        elif action == "approach":
            toward = 1 if slot <= 0.5 else -1
            start = slot - toward * 0.20
            mt = min(1.0, dur * 0.5)
            if t_in < mt:
                u = self._smooth(t_in / mt)
                x, moving = start + (slot - start) * u, True
        elif action == "retreat":
            away = -1 if slot <= 0.5 else 1
            target = slot + away * 0.15
            mt = min(1.0, dur * 0.5)
            u = self._smooth(t_in / mt) if t_in < mt else 1.0
            x, moving = slot + (target - slot) * u, t_in < mt

        jump_y = 0.0
        if action == "jump":
            jt = min(0.7, dur)
            if t_in < jt:
                jump_y = 0.16 * math.sin(math.pi * t_in / jt)

        collapse_u = self._smooth(t_in / 0.8) if action == "collapse" else 0.0
        return x, moving, facing, jump_y, collapse_u, visible

    def _draw_staging(self, draw: ImageDraw.ImageDraw, t: float, base: RGB,
                      is_dark: bool, tl: TimedLine, shot: str, scene: TimedScene) -> None:
        """Render the current beat for the given shot framing."""
        actors = list(tl.voiced.actors)
        ink = INK_LIGHT if is_dark else INK_DARK
        t_line = max(0.0, t - tl.start)

        if shot == SHOT_INSERT or not actors:
            if tl.voiced.prop != "none":
                self._draw_prop(draw, tl.voiced.prop, (self.cw * 0.5, self.ch * 0.46),
                                self.ch * 0.26, ink, t_line)
            return

        # Close-ups / mediums are single-character by design (no stray extras).
        if shot in (SHOT_CLOSEUP, SHOT_MEDIUM):
            actors = actors[:1]
        else:
            actors = actors[:2]

        dur = max(0.3, tl.end - tl.start)
        t_in = min(t_line, dur)
        scale_f, ground_f = SHOT_FRAMING.get(shot, SHOT_FRAMING[SHOT_WIDE])
        scale = self.ch * scale_f
        ground_y = self.ch * ground_f
        lip_sync = shot in (SHOT_CLOSEUP, SHOT_MEDIUM)

        if len(actors) == 1:
            if shot == SHOT_WIDE:
                slots = [{"wall": 0.32, "pit": 0.32, "path_split": 0.36,
                          "mountain": 0.34}.get(scene.background, 0.5)]
            else:
                slots = [0.5]
        else:
            slots = [0.32, 0.68]
        prop_anchor: Optional[Tuple[float, float]] = None

        for i, a in enumerate(actors):
            cfg = self.settings.characters.get(a.get("character", ""))
            if cfg is None:
                continue
            base_facing = 1 if i == 0 else -1
            x, moving, facing, jump_y, collapse_u, visible = self._actor_kinematics(
                a.get("action", "none"), slots[i], t_in, dur, base_facing)
            if not visible:
                continue
            phase = self._char_phase.get(cfg.key, 0.0)
            pose_name = "walking" if moving else a.get("pose", "idle")
            pose = animate_pose(pose_name, t, phase, speaking=lip_sync and i == 0)
            pose.y_offset += jump_y
            if collapse_u > 0:
                pose = lerp_pose(pose, COLLAPSED, collapse_u)

            mouth = lip_sync and i == 0 and tl.mouth_open(t)
            draw_character(
                draw, (self.cw * x, ground_y), scale,
                color=self._ink_for(hex_to_rgb(cfg.color), base), bg_fill=base,
                pose=pose, emotion=a.get("emotion", "neutral"), mouth_open=mouth,
                blink=is_blinking(t, phase), facing=facing,
                accessory=cfg.accessory, hair=cfg.hair, accent=self.accent,
                shadow=(shot == SHOT_WIDE),
            )
            if i == 0:
                if shot == SHOT_WIDE:
                    prop_anchor = (self.cw * x + facing * scale * 0.55,
                                   ground_y - scale * 1.20)
                elif shot == SHOT_MEDIUM:
                    prop_anchor = (self.cw * 0.78, self.ch * 0.28)
                # close-up stays clean: the head is the whole frame

        if tl.voiced.prop != "none" and prop_anchor is not None:
            psize = scale * (0.30 if shot == SHOT_WIDE else 0.13)
            self._draw_prop(draw, tl.voiced.prop, prop_anchor, psize, ink, t_line)

    # ----------------------------------------------------------------- props
    def _draw_prop(self, draw: ImageDraw.ImageDraw, name: str, center, size: float,
                   ink: RGB, t_in: float) -> None:
        u = min(1.0, max(0.0, t_in / PROP_POP_SECONDS))
        s = size * math.sin(u * math.pi / 2) * (1 + 0.04 * math.sin(t_in * 3.1))
        if s < 1:
            return
        cx, cy = center
        cy += math.sin(t_in * 2.2) * size * 0.06  # gentle float
        fw = max(3, int(s * 0.09))
        a = self.accent

        def glyph(ch: str):
            font = load_font(self.font_path, int(s * 1.5))
            w, h = text_size(draw, ch, font)
            draw.text((cx - w / 2, cy - h * 0.72), ch, font=font, fill=a,
                      stroke_width=max(2, fw // 2), stroke_fill=ink)

        if name == "question_mark":
            glyph("?")
        elif name == "exclamation":
            glyph("!")
        elif name == "money":
            glyph("$")
        elif name == "lightbulb":
            r = s * 0.42
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=a, width=fw)
            draw.rectangle([cx - r * 0.35, cy + r * 0.9, cx + r * 0.35, cy + r * 1.35], outline=a, width=fw)
            for kk in range(6):
                ang = math.pi * (0.15 + 0.7 * kk / 5) + math.pi
                x1, y1 = cx + math.cos(ang) * r * 1.25, cy + math.sin(ang) * r * 1.25
                x2, y2 = cx + math.cos(ang) * r * 1.65, cy + math.sin(ang) * r * 1.65
                draw.line([(x1, y1), (x2, y2)], fill=a, width=fw)
        elif name == "heart":
            r = s * 0.3
            draw.ellipse([cx - r * 1.7, cy - r * 1.3, cx - r * 0.0, cy + r * 0.4], fill=a)
            draw.ellipse([cx + r * 0.0, cy - r * 1.3, cx + r * 1.7, cy + r * 0.4], fill=a)
            draw.polygon([(cx - r * 1.55, cy), (cx + r * 1.55, cy), (cx, cy + r * 1.8)], fill=a)
        elif name == "clock":
            r = s * 0.5
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=a, width=fw)
            draw.line([(cx, cy), (cx, cy - r * 0.6)], fill=a, width=fw)
            draw.line([(cx, cy), (cx + r * 0.45, cy + r * 0.15)], fill=a, width=fw)
        elif name in ("arrow_up", "arrow_down"):
            dd = -1 if name == "arrow_up" else 1
            h, w2 = s * 0.55, s * 0.34
            draw.polygon([(cx, cy + dd * h), (cx - w2, cy + dd * h * 0.1),
                          (cx - w2 * 0.45, cy + dd * h * 0.1), (cx - w2 * 0.45, cy - dd * h * 0.8),
                          (cx + w2 * 0.45, cy - dd * h * 0.8), (cx + w2 * 0.45, cy + dd * h * 0.1),
                          (cx + w2, cy + dd * h * 0.1)], fill=a)
        elif name == "star":
            pts = []
            for kk in range(10):
                rr = s * (0.55 if kk % 2 == 0 else 0.24)
                ang = -math.pi / 2 + kk * math.pi / 5
                pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
            draw.polygon(pts, fill=a)
        elif name == "target":
            for kk, rr in enumerate((0.5, 0.34, 0.18)):
                draw.ellipse([cx - s * rr, cy - s * rr, cx + s * rr, cy + s * rr],
                             outline=a if kk % 2 == 0 else ink, width=fw)
        elif name == "eye":
            w2, h2 = s * 0.55, s * 0.32
            draw.ellipse([cx - w2, cy - h2, cx + w2, cy + h2], outline=a, width=fw)
            draw.ellipse([cx - h2 * 0.55, cy - h2 * 0.55, cx + h2 * 0.55, cy + h2 * 0.55], fill=a)
        elif name == "brain":
            r = s * 0.26
            offs = [(-1.1, 0.1), (-0.55, -0.65), (0.3, -0.7), (1.0, -0.1), (0.2, 0.25), (-0.45, 0.3)]
            for ox, oy in offs:
                draw.ellipse([cx + ox * r - r, cy + oy * r - r, cx + ox * r + r, cy + oy * r + r],
                             outline=a, width=fw)

    # ----------------------------------------------------------- text layers
    def _draw_caption(self, img: Image.Image, text: str, is_dark: bool) -> None:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        font = load_font(self.font_path, int(self.ch * 0.058))
        lines = wrap_text(d, text, font, int(self.cw * 0.74))
        pad = int(self.ch * 0.020)
        line_h = int(self.ch * 0.068)
        block_w = max(text_size(d, ln, font)[0] for ln in lines)
        x0 = (self.cw - block_w) / 2 - pad * 1.6
        y0 = self.ch * 0.05
        d.rounded_rectangle(
            [x0, y0, x0 + block_w + pad * 3.2, y0 + len(lines) * line_h + pad * 2],
            radius=int(self.ch * 0.018), fill=(14, 14, 20, 215))
        # thin accent underline tab
        d.rectangle([x0, y0 + len(lines) * line_h + pad * 2 - int(self.ch * 0.006),
                     x0 + block_w + pad * 3.2, y0 + len(lines) * line_h + pad * 2],
                    fill=(*self.accent, 255))
        for i, ln in enumerate(lines):
            w, _ = text_size(d, ln, font)
            d.text(((self.cw - w) / 2, y0 + pad + i * line_h), ln, font=font,
                   fill=(245, 241, 232, 255),
                   stroke_width=max(2, int(self.ch * 0.003)), stroke_fill=(0, 0, 0, 255))
        img.paste(overlay, (0, 0), overlay)

    def _draw_chapter_card(self, img: Image.Image, title: str, index: int, u: float) -> None:
        """u in [0,1] across the card window; fades in/out."""
        alpha = min(1.0, u * 6, (1 - u) * 6)
        if alpha <= 0:
            return
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rectangle([0, 0, self.cw, self.ch], fill=(12, 12, 16, int(185 * alpha)))
        font_big = load_font(self.font_path, int(self.ch * 0.078))
        font_small = load_font(self.font_path, int(self.ch * 0.034))
        kicker = f"PART {index + 1}"
        ty = self.ch * 0.30
        w, _ = text_size(d, kicker, font_small)
        d.text(((self.cw - w) / 2, ty - self.ch * 0.07), kicker, font=font_small,
               fill=(*self.accent, int(255 * alpha)))
        for i, ln in enumerate(wrap_text(d, title, font_big, int(self.cw * 0.8))):
            w, _ = text_size(d, ln, font_big)
            d.text(((self.cw - w) / 2, ty + i * self.ch * 0.094), ln, font=font_big,
                   fill=(245, 241, 232, int(255 * alpha)),
                   stroke_width=max(2, int(self.ch * 0.0035)),
                   stroke_fill=(0, 0, 0, int(255 * alpha)))
        bar_w = self.cw * 0.12
        d.rectangle([(self.cw - bar_w) / 2, ty - self.ch * 0.018,
                     (self.cw + bar_w) / 2, ty - self.ch * 0.010],
                    fill=(*self.accent, int(255 * alpha)))
        img.paste(overlay, (0, 0), overlay)

    # ---------------------------------------------------------------- camera
    def _camera(self, t: float, shot: str, active: TimedLine) -> Tuple[float, float, float]:
        since = t - active.start
        dur = max(0.4, active.end - active.start)
        p = self._smooth(min(1.0, since / dur))
        idx = self._line_index.get(active.voiced.line_id, 0)

        # Alternate push-in / pull-out per beat so no two cuts feel the same.
        amp = 0.10 if shot == SHOT_CLOSEUP else 0.07
        cam = active.voiced.camera
        if cam == "zoom_in":
            zoom = 1.0 + (amp + 0.04) * p
        elif cam == "zoom_out":
            zoom = 1.0 + (amp + 0.04) * (1 - p)
        elif idx % 2 == 0:
            zoom = 1.0 + amp * p                  # push in
        else:
            zoom = 1.0 + amp * (1 - p)            # pull out

        # Snap punch on the cut, easing out fast.
        punch = 0.05 if cam == "punch" else 0.035
        if since < PUNCH_SECONDS:
            zoom += punch * (1 - since / PUNCH_SECONDS)

        dx = (1 if idx % 2 else -1) * 0.010 * self.cw * p
        dy = 0.0
        if cam == "shake" and since < SHAKE_SECONDS:
            amp_s = self.ch * 0.010 * (1 - since / SHAKE_SECONDS)
            dx += amp_s * math.sin(since * 73)
            dy += amp_s * math.cos(since * 61)
        return zoom, dx, dy

    # ------------------------------------------------------------ main frame
    def _active_line(self, scene: TimedScene, t: float) -> TimedLine:
        tl = scene.active_line(t)
        if tl is None:
            for cand in scene.lines:
                if cand.start <= t:
                    tl = cand
                else:
                    break
            tl = tl or scene.lines[0]
        return tl

    def frame_at(self, t: float) -> Image.Image:
        scene = self.timeline.scene_at(t)
        tl = self._active_line(scene, t)
        shot = self._shot_for(tl)

        if shot == SHOT_CLOSEUP:
            img = self._closeup_backdrop(scene.scene_index).copy()
            base, is_dark = (18, 14, 13), True
        else:
            bg, base, is_dark = self.background(scene.background)
            img = bg.copy()
            if shot == SHOT_MEDIUM:
                img.paste(self._dim_overlay(), (0, 0), self._dim_overlay())
                is_dark = True
        draw = ImageDraw.Draw(img)

        self._draw_staging(draw, t, base, is_dark, tl, shot, scene)

        if scene.caption:
            self._draw_caption(img, scene.caption, is_dark)

        if self.chapter_cards:
            ch = self.timeline.chapter_at(t)
            if ch is not None and ch.show_card and t - ch.start < CARD_SECONDS:
                self._draw_chapter_card(img, ch.title, ch.index, (t - ch.start) / CARD_SECONDS)

        if self.watermark:
            font = load_font(self.font_path, int(self.ch * 0.024))
            wm_ink = mix(INK_LIGHT if is_dark else INK_DARK, base, 0.45)
            w, h = text_size(draw, self.watermark, font)
            draw.text((self.cw - w - self.ch * 0.03, self.ch - h - self.ch * 0.05),
                      self.watermark, font=font, fill=wm_ink)

        if self.progress_bar:
            frac = min(1.0, t / max(1e-6, self.timeline.duration))
            bar_h = max(4, int(self.ch * 0.006))
            draw.rectangle([0, self.ch - bar_h, self.cw * frac, self.ch], fill=self.accent)

        # Camera: crop + downscale in one resize.
        zoom, dx, dy = self._camera(t, shot, tl)
        zoom = max(1.0, zoom)
        vw, vh = self.cw / zoom, self.ch / zoom
        x0 = max(0.0, min(self.cw - vw, (self.cw - vw) / 2 + dx))
        y0 = max(0.0, min(self.ch - vh, (self.ch - vh) / 2 + dy))
        box = (x0, y0, min(float(self.cw), x0 + vw), min(float(self.ch), y0 + vh))
        return img.resize((self.W, self.H), Image.BILINEAR, box=box)

    def frames(self, log=print) -> Iterator[bytes]:
        total = int(math.ceil(self.timeline.duration * self.fps))
        report = max(1, total // 20)
        for i in range(total):
            if i % report == 0:
                log(f"    [render] frame {i}/{total} ({100 * i // total}%)")
            yield self.frame_at(i / self.fps).tobytes()
        log(f"    [render] frame {total}/{total} (100%)")
