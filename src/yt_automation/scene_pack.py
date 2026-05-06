"""Scene-pack extraction.

Take a long source video (e.g. a downloaded YouTube clip) and split it into
short, motion-rich clips suitable for fast-cut B-roll. Uses PySceneDetect for
shot boundaries, FFmpeg for re-encoding, and a motion filter to drop static
or near-black scenes.

NOTE: Same copyright caveat as `footage.py` — only extract from material you
have a license for. Pipeline does not implement detection evasion.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from scenedetect import ContentDetector, SceneManager, open_video


@dataclass
class Scene:
    index: int
    start: float
    end: float
    duration: float
    path: Path
    motion_score: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


def _detect_scenes(
    source: Path, threshold: float, min_len_seconds: float
) -> list[tuple[float, float]]:
    video = open_video(str(source))
    fps = video.frame_rate or 30.0
    min_len_frames = max(1, int(min_len_seconds * fps))

    sm = SceneManager()
    sm.add_detector(
        ContentDetector(threshold=threshold, min_scene_len=min_len_frames)
    )
    sm.detect_scenes(video=video, show_progress=False)
    raw = sm.get_scene_list()
    return [(s[0].get_seconds(), s[1].get_seconds()) for s in raw]


def _split_long_scenes(
    scenes: list[tuple[float, float]], max_len: float
) -> list[tuple[float, float]]:
    """Cut scenes that exceed max_len into max_len-sized chunks."""
    out: list[tuple[float, float]] = []
    for start, end in scenes:
        cur = start
        while end - cur > max_len:
            out.append((cur, cur + max_len))
            cur += max_len
        if end - cur > 0.4:
            out.append((cur, end))
    return out


def _motion_score(source: Path, start: float, end: float) -> float:
    """Mean YDIF (frame-to-frame Y-channel diff) — higher = more motion.

    Returns 0 on failure rather than blocking the whole pack.
    """
    if not shutil.which("ffmpeg"):
        return 0.0
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(source),
        "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YDIF",
        "-f", "null",
        "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    diffs: list[float] = []
    for line in res.stderr.splitlines():
        if "lavfi.signalstats.YDIF=" in line:
            try:
                diffs.append(float(line.rsplit("=", 1)[1]))
            except ValueError:
                continue
    if not diffs:
        return 0.0
    return sum(diffs) / len(diffs)


def _cut(source: Path, start: float, end: float, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(source),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def extract(
    source: Path,
    out_dir: Path,
    *,
    threshold: float = 27.0,
    min_len: float = 2.0,
    max_len: float = 6.0,
    min_motion: float = 1.5,
    keep_top: int | None = None,
) -> list[Scene]:
    """Detect scenes in `source`, write clips to `out_dir/<source.stem>/`.

    `min_motion` filters static frames (title cards, blank intros).
    `keep_top` (optional) keeps only the N highest-motion scenes.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")
    if not source.exists():
        raise FileNotFoundError(source)

    pack_dir = out_dir / source.stem
    pack_dir.mkdir(parents=True, exist_ok=True)

    raw_scenes = _detect_scenes(source, threshold, min_len)
    if not raw_scenes:
        raise RuntimeError(
            f"No scenes detected in {source.name}. "
            "Try lowering SCENE_THRESHOLD or check the source isn't a single static shot."
        )

    chunks = _split_long_scenes(raw_scenes, max_len)
    chunks = [(s, e) for s, e in chunks if (e - s) >= min_len]

    scored: list[tuple[float, float, float]] = []
    for start, end in chunks:
        score = _motion_score(source, start, end)
        if score >= min_motion:
            scored.append((start, end, score))

    if not scored:
        raise RuntimeError(
            f"All scenes filtered out (min_motion={min_motion}). "
            "Lower SCENE_MIN_LEN or pass --min-motion 0 to keep everything."
        )

    scored.sort(key=lambda t: t[2], reverse=True)
    if keep_top is not None:
        scored = scored[:keep_top]
    scored.sort(key=lambda t: t[0])

    scenes: list[Scene] = []
    for i, (start, end, score) in enumerate(scored):
        out_path = pack_dir / f"scene_{i:03d}.mp4"
        _cut(source, start, end, out_path)
        scenes.append(
            Scene(
                index=i,
                start=start,
                end=end,
                duration=end - start,
                path=out_path,
                motion_score=score,
            )
        )

    manifest = pack_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": str(source),
                "threshold": threshold,
                "min_len": min_len,
                "max_len": max_len,
                "min_motion": min_motion,
                "scenes": [s.to_dict() for s in scenes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return scenes


def load_pack(pack_dir: Path) -> list[Scene]:
    """Read scenes from a previously-generated pack directory."""
    manifest = pack_dir / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(f"No manifest in {pack_dir}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [
        Scene(
            index=s["index"],
            start=s["start"],
            end=s["end"],
            duration=s["duration"],
            path=Path(s["path"]),
            motion_score=s["motion_score"],
        )
        for s in data["scenes"]
    ]


def list_packs(footage_dir: Path) -> list[Path]:
    """All directories under footage_dir that contain a manifest.json."""
    if not footage_dir.exists():
        return []
    return sorted(
        p for p in footage_dir.iterdir()
        if p.is_dir() and (p / "manifest.json").exists()
    )
