"""Content tests: topic bank, curated lookup, template generator, captions."""

from __future__ import annotations

import os

from yt_automation import captions
from yt_automation.config import Config
from yt_automation.content.psychology import (
    ACTION_VOCAB,
    CURATED,
    CURATED_BY_SLUG,
    TOPICS,
    generate_stickscript,
    list_topics,
)


def _cfg() -> Config:
    os.environ["TTS_PROVIDER"] = "local"      # avoid any provider validation surprises
    os.environ.pop("ANTHROPIC_API_KEY", None)  # force the offline path
    return Config.load()


def test_topic_bank_nonempty():
    assert len(list_topics()) >= 10
    assert all(len(t) == 2 for t in TOPICS)


def test_curated_scripts_are_valid():
    for key, script in CURATED.items():
        assert 5 <= len(script.beats) <= 14, key
        assert script.title and script.tags
        for b in script.beats:
            assert b.action in ACTION_VOCAB, (key, b.action)
            assert 0.0 <= b.resolved_intensity() <= 1.0


def test_curated_lookup_normalises_punctuation():
    cfg = _cfg()
    s = generate_stickscript(cfg, "The 5-Second Rule", source="auto")
    assert "second" in s.title.lower() or "fear" in s.title.lower()
    # matches the curated entry, not the generic template
    assert len(s.beats) == len(CURATED_BY_SLUG["the 5 second rule"].beats)


def test_template_generator_for_unknown_topic():
    cfg = _cfg()
    s = generate_stickscript(cfg, "The Florble Effect", source="template")
    assert s.beats and s.beats[-1].keyword == "FOLLOW"
    assert "the" not in s.tags  # stopwords filtered out
    assert all(b.action in ACTION_VOCAB for b in s.beats)


def test_pick_random_topic_when_none():
    cfg = _cfg()
    s = generate_stickscript(cfg, None, source="auto", seed=3)
    assert s.title and len(s.beats) >= 5


def test_even_words_partitions_window():
    words = captions.even_words("one two three", 10.0, 13.0)
    assert len(words) == 3
    assert abs(words[0].start - 10.0) < 1e-6
    assert abs(words[-1].end - 13.0) < 1e-3
    for a, b in zip(words, words[1:]):
        assert b.start >= a.start
