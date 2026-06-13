"""Generate consistent character images with Gemini image models ("Nano Banana").

Feed one or more reference images of a figure plus a prompt; the model returns a
new image of the *same* character in a new pose/scene. Nano Banana (Pro) is built
for character consistency, so this is the path for a richer illustrated look than
the code-defined vector mascot in ``character.py`` -- and you can use the vector
mascot itself as the reference to lock the design.

The model id is configurable (``GEMINI_IMAGE_MODEL``); the same ``GEMINI_API_KEY``
used for scripts works here too.
"""

from __future__ import annotations

import io
from pathlib import Path

from .config import Config

DEFAULT_STYLE = (
    "Flat 2D vector cartoon style, clean thick consistent outlines, soft shading, "
    "friendly and modern."
)

# Natural-language actions for a consistent pose set. Edit freely.
POSE_PROMPTS: dict[str, str] = {
    "idle":          "standing relaxed and facing forward, friendly",
    "wave":          "waving one hand, smiling",
    "point_up":      "pointing upward with one finger, like having an idea",
    "point_side":    "pointing to the side, presenting something",
    "thumbs_up":     "giving a thumbs up, happy",
    "thinking":      "one hand near the chin, thoughtful expression",
    "explain":       "both hands open mid-gesture, explaining a concept",
    "hand_on_heart": "one hand on the chest, sincere and empathetic",
    "shrug":         "shrugging with both palms up, unsure",
    "celebrate":     "both arms raised, celebrating",
    "count_three":   "holding up three fingers",
    "mind_blown":    "both hands near the head, amazed, mind blown",
    "sitting":       "sitting calmly and talking",
    "walking":       "walking in side view, mid-step",
}


def build_prompt(action: str, style: str = DEFAULT_STYLE, *, background: str = "plain flat") -> str:
    return (
        "Use the EXACT SAME character shown in the reference image(s): keep the "
        "identical design, colours, proportions, outfit and accessories. Do not "
        f"redesign or restyle the character. Now show them {action}. "
        f"{style} Full body, centered composition, {background} background. "
        "Keep the character 100% consistent with the reference."
    )


def _images_from_response(response) -> list:
    from PIL import Image

    imgs: list = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if not data:
                continue
            try:
                imgs.append(part.as_image())
            except Exception:
                imgs.append(Image.open(io.BytesIO(data)))
    return imgs


def _text_from_response(response) -> str:
    chunks: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
    return "\n".join(chunks)


def generate_figure(
    cfg: Config,
    prompt: str,
    out_path: Path,
    *,
    references: list[Path] | None = None,
) -> Path:
    """Generate one image from `prompt` (+ optional reference images) and save it."""
    cfg.require_gemini()
    from google import genai
    from PIL import Image

    client = genai.Client(api_key=cfg.gemini_api_key)

    contents: list = [prompt]
    for ref in references or []:
        contents.append(Image.open(ref))

    response = client.models.generate_content(
        model=cfg.gemini_image_model,
        contents=contents,
    )
    images = _images_from_response(response)
    if not images:
        raise RuntimeError(
            f"{cfg.gemini_image_model} returned no image. "
            f"Model text: {_text_from_response(response)[:300] or '(none)'}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out_path)
    return out_path


def generate_pose_set(
    cfg: Config,
    references: list[Path],
    out_dir: Path,
    *,
    prompts: dict[str, str] | None = None,
    style: str = DEFAULT_STYLE,
    background: str = "plain flat",
) -> list[Path]:
    """Generate a whole consistent set of poses for the same reference character."""
    prompts = prompts or POSE_PROMPTS
    written: list[Path] = []
    for name, action in prompts.items():
        out = out_dir / f"{name}.png"
        generate_figure(
            cfg,
            build_prompt(action, style, background=background),
            out,
            references=references,
        )
        written.append(out)
    return written
