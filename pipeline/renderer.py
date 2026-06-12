"""Frame renderer: composes every video frame from the timeline.

Frames are drawn at `supersample`x resolution for clean anti-aliased lines,
then a camera transform (slow zoom, emphasis pulses, shake) crops + scales
down to the output size in a single resize. Frames are yielded as raw RGB
bytes and piped straight into ffmpeg — no intermediate image files.
"""

from __future__ import annotations

import math
from typing import Dict, Iterator, List, Optional, Tuple

from PIL import Image, ImageDraw

from .config import Settings
from .stickman import (COLLAPSED, animate_pose, draw_character, is_blinking,
                       lerp_pose)
from .timeline import TimedLine, TimedScene, Timeline
from .utils import RGB, hex_to_rgb, load_font, luminance, mix, text_size, wrap_text

INK_DARK = (27, 27, 31)
INK_LIGHT = (245, 241, 232)

CARD_SECONDS = 1.7
PROP_POP_SECONDS = 0.35
SHAKE_SECONDS = 0.7


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
        self._vignette: Optional[Image.Image] = None
        self._char_phase = {key: 2 * math.pi * _seeded(i + 1)
                            for i, key in enumerate(sorted(settings.characters))}

    # ----------------------------------------------------------- backgrounds
    def _vignette_overlay(self) -> Image.Image:
        if self._vignette is None:
            small = Image.new("L", (160, 90), 0)
            d = ImageDraw.Draw(small)
            cx, cy = 80, 45
            for y in range(90):
                for x in range(160):
                    dist = math.hypot((x - cx) / 80, (y - cy) / 45)
                    small.putpixel((x, y), int(70 * max(0.0, dist - 0.55) ** 1.6))
            mask = small.resize((self.cw, self.ch), Image.BILINEAR)
            overlay = Image.new("RGBA", (self.cw, self.ch), (10, 10, 14, 0))
            overlay.putalpha(mask)
            self._vignette = overlay
        return self._vignette

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
            for k in range(5, 0, -1):
                u = k / 5
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
                for k, side in enumerate((-1, 1)):
                    by = post_y - ch * (0.15 - 0.055 * k)
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
                      is_dark: bool, tl: TimedLine) -> None:
        """Render the current beat: 0-2 silent actors performing + their prop."""
        actors = tl.voiced.actors[:2]
        ink = INK_LIGHT if is_dark else INK_DARK
        t_line = max(0.0, t - tl.start)

        if not actors:
            if tl.voiced.prop != "none":  # diagram shot: big centered prop
                self._draw_prop(draw, tl.voiced.prop, (self.cw * 0.5, self.ch * 0.44),
                                self.ch * 0.20, ink, t_line)
            return

        dur = max(0.3, tl.end - tl.start)
        t_in = min(t_line, dur)
        ground_y = self.ch * 0.84
        scale = self.ch * (0.42 if len(actors) == 1 else 0.38)
        if len(actors) == 1:
            # Keep a lone actor clear of center-stage background elements.
            slots = [{"wall": 0.30, "pit": 0.30, "path_split": 0.36,
                      "mountain": 0.32}.get(self.timeline.scene_at(t).background, 0.5)]
        else:
            slots = [0.33, 0.67]
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
            pose = animate_pose(pose_name, t, phase, speaking=False)
            pose.y_offset += jump_y
            if collapse_u > 0:
                pose = lerp_pose(pose, COLLAPSED, collapse_u)

            draw_character(
                draw, (self.cw * x, ground_y), scale,
                color=self._ink_for(hex_to_rgb(cfg.color), base), bg_fill=base,
                pose=pose, emotion=a.get("emotion", "neutral"), mouth_open=False,
                blink=is_blinking(t, phase), facing=facing,
                accessory=cfg.accessory, hair=cfg.hair, accent=self.accent,
            )
            if i == 0:
                prop_anchor = (self.cw * x + facing * scale * 0.55,
                               ground_y - scale * 1.20)

        if tl.voiced.prop != "none" and prop_anchor is not None:
            self._draw_prop(draw, tl.voiced.prop, prop_anchor, scale * 0.30, ink, t_line)

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
            for k in range(6):
                ang = math.pi * (0.15 + 0.7 * k / 5) + math.pi  # rays over the top
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
            d = -1 if name == "arrow_up" else 1
            h, w2 = s * 0.55, s * 0.34
            draw.polygon([(cx, cy + d * h), (cx - w2, cy + d * h * 0.1),
                          (cx - w2 * 0.45, cy + d * h * 0.1), (cx - w2 * 0.45, cy - d * h * 0.8),
                          (cx + w2 * 0.45, cy - d * h * 0.8), (cx + w2 * 0.45, cy + d * h * 0.1),
                          (cx + w2, cy + d * h * 0.1)], fill=a)
        elif name == "star":
            pts = []
            for k in range(10):
                rr = s * (0.55 if k % 2 == 0 else 0.24)
                ang = -math.pi / 2 + k * math.pi / 5
                pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
            draw.polygon(pts, fill=a)
        elif name == "target":
            for k, rr in enumerate((0.5, 0.34, 0.18)):
                draw.ellipse([cx - s * rr, cy - s * rr, cx + s * rr, cy + s * rr],
                             outline=a if k % 2 == 0 else ink, width=fw)
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
        font = load_font(self.font_path, int(self.ch * 0.046))
        lines = wrap_text(d, text, font, int(self.cw * 0.7))
        pad = int(self.ch * 0.018)
        line_h = int(self.ch * 0.055)
        block_w = max(text_size(d, ln, font)[0] for ln in lines)
        x0 = (self.cw - block_w) / 2 - pad * 1.6
        y0 = self.ch * 0.06
        pill = (20, 20, 26, 200) if not is_dark else (245, 241, 232, 220)
        ink = INK_LIGHT if not is_dark else INK_DARK
        d.rounded_rectangle(
            [x0, y0, x0 + block_w + pad * 3.2, y0 + len(lines) * line_h + pad * 2],
            radius=int(self.ch * 0.02), fill=pill)
        for i, ln in enumerate(lines):
            w, _ = text_size(d, ln, font)
            d.text(((self.cw - w) / 2, y0 + pad + i * line_h), ln, font=font, fill=ink)
        img.paste(overlay, (0, 0), overlay)

    def _draw_chapter_card(self, img: Image.Image, title: str, index: int, u: float) -> None:
        """u in [0,1] across the card window; fades in/out."""
        alpha = min(1.0, u * 6, (1 - u) * 6)
        if alpha <= 0:
            return
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rectangle([0, 0, self.cw, self.ch], fill=(12, 12, 16, int(185 * alpha)))
        font_big = load_font(self.font_path, int(self.ch * 0.075))
        font_small = load_font(self.font_path, int(self.ch * 0.032))
        kicker = f"PART {index + 1}"
        ty = self.ch * 0.22
        w, _ = text_size(d, kicker, font_small)
        d.text(((self.cw - w) / 2, ty - self.ch * 0.06), kicker, font=font_small,
               fill=(*self.accent, int(255 * alpha)))
        for i, ln in enumerate(wrap_text(d, title, font_big, int(self.cw * 0.8))):
            w, _ = text_size(d, ln, font_big)
            d.text(((self.cw - w) / 2, ty + i * self.ch * 0.09), ln, font=font_big,
                   fill=(245, 241, 232, int(255 * alpha)))
        bar_w = self.cw * 0.12
        d.rectangle([(self.cw - bar_w) / 2, ty - self.ch * 0.015,
                     (self.cw + bar_w) / 2, ty - self.ch * 0.008],
                    fill=(*self.accent, int(255 * alpha)))
        img.paste(overlay, (0, 0), overlay)

    # ---------------------------------------------------------------- camera
    def _camera(self, t: float, scene: TimedScene, active: Optional[TimedLine]) -> Tuple[float, float, float]:
        dur = max(1.0, scene.end - scene.start)
        progress = min(1.0, max(0.0, (t - scene.start) / dur))
        zoom = 1.0 + 0.06 * progress
        # Slow horizontal drift, alternating direction per scene, for constant
        # subtle motion even in still beats.
        dx = (1 if scene.scene_index % 2 else -1) * 0.012 * self.cw * progress
        dy = 0.0
        if active is not None:
            since = t - active.start
            if active.voiced.camera == "zoom_in":
                zoom += 0.06 * math.sin(min(1.0, since / 0.35) * math.pi / 2)
            elif active.voiced.camera == "shake" and since < SHAKE_SECONDS:
                amp = self.ch * 0.008 * (1 - since / SHAKE_SECONDS)
                dx = amp * math.sin(since * 73)
                dy = amp * math.cos(since * 61)
        return zoom, dx, dy

    # ------------------------------------------------------------ main frame
    def frame_at(self, t: float) -> Image.Image:
        scene = self.timeline.scene_at(t)
        bg, base, is_dark = self.background(scene.background)
        img = bg.copy()
        draw = ImageDraw.Draw(img)

        # Current beat — or hold the most recent beat's staging during gaps.
        tl = scene.active_line(t)
        if tl is None:
            for cand in scene.lines:
                if cand.start <= t:
                    tl = cand
                else:
                    break
            tl = tl or scene.lines[0]
        self._draw_staging(draw, t, base, is_dark, tl)
        active = tl

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
            draw.text((self.cw - w - self.ch * 0.03, self.ch - h - self.ch * 0.045),
                      self.watermark, font=font, fill=wm_ink)

        if self.progress_bar:
            frac = min(1.0, t / max(1e-6, self.timeline.duration))
            bar_h = max(4, int(self.ch * 0.006))
            draw.rectangle([0, self.ch - bar_h, self.cw * frac, self.ch], fill=self.accent)

        # Camera: crop + downscale in one resize.
        zoom, dx, dy = self._camera(t, scene, active)
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
