"""Stickman Studio — automated long-form YouTube video pipeline.

Stages: script (Claude) -> voiceover (ElevenLabs) -> timeline -> render
(procedural stickman frames piped to ffmpeg) -> subtitles -> thumbnail ->
metadata -> optional YouTube upload.
"""

__version__ = "1.0.0"
