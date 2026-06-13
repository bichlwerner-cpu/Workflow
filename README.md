# yt-automation

Schlanke Python-CLI-Pipeline für YouTube-/Shorts-Content. **Default ist komplett kostenlos.**

```
Skript-Datei (du) → edge-tts (Stimme) → Whisper (Captions)
                  → FFmpeg + Footage + Musik → .mp4
```

## Workflows

### Kostenloser Workflow (empfohlen)

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

## 2D Brand-Charakter (Mascot)

Für einen faceless Channel mit eigenem Charakter ("yellow dude"-Stil). Der Clou:
der Charakter ist **kein KI-Bild**, sondern parametrisch im Code definiert
(`character.py`). Jede Pose nutzt exakt dieselben Teile, Farben, Proportionen und
Strichstärken – nur Gelenkwinkel/Position ändern sich. Dadurch ist er über
beliebig viele Frames **zu 100 % konsistent**, was ein Editor braucht, um die
Bilder smooth aneinanderzureihen.

```bash
# Was gibt es? (Posen, Ausdrücke, Lip-Sync-Mundformen)
yt-automation mascot list

# Kontaktblatt (ein PNG zum Überblick)
yt-automation mascot sheet --out out/mascot/contact_sheet.png

# Komplette Bilder-Bibliothek für den Editor (transparente PNGs + SVG-Quellen)
yt-automation mascot export --out out/mascot --width 1200
yt-automation mascot export --out out/mascot --full      # ganze Pose×Ausdruck-Matrix

# Einzelne Pose+Ausdruck
yt-automation mascot pose wave happy --out out/mascot/wave.png
```

Export-Struktur:

```
out/mascot/
├── poses/        idle, wave, point_up/right/left, thumbs_up, thinking,
│                 hands_hips, shrug, celebrate, welcome, run, facepalm
├── expressions/  neutral, happy, talk, surprised, sad, angry, thinking,
│                 wink, cool, dead
├── visemes/      rest, mbp, talk_a/e/i/o/u   (Mundformen für Lip-Sync)
└── svg/          editierbare Vektor-Quellen aller Bilder
```

Alle PNGs sind transparent und hochauflösend – direkt im Editor (After Effects,
Premiere, CapCut, DaVinci) auf Hintergründe komponierbar. Die `visemes/` sind die
Mundformen, mit denen sich das Voiceover lippensynchron animieren lässt.

**Re-Branding:** Farbe/Style an einer Stelle ändern – die `PALETTE`-Konstanten oben
in `character.py` (`BODY`, `OUTLINE`, `CHEEK`, …). Alle Posen aktualisieren sich.

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
| `ANTHROPIC_API_KEY` | – | Nur für `run`/`script` (Claude) |
| `ELEVENLABS_API_KEY` | – | Nur wenn `TTS_PROVIDER=elevenlabs` |

## Befehle

```bash
# Stimmen anschauen
yt-automation voices --language de

# Footage holen
yt-automation footage download "https://www.youtube.com/watch?v=..."
yt-automation footage clip ./assets/footage/abc.mp4 --start 0:30 --end 0:45 --label scene1
yt-automation footage list

# Komplettes Video aus Text-Datei
yt-automation from-text skript.txt --format shorts \
  --background ./assets/footage --word-captions

# Bezahl-Variante mit Claude
yt-automation run "Topic" --format shorts --word-captions
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
├── video.py       # Render-Pfade (Title-Card / Footage)
└── pipeline.py    # End-to-End-Orchestrator
```

## Hinweis zu Footage von YouTube

`yt-dlp` ist generisches Tooling, aber Anime/Filme/Serien sind urheberrechtlich geschützt. Sie zu rippen verletzt YouTube-ToS, sie in eigenen Uploads zu nutzen verletzt die Rechte der Studios. Content-ID erkennt das in der Regel; Konsequenzen reichen von Demonetarisierung bis Channel-Löschung. Fair Use existiert in den USA, in DE/AT/CH ist § 51 UrhG (Zitatrecht) deutlich enger gefasst und deckt reine Montagen nicht ab.

Sicher nutzbar: eigenes Material, Stock-Footage (Pexels/Pixabay), CC-Quellen, Public Domain, echte Kommentar-/Kritik-Videos mit substantiellem eigenem Anteil. Du bist verantwortlich für das, was du veröffentlichst. Die Pipeline enthält **keine** Detection-Evasion.
