"""Psychology content for a fast-paced stickman channel.

Produces a :class:`StickScript`: a title/description/tags plus an ordered list
of :class:`ScriptBeat` — one punchy spoken line each, with an assigned stickman
action, a big on-screen keyword, and an intensity (0..1).

Three sources, in quality order:
  1. ``claude``  — Claude writes a fresh, factual, retention-tuned script.
  2. ``curated`` — hand-written scripts for popular topics (great, offline).
  3. ``template``— structural fallback for any topic (functional, offline).

Editorial stance: this is *educational* psychology — understanding your own
mind and **recognising** manipulation, not how-to-manipulate. Topics are framed
for awareness and self-improvement.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..config import Config

# Action vocabulary the animation engine understands (see stickman.actions).
ACTION_VOCAB = [
    "idle", "walk", "run", "point", "point_up", "think", "idea", "shrug",
    "cheer", "panic", "facepalm", "punch", "power", "fall", "jump", "stomp",
]

# A sensible intensity per action so authors can omit it.
_DEFAULT_INTENSITY = {
    "idle": 0.35, "walk": 0.45, "run": 0.8, "point": 0.7, "point_up": 0.75,
    "think": 0.4, "idea": 0.85, "shrug": 0.5, "cheer": 0.9, "panic": 0.95,
    "facepalm": 0.55, "punch": 0.95, "power": 0.85, "fall": 0.7, "jump": 0.85,
    "stomp": 0.9,
}


class ScriptBeat(BaseModel):
    text: str = Field(description="One spoken sentence. Punchy, 4-14 words.")
    action: str = Field(default="point", description="Stickman action key.")
    keyword: str | None = Field(
        default=None, description="Big on-screen word, 1-2 words, UPPER ok. May be null."
    )
    intensity: float | None = Field(
        default=None, description="0..1. Drives shake/flash/zoom. Omit for a default."
    )

    def resolved_intensity(self) -> float:
        if self.intensity is not None:
            return max(0.0, min(1.0, self.intensity))
        return _DEFAULT_INTENSITY.get(self.action, 0.6)


class StickScript(BaseModel):
    title: str = Field(description="YouTube title, <=70 chars, hook-driven.")
    description: str = Field(description="2-3 sentence description.")
    tags: list[str] = Field(description="6-12 lowercase tags.")
    beats: list[ScriptBeat] = Field(description="6-12 ordered beats.")
    theme: str = Field(default="midnight", description="Visual theme key.")

    def voiceover_lines(self) -> list[str]:
        return [b.text.strip() for b in self.beats if b.text.strip()]


# ---------------------------------------------------------------------------
# Topic bank  (title, angle/keywords used by the template generator)
# ---------------------------------------------------------------------------

TOPICS: list[tuple[str, str]] = [
    ("The Spotlight Effect", "nobody is watching you as closely as you think"),
    ("Negativity Bias", "why one insult outweighs ten compliments"),
    ("The Dopamine Trap", "why your phone feels impossible to put down"),
    ("Why You Procrastinate", "your brain treats future-you like a stranger"),
    ("Spotting Gaslighting", "how to recognise reality being rewritten"),
    ("The Zeigarnik Effect", "unfinished tasks haunt your mind on purpose"),
    ("The Dunning-Kruger Effect", "the less you know, the smarter you feel"),
    ("The 5-Second Rule", "beat fear before your brain talks you out of it"),
    ("Loss Aversion", "losing 100 hurts twice as much as winning 100"),
    ("The Mere Exposure Effect", "you like things just because they're familiar"),
    ("Cognitive Dissonance", "why you defend decisions you know are wrong"),
    ("The Halo Effect", "one good trait makes us assume all the rest"),
    ("Imposter Syndrome", "the smarter you are, the more you doubt yourself"),
    ("Parkinson's Law", "work expands to fill the time you give it"),
    ("Anchoring Bias", "the first number you hear hijacks every judgement"),
    ("The Paradox of Choice", "more options make you less happy"),
    ("Ego Depletion", "willpower runs out like a battery"),
    ("The Benjamin Franklin Effect", "doing someone a favour makes you like them"),
    ("Hedonic Adaptation", "why nothing makes you happy for long"),
    ("The Pratfall Effect", "small flaws make you more likeable, not less"),
]


def list_topics() -> list[tuple[str, str]]:
    return list(TOPICS)


# ---------------------------------------------------------------------------
# Curated scripts (offline, high quality)
# ---------------------------------------------------------------------------

def _b(text: str, action: str, keyword: str | None = None, intensity: float | None = None):
    return ScriptBeat(text=text, action=action, keyword=keyword, intensity=intensity)


CURATED: dict[str, StickScript] = {
    "the spotlight effect": StickScript(
        title="Nobody Is Watching You (The Spotlight Effect)",
        description="You think everyone notices your every mistake. Here's the brutal psychological truth about the spotlight effect — and why it sets you free.",
        tags=["psychology", "spotlight effect", "social anxiety", "confidence",
              "mindset", "self improvement", "shorts"],
        beats=[
            _b("You walk in and feel everyone staring at you.", "panic", "STARING", 0.9),
            _b("Here's the truth: almost no one noticed.", "shrug", "NO ONE", 0.7),
            _b("It's called the spotlight effect.", "point", "SPOTLIGHT", 0.75),
            _b("Your brain makes you the main character of every room.", "think", "MAIN CHARACTER", 0.6),
            _b("But everyone else is busy starring in their own movie.", "facepalm", "THEIR MOVIE", 0.6),
            _b("Studies show people remember your slip-ups half as much as you do.", "point", "HALF", 0.7),
            _b("So that embarrassing moment? Already forgotten.", "idea", "FORGOTTEN", 0.85),
            _b("Stop performing for an audience that isn't watching.", "power", "BE FREE", 0.9),
            _b("Follow for the psychology they never taught you.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "negativity bias": StickScript(
        title="Why One Insult Beats Ten Compliments",
        description="Ten people praise you, one criticises you — and you only think about the one. That's negativity bias, and here's how to beat it.",
        tags=["psychology", "negativity bias", "mindset", "criticism",
              "mental health", "self improvement", "shorts"],
        beats=[
            _b("Ten people praise you. One criticises you.", "shrug", "10 vs 1", 0.7),
            _b("Guess which one keeps you up at night.", "facepalm", "THE 1", 0.75),
            _b("This is negativity bias.", "point", "NEGATIVITY BIAS", 0.8),
            _b("Your brain treats bad news as a survival threat.", "panic", "THREAT", 0.9),
            _b("A bad review felt like a tiger to your ancestors.", "run", "TIGER", 0.85),
            _b("So negativity gets burned in. Praise just evaporates.", "fall", "EVAPORATES", 0.7),
            _b("The fix? Write down three wins every single day.", "idea", "3 WINS", 0.85),
            _b("You're not negative. Your brain is just outdated.", "power", "OUTDATED", 0.9),
            _b("Follow if your brain needs a software update.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "the dopamine trap": StickScript(
        title="Why You Can't Put Your Phone Down",
        description="Your phone is engineered to hijack your dopamine. Here's exactly how the loop works — and how to break it.",
        tags=["psychology", "dopamine", "phone addiction", "focus", "discipline",
              "self improvement", "shorts"],
        beats=[
            _b("You picked up your phone for no reason. Again.", "facepalm", "AGAIN", 0.7),
            _b("That's not weakness. That's design.", "point", "DESIGN", 0.85),
            _b("Every notification gives you a tiny hit of dopamine.", "idea", "DOPAMINE", 0.8),
            _b("Dopamine isn't pleasure. It's craving.", "think", "CRAVING", 0.7),
            _b("So you chase the next swipe, and the next.", "run", "NEXT SWIPE", 0.85),
            _b("Apps use random rewards — the same trick as slot machines.", "panic", "SLOT MACHINE", 0.9),
            _b("Break it: make your phone boring. Grayscale, no badges.", "power", "GO GRAY", 0.85),
            _b("Bored beats hijacked. Take your focus back.", "stomp", "TAKE IT BACK", 0.9),
            _b("Follow for your daily dose of mind control... defence.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "why you procrastinate": StickScript(
        title="The Real Reason You Procrastinate",
        description="Procrastination isn't laziness — it's a battle between present-you and future-you. Here's how to win it.",
        tags=["psychology", "procrastination", "productivity", "discipline",
              "motivation", "self improvement", "shorts"],
        beats=[
            _b("You're not lazy. You're at war with yourself.", "punch", "AT WAR", 0.9),
            _b("Your brain sees future-you as a total stranger.", "shrug", "STRANGER", 0.7),
            _b("So it dumps the hard work on them, not you.", "facepalm", "NOT ME", 0.7),
            _b("Present-you wants the reward now.", "run", "NOW", 0.8),
            _b("That's why deadlines feel fake until they're tomorrow.", "think", "TOMORROW", 0.6),
            _b("The hack? Shrink the task until it's stupidly small.", "idea", "TINY", 0.85),
            _b("Don't write the essay. Open the document. That's it.", "point", "JUST OPEN IT", 0.8),
            _b("Motion kills hesitation. Start ugly, start now.", "power", "START NOW", 0.95),
            _b("Follow before future-you forgets.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "spotting gaslighting": StickScript(
        title="5 Signs Someone Is Gaslighting You",
        description="Gaslighting makes you doubt your own reality. Learn to recognise the tactics so no one can rewrite your mind.",
        tags=["psychology", "gaslighting", "manipulation", "toxic relationships",
              "mental health", "boundaries", "shorts"],
        beats=[
            _b("If you constantly question your own memory, listen up.", "think", "LISTEN", 0.7),
            _b("Gaslighting makes you doubt your own reality.", "panic", "DOUBT", 0.9),
            _b("Sign one: that never happened — when it clearly did.", "point", "IT HAPPENED", 0.8),
            _b("Sign two: you're too sensitive, every single time.", "facepalm", "TOO SENSITIVE", 0.75),
            _b("Sign three: they twist the story until you apologise.", "shrug", "YOU APOLOGISE", 0.75),
            _b("Sign four: you start keeping receipts to prove you're sane.", "point_up", "RECEIPTS", 0.8),
            _b("Your memory is not the problem. Trust the pattern.", "power", "TRUST IT", 0.9),
            _b("Name it, and it loses its power over you.", "stomp", "NAME IT", 0.9),
            _b("Follow to protect your mind, not just inform it.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "the zeigarnik effect": StickScript(
        title="Why Your Brain Won't Let Unfinished Tasks Go",
        description="That nagging feeling about half-done work has a name: the Zeigarnik effect. Here's how to use it instead of suffering from it.",
        tags=["psychology", "zeigarnik effect", "focus", "productivity",
              "memory", "self improvement", "shorts"],
        beats=[
            _b("There's a reason unfinished tasks haunt you.", "panic", "HAUNT", 0.85),
            _b("It's called the Zeigarnik effect.", "point", "ZEIGARNIK", 0.8),
            _b("Your brain keeps open loops loud and unforgettable.", "think", "OPEN LOOPS", 0.7),
            _b("A waiter remembers your order... until you pay.", "idea", "THE WAITER", 0.75),
            _b("Then it's instantly wiped. Loop closed.", "facepalm", "WIPED", 0.65),
            _b("That's why you can't relax with ten tabs open in your head.", "run", "TEN TABS", 0.85),
            _b("The trick: write the next step down. The loop quiets.", "point_up", "WRITE IT", 0.8),
            _b("Close the loop on paper, and your mind lets go.", "power", "LET GO", 0.85),
            _b("Follow to finally close the loop.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "the dunning-kruger effect": StickScript(
        title="The Less You Know, The Smarter You Feel",
        description="The Dunning-Kruger effect explains why beginners feel like experts and experts feel like frauds. Where are you on the curve?",
        tags=["psychology", "dunning kruger", "confidence", "learning",
              "ego", "self improvement", "shorts"],
        beats=[
            _b("The dumbest people are often the most confident.", "cheer", "CONFIDENT", 0.85),
            _b("This isn't an insult. It's the Dunning-Kruger effect.", "point", "DUNNING-KRUGER", 0.8),
            _b("When you know almost nothing, you can't see what you're missing.", "shrug", "BLIND", 0.7),
            _b("So beginners stand on a peak of fake confidence.", "power", "FAKE PEAK", 0.8),
            _b("Learn a little more, and you crash into reality.", "fall", "THE CRASH", 0.85),
            _b("Real experts actually doubt themselves the most.", "think", "DOUBT", 0.6),
            _b("So if you feel like a fraud — you might be good.", "idea", "MAYBE GOOD", 0.85),
            _b("Stay humble on the peak, stay brave in the valley.", "point_up", "STAY HUMBLE", 0.8),
            _b("Follow to climb the right side of the curve.", "cheer", "FOLLOW", 0.85),
        ],
    ),
    "the 5-second rule": StickScript(
        title="Beat Fear In 5 Seconds (Neuroscience Trick)",
        description="Your brain kills your courage in milliseconds. The 5-second rule hijacks that window. Here's the science.",
        tags=["psychology", "5 second rule", "motivation", "fear", "discipline",
              "mel robbins", "shorts"],
        beats=[
            _b("You get an impulse to act. Then you hesitate.", "think", "HESITATE", 0.6),
            _b("In five seconds, your brain talks you out of it.", "facepalm", "5 SECONDS", 0.8),
            _b("Fear floods in to keep you safe and small.", "panic", "FEAR", 0.9),
            _b("So beat it to the punch. Count backwards.", "point", "COUNT DOWN", 0.8),
            _b("Five. Four. Three. Two. One.", "run", "5-4-3-2-1", 0.9),
            _b("That countdown interrupts the fear circuit.", "idea", "INTERRUPT", 0.85),
            _b("Then move — before the excuse loads.", "punch", "MOVE", 0.95),
            _b("Courage isn't a feeling. It's a five-second decision.", "power", "DECIDE", 0.9),
            _b("Follow and start counting.", "cheer", "FOLLOW", 0.85),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Template generator (offline, any topic)
# ---------------------------------------------------------------------------

_HOOK_ACTIONS = ["point", "panic", "point_up", "punch"]
_BODY_ACTIONS = ["think", "shrug", "facepalm", "run", "idea", "point", "power"]
_KEYWORDS_BANK = ["WAIT", "TRUTH", "WHY", "STOP", "LISTEN", "REAL", "DANGER", "SECRET"]
_STOPWORDS = {"the", "a", "an", "of", "to", "in", "on", "for", "why", "how",
              "you", "your", "is", "are", "and", "or", "it"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# Curated scripts indexed by normalised key so topic strings match regardless
# of punctuation/casing ("The 5-Second Rule" -> "the 5 second rule").
CURATED_BY_SLUG: dict[str, StickScript] = {_slug(k): v for k, v in CURATED.items()}


def _template_script(title: str, angle: str, *, seed: int) -> StickScript:
    rng = random.Random(seed)
    kw = lambda i: _KEYWORDS_BANK[i % len(_KEYWORDS_BANK)]
    topic = title.strip()
    beats = [
        _b(f"Most people have no idea how {topic.lower()} controls them.", rng.choice(_HOOK_ACTIONS), "WAIT", 0.9),
        _b(f"{topic} — {angle}.", "point", topic.split()[0].upper(), 0.8),
        _b("And once you see it, you can't unsee it.", "idea", "SEE IT", 0.8),
        _b("Your brain runs this pattern automatically, every day.", "run", "EVERY DAY", 0.8),
        _b("It worked for survival. It sabotages you now.", "facepalm", "SABOTAGE", 0.7),
        _b("But awareness is the off switch.", "power", "OFF SWITCH", 0.85),
        _b("Catch it once, and you take back control.", "stomp", "CONTROL", 0.9),
        _b("Follow for the psychology they never taught you.", "cheer", "FOLLOW", 0.85),
    ]
    tags = ["psychology", "mindset", "self improvement", "shorts", "mental health"]
    tags += [w for w in _slug(topic).split() if len(w) > 2 and w not in _STOPWORDS][:4]
    return StickScript(
        title=topic if len(topic) <= 70 else topic[:67] + "...",
        description=f"{topic}: {angle}. The psychology explained fast.",
        tags=list(dict.fromkeys(tags)),
        beats=beats,
    )


# ---------------------------------------------------------------------------
# Claude generator (best quality)
# ---------------------------------------------------------------------------

_SYSTEM = """You are the head writer for a fast-paced, high-retention YouTube
psychology channel animated with stickmen. Your scripts are punchy, factual,
and intense.

Hard rules:
- Educational psychology only: help people understand their own minds and
  RECOGNISE manipulation. Never write how-to-manipulate or harmful content.
- Each beat is ONE spoken sentence, 4-14 words, natural spoken prose. No stage
  directions, no markdown, no emojis in the spoken text.
- Open with a pattern-interrupt hook in the first beat. End with a call to
  action ("Follow ...").
- 8 to 11 beats. Build curiosity, deliver a real insight, give one practical
  takeaway, then the CTA.
- For each beat choose an `action` from this exact list and a short `keyword`
  (1-2 words) that punches on screen:
  {actions}
- Pick `intensity` 0..1: hooks and climaxes high (0.85-0.95), calm explanation
  lower (0.4-0.6).
- Title <=70 chars, curiosity-driven. 6-12 lowercase tags."""


def _claude_script(cfg: Config, topic: str, angle: str | None) -> StickScript:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    user = (
        f"Topic: {topic}\n"
        + (f"Angle: {angle}\n" if angle else "")
        + "Write the full stickman script as structured JSON. Make it intense, "
        "fast, and genuinely informative."
    )
    resp = client.messages.parse(
        model=cfg.anthropic_model,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.anthropic_effort},
        system=[{
            "type": "text",
            "text": _SYSTEM.format(actions=", ".join(ACTION_VOCAB)),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user}],
        output_format=StickScript,
    )
    script = resp.parsed_output
    # sanitise actions the model might have invented
    for b in script.beats:
        if b.action not in ACTION_VOCAB:
            b.action = "point"
    return script


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

Source = Literal["auto", "claude", "curated", "template"]


# ---------------------------------------------------------------------------
# Long-form (4-6 min)
# ---------------------------------------------------------------------------

_LONG_SYSTEM = """You are the head writer for a fast-paced YouTube psychology
channel animated with a single recurring stickman mascot. Write a LONG-FORM
script (the spoken voiceover for a {minutes}-minute video).

Hard rules:
- Educational psychology only: understanding the mind and RECOGNISING
  manipulation. Never how-to-manipulate or harmful content.
- Each beat is ONE spoken sentence, 4-16 words, natural spoken prose.
- Structure: a gripping cold-open hook, then 5-8 sections each with a clear
  idea, a concrete example, and a takeaway; a recap; a strong CTA.
- Aim for about {n_beats} beats so the narration runs ~{minutes} minutes.
- For each beat pick an `action` from: {actions}; a short `keyword` (1-2 words);
  and `intensity` 0..1 (hooks/climaxes high, calm explanation lower).
- Title <=70 chars, curiosity-driven. 8-15 lowercase tags."""


def _compilation_script(minutes: int, *, seed: int) -> StickScript:
    """Offline long-form: stitch curated segments into an 'N facts' compilation."""
    rng = random.Random(seed)
    target = minutes * 60
    segs = list(CURATED.values())
    rng.shuffle(segs)
    # ~22s of body per segment + intro line; size the list to the target length.
    n = max(3, min(len(segs), round(target / 26)))
    chosen = segs[:n]

    beats: list[ScriptBeat] = [
        _b(f"Here are {n} psychology facts that will change how you read people.",
           "point", "PSYCHOLOGY", 0.92),
        _b("Most people go their whole lives never learning these.", "point_up", "MOST NEVER", 0.8),
    ]
    for idx, seg in enumerate(chosen, start=1):
        beats.append(_b(f"Number {idx}.", "stomp", f"#{idx}", 0.9))
        # use each segment's body, drop its individual CTA (last beat)
        body = seg.beats[:-1] if len(seg.beats) > 1 else seg.beats
        for b in body:
            beats.append(b.model_copy(deep=True))
    beats.append(_b("Which one hit the hardest? Tell me in the comments.", "point", "COMMENT", 0.82))
    beats.append(_b("Follow — your mind will thank you for it.", "cheer", "FOLLOW", 0.92))

    tags = ["psychology", "psychology facts", "mindset", "self improvement",
            "human behavior", "mental models", "dark psychology", "motivation"]
    return StickScript(
        title=f"{n} Psychology Facts That Feel Illegal To Know",
        description=(
            f"{n} psychology facts and cognitive biases that change how you see "
            "yourself and everyone around you — explained fast."
        ),
        tags=tags,
        beats=beats,
    )


def _claude_longform(cfg: Config, topic: str, angle: str | None, minutes: int) -> StickScript:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    n_beats = int(minutes * 60 / 2.6)  # ~2.6s of speech per beat
    user = (
        f"Topic: {topic}\n" + (f"Angle: {angle}\n" if angle else "")
        + f"Write the full {minutes}-minute stickman script as structured JSON."
    )
    resp = client.messages.parse(
        model=cfg.anthropic_model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.anthropic_effort},
        system=[{
            "type": "text",
            "text": _LONG_SYSTEM.format(minutes=minutes, n_beats=n_beats,
                                        actions=", ".join(ACTION_VOCAB)),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user}],
        output_format=StickScript,
    )
    script = resp.parsed_output
    for b in script.beats:
        if b.action not in ACTION_VOCAB:
            b.action = "point"
    return script


def generate_longform(
    cfg: Config,
    topic: str | None = None,
    *,
    angle: str | None = None,
    minutes: int = 5,
    source: Source = "auto",
    theme: str = "midnight",
    seed: int | None = None,
) -> StickScript:
    """Long-form (4-6 min) script.

    With an Anthropic key (and ``source`` auto/claude) Claude writes an original
    deep-dive on ``topic``. Otherwise an offline 'N facts' compilation is built
    from the curated library (genuinely good, no API needed).
    """
    if seed is None:
        seed = random.randint(0, 2**31)
    minutes = max(2, min(8, minutes))

    if source in ("auto", "claude") and cfg.anthropic_api_key:
        if topic is None:
            topic, angle = random.Random(seed).choice(TOPICS)
        cfg.require_anthropic()
        s = _claude_longform(cfg, topic, angle, minutes)
        s.theme = theme
        return s

    if source == "claude":
        cfg.require_anthropic()

    s = _compilation_script(minutes, seed=seed)
    s.theme = theme
    return s


def generate_stickscript(
    cfg: Config,
    topic: str | None = None,
    *,
    angle: str | None = None,
    source: Source = "auto",
    theme: str = "midnight",
    seed: int | None = None,
) -> StickScript:
    """Produce a StickScript. ``topic=None`` picks one from the bank.

    ``source='auto'`` uses Claude when an Anthropic key is set, otherwise a
    curated script (if the topic matches), otherwise the template generator.
    """
    if topic is None:
        rng = random.Random(seed)
        topic, angle = rng.choice(TOPICS)

    if seed is None:
        seed = int(hashlib.sha1(topic.encode()).hexdigest(), 16) % (2**31)

    key = _slug(topic)
    curated = CURATED_BY_SLUG.get(key)

    def _finish(s: StickScript) -> StickScript:
        s.theme = theme
        return s

    # Explicit overrides first.
    if source == "curated":
        if curated:
            return _finish(curated.model_copy(deep=True))
        return _finish(_template_script(topic, angle or "the hidden pattern in your mind", seed=seed))
    if source == "template":
        return _finish(_template_script(topic, angle or "the hidden pattern in your mind", seed=seed))
    if source == "claude":
        cfg.require_anthropic()
        return _finish(_claude_script(cfg, topic, angle))

    # auto: Claude if available, else curated, else template.
    if cfg.anthropic_api_key:
        return _finish(_claude_script(cfg, topic, angle))
    if curated:
        return _finish(curated.model_copy(deep=True))
    return _finish(_template_script(topic, angle or "the hidden pattern in your mind", seed=seed))
