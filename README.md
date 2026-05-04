# yt-automation

Schlanke Python-CLI-Pipeline für YouTube-Content:

```
Topic --> Claude (Skript)  --> ElevenLabs (Voiceover)  --> FFmpeg (Video) --> .mp4
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # API-Keys eintragen
```

`ffmpeg` muss im PATH sein (`brew install ffmpeg` / `apt install ffmpeg`).

## Nutzung

```bash
# Komplette Pipeline
yt-automation run "Wie Kaffee deinen Schlaf zerstört" --duration 60 --style explainer

# Einzelne Stufen
yt-automation script "Topic"           # nur Skript -> out/script.json
yt-automation tts out/script.json      # Skript -> out/voiceover.mp3
yt-automation video out/script.json    # Skript+Audio -> out/final.mp4

# Voices auflisten
yt-automation voices
```

## Struktur

```
src/yt_automation/
├── cli.py        # Typer-Entry-Point
├── config.py     # .env + Defaults
├── script.py     # Claude Opus 4.7 -> strukturiertes Skript
├── tts.py        # ElevenLabs Audio
├── video.py      # FFmpeg Assembly (Title-Card + Audio + Untertitel)
└── pipeline.py   # Orchestrator
```

## Notes

- **Modell**: `claude-opus-4-7` mit Adaptive Thinking + Prompt Caching auf System-Prompt.
- **Output**: Strukturierte JSON über `messages.parse()` (Pydantic-Schema).
- **Video**: Single-Pass FFmpeg mit gerendertem Title-Frame (Pillow) + Voiceover + auto-generierten SRT-Untertiteln.
- Für aufwändigere Videos (B-Roll, Schnitte) Video-Modul erweitern oder DaVinci/Resolve-Export-Pfad ergänzen.
