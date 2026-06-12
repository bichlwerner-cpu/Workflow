"""Script generation via Claude (paid, best quality) or Gemini (free tier).

Strategy for long-form quality (same for both providers):
  1. one OUTLINE call -> title options, chapter plan with open loops, metadata
  2. one call for the HOOK (cold open), one per CHAPTER, one for the OUTRO,
     each receiving the outline plus the tail of the previous section so the
     dialogue flows continuously.

Claude uses native structured outputs (schema-enforced). Gemini uses JSON
mode + pydantic validation with a repair retry; out-of-vocabulary values are
coerced by the model validators, so every script stays renderable.
"""

from __future__ import annotations

import json
import time
from typing import List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import Settings, require_env
from .models import Chapter, Outline, Scene, ScenesPayload, Script
from .vocab import ACTIONS, BACKGROUNDS, EMOTIONS, POSES, PROPS

T = TypeVar("T", bound=BaseModel)

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"

LANG_NAMES = {"en": "English", "de": "German"}


def _cast_block(settings: Settings) -> str:
    rows = []
    for c in settings.characters.values():
        rows.append(f'- "{c.key}" ({c.display_name}): {c.persona}')
    return "\n".join(rows)


def build_system_prompt(settings: Settings) -> str:
    lang = LANG_NAMES.get(settings.get("language", default="en"), "English")
    return f"""You are the head writer AND visual director of a YouTube channel that makes long-form \
psychology explainers. ONE narrator speaks the entire voiceover; silent animated stickman characters \
act out every beat on screen like a film. Your videos hit millions of views because the writing is \
genuinely fascinating AND the screen never stops moving.

LANGUAGE: write all narration, titles and captions in {lang}.

FORMAT: every "line" is one NARRATION BEAT = the narrator's text (8-22 words) PLUS stage directions \
("actors"): which characters are on screen, their pose, emotion and movement action. The narrator is \
never visible. Characters never speak — they perform what the narration describes.

CAST of silent actors (use ONLY these character keys):
{_cast_block(settings)}

RENDERER VOCABULARY (every value must come from these lists):
- poses: {", ".join(POSES)}
- emotions: {", ".join(EMOTIONS)}
- actions (movement): {", ".join(ACTIONS)}
- backgrounds: {", ".join(BACKGROUNDS)}
- props: {", ".join(PROPS)}

VISUAL DIRECTING RULES (this is what makes the video feel expensive):
1. The staging MUST change with every beat: different pose, action, prop, actor set or camera. Two \
identical consecutive beats are forbidden.
2. Change the BACKGROUND every 1-2 beats (one scene = one location/setup). Use the metaphor sets \
actively: mountain = goals/effort, path_split = decisions, wall = obstacles, pit = failure/low point, \
graph = data/results, stage = spotlight/judgement, night = fear/rumination, chalkboard = explanation.
3. Use movement actions constantly: characters enter, walk across, approach each other, jump on wins, \
collapse on defeats, exit when dismissed. A beat where someone just stands is the exception.
4. ACT OUT the narration literally. "Your brain hits the brakes" -> actor collapses. "You finally try" \
-> actor enters and climbs toward the mountain flag. "Everyone judges you" -> two actors, one on stage, \
one pointing. Make the screen tell the same story as the voice.
5. 0 actors + a prop = a clean diagram shot (big icon) — use for numbers/concepts, max once per scene.
6. captions: max 6 words, for key terms, numbers, study names. Use about every 3rd scene.
7. camera: "shake" on shock beats, "zoom_in" on key reveals — at least one per scene.

RETENTION PLAYBOOK (non-negotiable):
1. COLD OPEN: hit a curiosity gap within the first 12 words. Tease the most surprising payoff without \
resolving it. No greetings, no "in this video".
2. OPEN LOOPS: every chapter ends on an unresolved question pulling into the next chapter.
3. PACE: short punchy sentences. Cut every filler word. A beat never exceeds 22 words. No throat-clearing.
4. CONCRETE > ABSTRACT: every mechanism gets a vivid mini-story or number. Constant second person \
("you") — the viewer must feel personally diagnosed.
5. RE-HOOKS: roughly every 90 seconds, remind the viewer what's still coming.
6. PAYOFFS: deliver real "aha" moments. A curiosity gap that ends in a banality kills the channel.

SCIENTIFIC INTEGRITY (also non-negotiable):
- Real psychology only. Name a study/researcher ONLY if it is real and well-established \
(e.g. Milgram, Kahneman & Tversky, Festinger, Zimbardo, Cialdini, Dunning-Kruger).
- If unsure about a specific citation, phrase it as a general, hedged finding instead of inventing one.
- No medical or therapeutic advice. No instructions for manipulating or harming specific people. \
Frame dark-psychology topics as "recognize and defend", never as a how-to against others.
- Titles and thumbnail must be fully covered by the content. Curiosity yes, lies never."""


class ScriptWriter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = str(settings.get("llm", "provider", default="gemini")).lower()
        self.max_tokens = int(settings.get("llm", "max_tokens", default=16000))
        self.system = build_system_prompt(settings)

        model = str(settings.get("llm", "model", default="") or "")
        if self.provider == "claude":
            require_env("ANTHROPIC_API_KEY")
            import anthropic
            self.client = anthropic.Anthropic()
            self.model = model if model.startswith("claude") else "claude-opus-4-8"
        elif self.provider == "gemini":
            self.api_key = require_env("GEMINI_API_KEY")
            self.model = model if model.startswith("gemini") else "gemini-2.5-flash"
        else:
            raise SystemExit(f"Unknown llm.provider '{self.provider}' (use 'gemini' or 'claude').")

    # ------------------------------------------------------------------ utils
    def _parse(self, user_prompt: str, schema: Type[T]) -> T:
        if self.provider == "gemini":
            return self._parse_gemini(user_prompt, schema)
        return self._parse_claude(user_prompt, schema)

    def _parse_claude(self, user_prompt: str, schema: Type[T]) -> T:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{
                "type": "text",
                "text": self.system,
                "cache_control": {"type": "ephemeral"},
            }],
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user_prompt}],
            output_format=schema,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude refused this request — rephrase the topic.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                "Hit max_tokens mid-generation. Raise llm.max_tokens in settings.yaml "
                "or lower video.target_minutes."
            )
        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError("Claude returned no parseable structured output.")
        return parsed

    def _parse_gemini(self, user_prompt: str, schema: Type[T]) -> T:
        import requests

        prompt = (
            f"{user_prompt}\n\n"
            f"Respond with ONLY a single JSON object (no markdown fences, no prose) "
            f"that validates against this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        headers = {"x-goog-api-key": self.api_key}

        last_err = "unknown error"
        for attempt in range(5):
            body = {
                "system_instruction": {"parts": [{"text": self.system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": self.max_tokens,
                },
            }
            url = f"{GEMINI_API}/{self.model}:generateContent"
            resp = requests.post(url, headers=headers, json=body, timeout=600)
            if resp.status_code in (429, 500, 502, 503):
                # Free-tier Pro quotas are small; fall back to Flash rather
                # than stalling the whole production.
                if resp.status_code == 429 and "pro" in self.model and attempt >= 1:
                    print(f"    [script] {self.model} rate-limited repeatedly; "
                          f"falling back to gemini-2.5-flash")
                    self.model = "gemini-2.5-flash"
                    continue
                wait = [10, 20, 40, 70, 70][attempt]
                print(f"    [script] Gemini busy/rate-limited ({resp.status_code}); "
                      f"waiting {wait}s (free tier allows only a few requests/min) ...")
                time.sleep(wait)
                continue
            if resp.status_code in (403, 404) and self.model != "gemini-2.5-flash":
                print(f"    [script] {self.model} unavailable on this key "
                      f"({resp.status_code}); falling back to gemini-2.5-flash")
                self.model = "gemini-2.5-flash"
                continue
            if resp.status_code >= 400:
                raise SystemExit(f"Gemini API error {resp.status_code}: {resp.text[:500]}")

            data = resp.json()
            if not data.get("candidates"):
                block = data.get("promptFeedback", {}).get("blockReason", "no candidates")
                raise RuntimeError(f"Gemini returned no output ({block}) — rephrase the topic.")
            cand = data["candidates"][0]
            if cand.get("finishReason") == "MAX_TOKENS":
                raise RuntimeError(
                    "Gemini hit max_tokens mid-generation. Raise llm.max_tokens in "
                    "settings.yaml or lower video.target_minutes."
                )
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            try:
                return schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = str(e)[:600]
                prompt = (
                    f"{user_prompt}\n\nYour previous JSON response was invalid:\n{last_err}\n\n"
                    f"Return ONLY a corrected JSON object matching this schema:\n"
                    f"{json.dumps(schema.model_json_schema())}"
                )
                print(f"    [script] Gemini JSON invalid, retrying ({attempt + 1}/5) ...")
        raise RuntimeError(f"Gemini failed to produce valid JSON after retries: {last_err}")

    @staticmethod
    def _tail_of(scenes: List[Scene], n_lines: int = 4) -> str:
        lines = [l for s in scenes for l in s.lines][-n_lines:]
        if not lines:
            return "(none)"
        return "\n".join(f"NARRATOR: {l.text}" for l in lines)

    # ----------------------------------------------------------------- stages
    def outline(self, topic: str) -> Outline:
        minutes = int(self.settings.get("video", "target_minutes", default=12))
        n_chapters = max(4, min(9, round(minutes / 2.2)))
        prompt = f"""Plan a ~{minutes} minute video on this psychology topic:

TOPIC: {topic}

Create the outline with exactly {n_chapters} chapters. Each chapter needs a clear goal, 3-6 beats and an \
open loop into the next chapter. The chapter sequence must escalate: start with the most relatable \
symptom/phenomenon, end with the most counterintuitive insight plus what to actually do with it.

Title options: 5 variants under 60 characters each, built on curiosity gaps, negativity bias, specificity \
(numbers, "you") — but every promise must be answerable by the chapter plan."""
        return self._parse(prompt, Outline)

    def _word_budgets(self, outline: Outline) -> dict:
        minutes = int(self.settings.get("video", "target_minutes", default=12))
        wpm = int(self.settings.get("video", "words_per_minute", default=150))
        total = minutes * wpm
        hook = max(60, int(total * 0.07))
        outro = max(50, int(total * 0.05))
        per_chapter = max(120, int((total - hook - outro) / max(1, len(outline.chapters))))
        return {"hook": hook, "outro": outro, "chapter": per_chapter}

    def hook(self, topic: str, outline: Outline) -> List[Scene]:
        budget = self._word_budgets(outline)["hook"]
        prompt = f"""TOPIC: {topic}
WORKING TITLE: {outline.working_title}
ANGLE: {outline.angle}
CHAPTER PLAN: {"; ".join(c.title for c in outline.chapters)}

Write the COLD OPEN (hook): 3-4 scenes, about {budget} spoken words total. It must open the video's core \
curiosity gap in the first beat, tease the most surprising payoff from the later chapters, and end on a \
hard open loop that makes skipping feel impossible. High visual energy: shocked/mind_blown beats, camera \
shake, fast staging changes in every beat."""
        return self._parse(prompt, ScenesPayload).scenes

    def chapter(self, topic: str, outline: Outline, index: int, previous: List[Scene]) -> Chapter:
        plan = outline.chapters[index]
        budget = self._word_budgets(outline)["chapter"]
        nxt = outline.chapters[index + 1].title if index + 1 < len(outline.chapters) else "the outro"
        prompt = f"""TOPIC: {topic}
WORKING TITLE: {outline.working_title}
FULL CHAPTER PLAN: {"; ".join(f"{i+1}. {c.title}" for i, c in enumerate(outline.chapters))}

You are writing CHAPTER {index + 1}: "{plan.title}"
GOAL: {plan.goal}
BEATS TO COVER: {"; ".join(plan.beats)}
OPEN LOOP TO END ON (leads into "{nxt}"): {plan.open_loop}

THE PREVIOUS SECTION ENDED WITH:
{self._tail_of(previous)}

Continue seamlessly from that ending (no recap, no greeting). Write 4-7 short scenes, about {budget} \
spoken words total. Cover all content beats with concrete acted-out examples, change the background \
every 1-2 narration beats, keep the actors moving, and end exactly on the open loop. Do NOT include a \
subscribe/like CTA or a "next time/next video" tease — those belong exclusively in the outro, never in \
a chapter."""
        scenes = self._parse(prompt, ScenesPayload).scenes
        return Chapter(title=plan.title, scenes=scenes)

    def outro(self, topic: str, outline: Outline, previous: List[Scene]) -> List[Scene]:
        budget = self._word_budgets(outline)["outro"]
        prompt = f"""TOPIC: {topic}
WORKING TITLE: {outline.working_title}

THE FINAL CHAPTER ENDED WITH:
{self._tail_of(previous)}

Write the OUTRO: 1-2 scenes, about {budget} spoken words. One satisfying closing beat that lands the \
video's big idea, one open loop teasing a related psychology topic for next week's video, and exactly \
one subscribe CTA woven in naturally (no begging). Do not repeat any tease or CTA wording that already \
appeared in the final chapter ending shown above."""
        return self._parse(prompt, ScenesPayload).scenes

    # ------------------------------------------------------------------- main
    def write(self, topic: str, log=print) -> Script:
        valid_chars = set(self.settings.characters.keys())

        log("  [script] generating outline ...")
        outline = self.outline(topic)
        log(f"  [script] outline: \"{outline.working_title}\" with {len(outline.chapters)} chapters")

        log("  [script] writing hook ...")
        hook = self.hook(topic, outline)

        chapters: List[Chapter] = []
        previous = hook
        for i in range(len(outline.chapters)):
            log(f"  [script] writing chapter {i + 1}/{len(outline.chapters)}: {outline.chapters[i].title} ...")
            ch = self.chapter(topic, outline, i, previous)
            chapters.append(ch)
            previous = ch.scenes

        log("  [script] writing outro ...")
        outro = self.outro(topic, outline, previous)

        script = Script(
            topic=topic,
            language=self.settings.get("language", default="en"),
            outline=outline,
            hook=hook,
            chapters=chapters,
            outro=outro,
        )
        _sanitize_characters(script, valid_chars)
        log(f"  [script] done: {script.word_count()} spoken words, "
            f"{sum(len(c.scenes) for c in script.chapters) + len(hook) + len(outro)} scenes")
        return script


def _sanitize_characters(script: Script, valid: set) -> None:
    """Map any unknown actor key (shouldn't happen, but belt & braces) to the first cast member."""
    fallback = sorted(valid)[0]
    for scene in script.all_scenes():
        for line in scene.lines:
            for actor in line.actors:
                if actor.character not in valid:
                    actor.character = fallback


def write_script(settings: Settings, topic: str, log=print) -> Script:
    return ScriptWriter(settings).write(topic, log=log)
