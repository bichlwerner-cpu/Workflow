# Stickman Studio 🎬

Automatisierte Pipeline für einen **Long-Form YouTube-Kanal mit Stickman-Charakteren**
(Thema: Psychologie). Ein Befehl produziert ein komplettes, upload-fertiges Video:

```
Thema  ──►  Skript (Claude)  ──►  Voiceover (ElevenLabs)  ──►  Video (FFmpeg)
            + Titel/Tags          + Untertitel-Timing          + Untertitel
            + Thumbnail-Plan      + Lippensynchronisation      + Thumbnail
                                                               + Beschreibung
```

## Warum die Charaktere zu 100 % konsistent sind

Der Stickman wird **nicht** von einem Bildgenerator erzeugt, sondern **prozedural
gezeichnet** (parametrisches Skelett-Modell in `pipeline/stickman.py`). Dadurch:

- ist jeder Charakter in jedem Frame und jedem Video pixelgenau identisch,
- kann er animiert werden (16 Posen, 10 Emotionen, echte Lippensynchronisation
  aus den ElevenLabs-Timestamps, Blinzeln, Gesten, Idle-Bewegung),
- kostet das Rendern nichts außer CPU-Zeit.

**Format: Ein Erzähler, stumme Schauspieler.** Eine einzige ElevenLabs-Stimme
spricht das ganze Video (wie bei allen großen Erklär-Kanälen); die
Stickman-Charaktere spielen die Erzählung stumm als Szenen nach — mit
Auftritten, Märschen, Sprüngen, Zusammenbrüchen und Metapher-Kulissen
(Berg = Ziel, Weggabelung = Entscheidung, Mauer = Hindernis, Grube = Tiefpunkt).

**Schnitt-System (Shots).** Jeder Sprech-Beat ist ein eigener *Shot* mit hartem
Cut: **Close-up** (großer Kopf, echte Lippensynchronisation zur Erzählung) für
emotionale/direkte Sätze, **Wide** (ganzer Körper, Bewegung auf der
Metapher-Kulisse) für Aktion, **Insert** (ein großes Icon) für Zahlen/Begriffe.
Standardmäßig steht **genau ein** Charakter im Bild; ein zweiter erscheint nur
für echten Kontrast (du vs. innerer Kritiker). Pro Beat: eigener Zoom
(rein/raus), Snap-„Punch" auf dem Cut, Kamera-Shake bei Schock-Momenten —
das Bild steht nie still. Ziellänge **4–6 Minuten, Short-Tempo**.

**Ton.** Zur Stimme werden automatisch **Sound-Effekte** (Swoosh auf Cuts,
Klick beim Einblenden von Icons, tiefer Impact bei Schock-Beats) und ein
**Hintergrund-Musikbett** gemischt. Beides wird prozedural erzeugt (keine
Extra-Installation, keine Lizenzprobleme); die Musik wird beim ersten Render
automatisch nach `assets/music/bgm.wav` generiert und unter der Stimme
gesidechain-duckt. Eigene `bgm.mp3`/`bgm.wav` einfach dorthin legen zum
Überschreiben, oder `audio.bgm_path: ""` setzen, um Musik abzuschalten.

Die **Erzählstimme** bleibt konsistent durch drei Mechanismen:

1. Eine feste `voice_id` mit eingefrorenen Voice-Settings
   (`narrator:` in `config/characters.yaml`).
2. **Request Stitching**: Jeder Beat übergibt die `previous_request_ids` der
   letzten Generierungen — die Prosodie bleibt über das ganze Video kohärent
   (deshalb `eleven_multilingual_v2`, **nicht** `eleven_v3` — v3 unterstützt
   kein Stitching).
3. `previous_text` / `next_text` Kontext für natürlichen Satzfluss.

## Setup

```bash
# 1. Abhängigkeiten
pip install -r requirements.txt
sudo apt install ffmpeg          # bzw. brew install ffmpeg

# 2. API-Keys
cp .env.example .env             # GEMINI_API_KEY (gratis) + ELEVENLABS_API_KEY eintragen
#    Gemini-Key kostenlos (ohne Kreditkarte): https://aistudio.google.com/apikey

# 3. (empfohlen) Branding
#    - Bold-Font nach assets/fonts/ (siehe assets/fonts/README.md)
#    - Hintergrundmusik nach assets/music/bgm.mp3
#    - eigene/geklonte ElevenLabs-Stimmen in config/characters.yaml eintragen
#      (IDs anzeigen: python -m pipeline list-voices)

# 4. Alles prüfen
python -m pipeline validate
```

## Ein Video produzieren

```bash
python -m pipeline produce --topic "Why your brain sabotages you before success"
```

Ergebnis in `output/<slug>/`:

| Datei | Inhalt |
|---|---|
| `video.mp4` | 1080p30, H.264+AAC, -14 LUFS, Untertitel eingebrannt |
| `thumbnail.png` | 1280×720, hoher Kontrast, Akzentfarbe, Stickman |
| `description.txt` | Beschreibung inkl. Kapitel-Timestamps |
| `metadata.json` | 5 Titel-Varianten (A/B), Tags, Kategorie |
| `subtitles.srt` | für YouTube-CC zusätzlich hochladen |
| `script.json` / `timeline.json` | Skript + berechnetes Timing (Review/Debug) |

Danach prüfen und hochladen:

```bash
python -m pipeline upload --slug <slug>     # YouTube (Standard: privat)
```

Einzelne Stufen lassen sich getrennt ausführen und wiederholen — bereits
generierte Audio-Zeilen werden gecacht (kein doppeltes ElevenLabs-Kontingent):

```bash
python -m pipeline script    --topic "..."   # nur Skript
python -m pipeline voice     --slug <slug>   # nur Voiceover
python -m pipeline render    --slug <slug>   # nur Video
python -m pipeline thumbnail --slug <slug>
python -m pipeline metadata  --slug <slug>
```

## Was die Qualität/Retention treibt

Das Skript erzeugt standardmäßig **Gemini 2.5 Flash** (kostenloser API-Key) im
JSON-Modus mit Validierung + Reparatur-Retry; optional liefert
`llm.provider: claude` (`claude-opus-4-8`, bezahlt) mit nativen structured
outputs die beste Skriptqualität. In beiden Fällen ist jede
Pose/Emotion/Hintergrund garantiert renderbar. Das System-Prompt erzwingt
ein Retention-Playbook: Cold-Open-Hook in den ersten 15 Wörtern, Open Loops am
Kapitelende, Pattern-Interrupts alle 30–45 s, Re-Hooks, konkrete Beispiele statt
Abstraktion, ein CTA. Gleichzeitig gilt: **echte Psychologie, keine erfundenen
Studien, Titel ohne Lügen** — Clickbait, der nicht eingelöst wird, killt den
Kanal langfristig.

Im Video selbst: harte Cuts zwischen Close-up/Wide/Insert mit Snap-Punch und
Swoosh, Lippensynchronisation in Close-ups, große fett-umrandete
Wort-Karaoke-Untertitel (das gesprochene Wort leuchtet in der Akzentfarbe),
Kapitelkarten, schwebende Props mit Klick-Sound, Kamera-Zoom/-Shake bei
Schock-Momenten, Fortschrittsbalken, Musikbett mit Sidechain-Ducking.

## Konfiguration

- `config/settings.yaml` — Auflösung, FPS, Ziellänge, Audio-Gaps, Untertitel,
  Akzentfarbe, Sprache (`language: en` für maximale Reichweite, `de` möglich)
- `config/characters.yaml` — der Cast: Aussehen (Farbe, Accessoire), Persona
  (steuert das Skript) und Stimme (steuert ElevenLabs)

**Charaktere ändern = nur YAML ändern.** Neue Posen/Props brauchen zusätzlich
Rendering-Support in `pipeline/vocab.py` + `pipeline/stickman.py`/`renderer.py`.

## Wöchentliche Automatisierung

`examples/github-actions-weekly.yml` produziert jeden Montag automatisch ein
Video aus der Themen-Backlog (`topics.txt`) und hängt es als Artifact zur
Review an. Anleitung steht im File. Empfehlung: das Video **vor** dem
Veröffentlichen immer kurz prüfen (Upload-Stufe lädt standardmäßig privat hoch).

## Smoke-Test (ohne API-Keys)

```bash
python scripts/smoke_test.py    # rendert Beispiel-Frames + Thumbnail nach output/_smoke/
```

## Kosten pro Video (Größenordnung, ~5 min, Short-Tempo)

| Posten | ca. |
|---|---|
| Skript mit Gemini (Standard, ~8 Calls) | 0 USD (Free Tier) |
| Skript mit Claude (optional, beste Qualität) | 1–2 USD |
| ElevenLabs (~850 Wörter ≈ 5–6 k Zeichen) | Kontingent des Abos |
| SFX + Musikbett | 0 USD (prozedural erzeugt) |
| Rendern | nur CPU-Zeit (~10–30 min je nach Maschine) |

## Troubleshooting

- **`ffmpeg not found`** → installieren, `python -m pipeline validate` erneut.
- **ElevenLabs 4xx** → `voice_id` prüfen (`list-voices`), `output_format` ggf.
  auf `mp3_44100_128` lassen (höhere Formate sind Plan-abhängig).
- **Untertitel-Font falsch** → Font systemweit installieren und
  `subtitles.font_name` setzen (libass nutzt fontconfig).
- **Video zu lang/kurz** → `video.target_minutes` anpassen; die echte Länge
  ergibt sich aus dem gesprochenen Audio.
