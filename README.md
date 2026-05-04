# yt-automation

Schlanke Python-CLI-Pipeline für YouTube-/Shorts-Content:

```
Topic → Claude (Skript) → ElevenLabs (Voiceover) → [Music + Footage]
      → Whisper (Word-Captions) → FFmpeg → .mp4
```

## Features

- **Skript** via Claude Opus 4.7 mit Adaptive Thinking + Prompt Caching, strukturiert (`messages.parse()`).
- **Voiceover** via ElevenLabs Multilingual.
- **Background-Music** mit Sidechain-Ducking — Musik dimmt automatisch wenn die Stimme spricht.
- **Word-Level Captions** im TikTok/Shorts-Stil über `faster-whisper` → ASS-Subtitles, frame-genau getimt.
- **Format**: `landscape` (1920×1080) oder `shorts` (1080×1920).
- **Footage-Backgrounds**: einzelne Clips loopen oder Verzeichnis konkatenieren, automatisch gecroppt aufs Zielformat.
- **Footage-Tooling**: `yt-dlp`-Download + FFmpeg-Clipping als CLI-Subcommands.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # API-Keys eintragen
```

`ffmpeg` und `ffprobe` müssen im PATH sein (`brew install ffmpeg` / `apt install ffmpeg`).

Beim ersten `--word-captions` lädt `faster-whisper` das gewählte Modell (`WHISPER_MODEL`, default `base`).

## Nutzung

### Komplette Pipeline

```bash
# Default: Landscape, statische Title-Card, grobe Section-Untertitel
yt-automation run "Wie Kaffee deinen Schlaf zerstört"

# Shorts (9:16) mit Footage-Background, Word-Captions, Auto-Music
yt-automation run "Top 5 Anime Power-Ups" \
  --format shorts \
  --background ./assets/footage/montage.mp4 \
  --word-captions

# Mit Verzeichnis voller Clips (werden konkateniert + auf Voice-Länge geloopt)
yt-automation run "Topic" --background ./assets/footage/ --word-captions
```

### Einzelne Stufen

```bash
yt-automation script "Topic"             # nur Skript -> out/script.json
yt-automation tts out/script.json        # Skript -> out/voiceover.mp3
yt-automation video out/script.json      # Skript+Audio -> out/final.mp4
yt-automation voices                     # ElevenLabs voice_ids auflisten
```

### Footage-Management

```bash
yt-automation footage download "https://www.youtube.com/watch?v=..."
yt-automation footage list
yt-automation footage clip ./assets/footage/abc123.mp4 \
  --start 00:01:23 --end 00:01:45 --label fight-scene
```

### Music

Leg `.mp3`/`.wav`-Files in `assets/music/`. Die Pipeline pickt automatisch eine zufällige Spur, dimmt sie via Sidechain-Compression unter dem Voiceover.

## Struktur

```
src/yt_automation/
├── cli.py         # Typer-Entry-Point + footage subcommands
├── config.py      # .env-Loader + Pfade
├── script.py      # Claude → strukturiertes VideoScript
├── tts.py         # ElevenLabs Voice-Synthese
├── audio_mix.py   # Voice + Musik mit Ducking
├── captions.py    # faster-whisper → ASS Word-Captions
├── footage.py     # yt-dlp Download + FFmpeg Clip + Background-Prep
├── video.py       # Render-Pfade (Title-Card / Footage)
└── pipeline.py    # End-to-End Orchestrator
```

## Hinweis zu Footage von YouTube / Anime / Filmen

`yt-dlp` ist ein generisches Tool, aber **Anime, Filme und Serien sind urheberrechtlich geschützt**. Sie zu rippen verletzt YouTube-ToS, sie in eigenen Uploads weiterzuverwenden verletzt die Rechte der Studios. Content-ID erkennt das in der Regel; Konsequenzen reichen von Demonetarisierung bis Channel-Löschung. Fair Use existiert in den USA, ist in DE/AT/CH deutlich enger gefasst (Zitatrecht, § 51 UrhG — und das ist nichts, was eine reine Montage abdeckt).

Sicher nutzbar:
- Eigenes Material
- Lizenzierte Stock-Footage (Pexels, Pixabay, Storyblocks)
- Creative-Commons-Quellen
- Public-Domain-Werke (alte Filme/Anime, Urheber 70+ Jahre tot bzw. CC0)
- Echte Kommentar-/Kritik-Videos mit substantiellem eigenem Anteil

Du bist verantwortlich für das, was du hochlädst. Diese Pipeline baut **keine** Detection-Evasion ein.
