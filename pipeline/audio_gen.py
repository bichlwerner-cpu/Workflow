"""Procedural audio: sound-effect track + background-music bed.

Both are synthesised with the Python standard library only (no numpy / no extra
pip installs), written as 16-bit mono WAV, and mixed by the assembler:

  - SFX track  (output/<slug>/sfx.wav): swooshes on hard cuts, clicks when an
    icon pops, low impacts on shock beats — timed to the same shot edits the
    renderer uses, so picture and sound hit together.
  - Music bed  (assets/music/bgm.wav): a soft, seamless ~16 s loop (warm pad +
    slow sub pulse + quiet hats) that ffmpeg loops under the whole video and
    side-chain ducks beneath the narration.

The music loop is seamless by construction: every oscillator frequency is
snapped to an integer multiple of 1/loop_len, so each sine completes whole
cycles and there is no click at the loop point.
"""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path
from typing import Callable, List

# --------------------------------------------------------------------------- rng

class _Noise:
    """Deterministic white noise in [-1, 1] (linear congruential)."""

    def __init__(self, seed: int = 1234567):
        self.s = seed & 0xFFFFFFFF

    def __call__(self) -> float:
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return (self.s / 0x3FFFFFFF) - 1.0


# ----------------------------------------------------------------- one-shot SFX

def _swoosh(sr: int, dur: float = 0.22, amp: float = 0.34) -> List[float]:
    """Filtered-noise sweep — the 'cut' transition sound."""
    n = int(sr * dur)
    out = [0.0] * n
    rng = _Noise(99)
    lp = 0.0
    for i in range(n):
        u = i / n
        raw = rng()
        a = 0.04 + 0.55 * (math.sin(math.pi * u) ** 2)   # cutoff swells mid-sweep
        lp += a * (raw - lp)
        band = raw - lp                                  # high-passed = airy
        env = (math.sin(math.pi * u) ** 1.4)
        out[i] = band * env * amp
    return out


def _click(sr: int, dur: float = 0.06, amp: float = 0.32) -> List[float]:
    """Short bright tick — an icon snapping in."""
    n = int(sr * dur)
    out = [0.0] * n
    rng = _Noise(7)
    for i in range(n):
        env = math.exp(-28.0 * i / sr)
        tone = math.sin(2 * math.pi * 1150 * i / sr)
        out[i] = (0.7 * tone + 0.3 * rng()) * env * amp
    return out


def _impact(sr: int, dur: float = 0.40, amp: float = 0.45) -> List[float]:
    """Low thump for shock / punch beats."""
    n = int(sr * dur)
    out = [0.0] * n
    rng = _Noise(2024)
    for i in range(n):
        u = i / n
        f = 120.0 - 65.0 * u                             # pitch drops
        env = math.exp(-7.0 * u)
        body = math.sin(2 * math.pi * f * i / sr) * env
        transient = rng() * math.exp(-60.0 * u) * 0.4
        out[i] = (body + transient) * amp
    return out


def _add(buf: array.array, samples: List[float], start: int, gain: float = 1.0) -> None:
    n = len(buf)
    for i, s in enumerate(samples):
        j = start + i
        if 0 <= j < n:
            v = buf[j] + int(max(-1.0, min(1.0, s * gain)) * 32767)
            buf[j] = -32768 if v < -32768 else 32767 if v > 32767 else v


def synth_sfx_track(settings, timeline, out_path: Path, log=print) -> Path:
    """Build the full-length SFX track aligned to the timeline's shot edits."""
    from .shots import resolve_shots
    sr = settings.sample_rate
    total = int(round(timeline.duration * sr)) + sr // 2
    buf = array.array("h", bytes(2 * total))

    swoosh = _swoosh(sr)
    click = _click(sr)
    impact = _impact(sr)

    shots = resolve_shots(timeline)
    prev_shot = ""
    first = True
    for scene in timeline.scenes:
        for tl in scene.lines:
            v = tl.voiced
            shot = shots.get(v.line_id, "wide")
            start = int(round(tl.start * sr))
            # Swoosh on a real cut: scene change or a change of framing.
            if not first and shot != prev_shot:
                _add(buf, swoosh, start - len(swoosh) // 3, 0.9)
            if v.prop != "none":
                _add(buf, click, start, 0.9)
            if v.camera in ("shake", "punch"):
                _add(buf, impact, start, 1.0)
            prev_shot = shot
            first = False

    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())
    log(f"    [audio] sfx track: {out_path.name}")
    return out_path


# --------------------------------------------------------------------- music bed

# vi-IV-I-V in C (Am - F - C - G): calm, slightly wistful, non-distracting.
_PROGRESSION = [
    (110.00, 130.81, 164.81),   # Am
    (87.31, 110.00, 130.81),    # F
    (130.81, 164.81, 196.00),   # C
    (98.00, 123.47, 146.83),    # G
]


def _make_music_loop(sr: int, loop_len: float = 16.0, gain: float = 0.5) -> array.array:
    n = int(sr * loop_len)
    loop_freq = 1.0 / loop_len

    def snap(f: float) -> float:
        return max(loop_freq, round(f / loop_freq) * loop_freq)

    seg = loop_len / len(_PROGRESSION)
    xf = 0.6                                   # chord cross-fade (s)
    beats = 16
    beat = loop_len / beats
    rng = _Noise(555)
    # Pre-snap all oscillator frequencies for seamless looping.
    chords = [[snap(f) for f in tri] for tri in _PROGRESSION]
    subs = [snap(tri[0] / 2.0) for tri in _PROGRESSION]

    out = array.array("h", bytes(2 * n))
    for i in range(n):
        t = i / sr
        pos = t % loop_len
        c = int(pos // seg) % len(chords)
        nxt = (c + 1) % len(chords)
        local = pos - c * seg
        blend = (local - (seg - xf)) / xf if local > seg - xf else 0.0
        blend = max(0.0, min(1.0, blend))

        # Pad: current chord, cross-fading into the next near the boundary.
        pad = 0.0
        for f in chords[c]:
            pad += math.sin(2 * math.pi * f * t)
        pad *= (1.0 - blend)
        if blend > 0:
            nb = 0.0
            for f in chords[nxt]:
                nb += math.sin(2 * math.pi * f * t)
            pad += nb * blend
        pad *= 0.10 / 3.0                      # 3 partials -> keep headroom

        # Sub pulse on each beat (soft attack, short decay).
        bpos = (pos % beat) / beat
        sub_env = math.exp(-3.2 * bpos) * (1.0 - math.exp(-40.0 * bpos))
        sub = math.sin(2 * math.pi * subs[c] * t) * sub_env * 0.16

        # Quiet hat tick on the off-beat for gentle pace.
        hpos = pos % (beat / 2)
        hat = 0.0
        if hpos < 0.05:
            hat = rng() * math.exp(-70.0 * hpos) * 0.025

        v = (pad + sub + hat) * gain
        s = int(max(-1.0, min(1.0, v)) * 32767)
        out[i] = s
    return out


def ensure_bgm(settings, log=print) -> None:
    """Generate the music bed if the configured bgm file is missing."""
    from .config import ROOT
    raw = settings.get("audio", "bgm_path", default="")
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    log(f"    [audio] generating background music loop -> {path.name}")
    sr = settings.sample_rate
    loop = _make_music_loop(sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(loop.tobytes())
