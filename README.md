# yt-automation

Schlanke Python-CLI-Pipeline für YouTube-/Shorts-Content mit eigenem **Stick-Man Brand-Charakter** (faceless). **Default ist komplett kostenlos.**

```
Skript-Datei (du) → edge-tts (Stimme) → Whisper (Captions)
                  → FFmpeg + Stick-Man/Footage + Musik → .mp4
```

## Workflows

### Stick-Man Brand-Workflow (empfohlen für faceless Channel)

Dein Charakter wird **einmal** in `assets/character.json` definiert (Farben, Accessoire, Name) und sieht danach in jedem Video und Bild identisch aus — das ist deine Brand. Kein Footage nötig, kein Copyright-Risiko.

```bash
# 1. Charakter anlegen (einmalig) -- rendert auch eine Posen-Vorschau
yt-automation stickman init --name "Stixx" --accent-color "#FF7A59" --accessory cap

# 2. Video rendern: animierter Charakter als Hintergrund
yt-automation from-text mein_skript.txt --format shorts --stickman

# 3. Passendes Thumbnail im selben Look
yt-automation stickman thumbnail "Warum dein Gehirn dich anlügt" --pose point
```

Im Video läuft der Charakter rein und gestikuliert dann im Loop (idle, wave, point, think, celebrate, …) mit subtiler Dauerbewegung, auf Brand-Hintergrund mit Spot, Partikeln und Kanal-Tag.

### Kostenloser Workflow mit Footage

Du schreibst dein Skript selbst — z. B. mit Gemini, ChatGPT oder von Hand — und legst es als `.txt` ab. Der Rest läuft automatisch:

```bash
yt-automation from-text mein_skript.txt --format shorts \
  --background ./assets/footage --word-captions
```

Was passiert: Skript einlesen → Microsoft-Edge-Stimme synthetisiert das Voiceover (gratis) → Hintergrundmusik aus `assets/music/` wird darunter gemischt mit Auto-Ducking → Whisper hört das Voiceover ab und erzeugt frame-genaue Word-by-Word Captions → FFmpeg loopt deine Footage auf die Voiceover-Länge, croppt aufs 9:16 Format und brennt die Captions drauf.

### Bezahl-Workflow (optional)

Mit Anthropic-API-Key wird das Skript komplett von Claude geschrieben:

```bash
yt-automation run "Topic" --format shorts --background ./assets/footage --word-captions
```

Mit ElevenLabs (`TTS_PROVIDER=elevenlabs` in `.env`) kommt eine natürlichere Stimme — kostet ab 10.000 Zeichen/Monat.

## Skript-Datei-Format

Plain Text. Absätze durch Leerzeilen getrennt. Erster Absatz = Hook, letzter = Call-to-Action, dazwischen = Sections. Optional Header oben:

```
# Mein Titel
description: Optionale Beschreibung
tags: tag1, tag2

Erster Absatz wird zum Hook.

Mittlerer Absatz wird zur Section.

Letzter Absatz wird zum Call-to-Action.
```

`skript_beispiel.txt` im Repo zeigt's konkret.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -e .
cp .env.example .env              # ggf. anpassen
```

`ffmpeg` und `ffprobe` müssen im PATH sein.

## Konfiguration (`.env`)

| Variable | Default | Wozu |
|---|---|---|
| `TTS_PROVIDER` | `edge` | `edge` (gratis) oder `elevenlabs` (bezahlt) |
| `EDGE_VOICE` | `de-DE-KatjaNeural` | Microsoft-Stimme. Liste via `yt-automation voices --language de` |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `OUTPUT_DIR` | `./out` | Wohin Skript/Audio/Video gespeichert werden |
| `MUSIC_DIR` | `./assets/music` | Hintergrundmusik (Auto-Pick) |
| `FOOTAGE_DIR` | `./assets/footage` | Footage-Pool |
| `CHARACTER_FILE` | `./assets/character.json` | Stick-Man-Charakter-Definition |
| `ANTHROPIC_API_KEY` | – | Nur für `run`/`script` (Claude) |
| `ELEVENLABS_API_KEY` | – | Nur wenn `TTS_PROVIDER=elevenlabs` |

## Befehle

```bash
# Stimmen anschauen
yt-automation voices --language de

# Stick-Man Brand-Charakter
yt-automation stickman init --name "Stixx" --accessory cap   # einmalig
yt-automation stickman sheet                                  # alle Posen als Übersicht
yt-automation stickman pose wave --transparent                # PNG, z.B. für Canva/Profilbild
yt-automation stickman thumbnail "Mein Titel" --pose point    # Thumbnail 1280x720
yt-automation stickman video --duration 15                    # Hintergrund-Clip zum Testen

# Footage holen
yt-automation footage download "https://www.youtube.com/watch?v=..."
yt-automation footage clip ./assets/footage/abc.mp4 --start 0:30 --end 0:45 --label scene1
yt-automation footage list

# Komplettes Video aus Text-Datei (Stick-Man als Background)
yt-automation from-text skript.txt --format shorts --stickman

# ... oder mit Footage als Background
yt-automation from-text skript.txt --format shorts \
  --background ./assets/footage --word-captions

# Bezahl-Variante mit Claude
yt-automation run "Topic" --format shorts --stickman --word-captions
```

## Struktur

```
src/yt_automation/
├── cli.py         # Typer-CLI
├── config.py      # .env-Loader, Provider-Switches
├── script.py      # Plain-Text-Parser + Claude-Generator
├── tts.py         # edge-tts | ElevenLabs (umschaltbar)
├── audio_mix.py   # Voice + Musik mit Sidechain-Ducking
├── captions.py    # faster-whisper → ASS Word-Captions
├── footage.py     # yt-dlp + FFmpeg Clip + Background-Prep
├── stickman.py    # Brand-Charakter: Posen, Thumbnails, animierte Backgrounds
├── fonts.py       # Font-Lookup für Pillow
├── video.py       # Render-Pfade (Title-Card / Footage)
└── pipeline.py    # End-to-End-Orchestrator
```

## Hinweis zu Footage von YouTube

`yt-dlp` ist generisches Tooling, aber Anime/Filme/Serien sind urheberrechtlich geschützt. Sie zu rippen verletzt YouTube-ToS, sie in eigenen Uploads zu nutzen verletzt die Rechte der Studios. Content-ID erkennt das in der Regel; Konsequenzen reichen von Demonetarisierung bis Channel-Löschung. Fair Use existiert in den USA, in DE/AT/CH ist § 51 UrhG (Zitatrecht) deutlich enger gefasst und deckt reine Montagen nicht ab.

Sicher nutzbar: eigenes Material, Stock-Footage (Pexels/Pixabay), CC-Quellen, Public Domain, echte Kommentar-/Kritik-Videos mit substantiellem eigenem Anteil. Du bist verantwortlich für das, was du veröffentlichst. Die Pipeline enthält **keine** Detection-Evasion.
