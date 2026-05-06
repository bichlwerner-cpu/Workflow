# yt-automation — Handoff

Alles was ein anderer Entwickler oder AI-Agent (Cursor, Codex, Cowork, etc.)
braucht, um an diesem Repo weiterzuarbeiten. Stand: Branch
`claude/learn-yt-automation-RrjYQ`, Commit `7e80b83`.

---

## 1. Was die Pipeline tut

Eine Python-CLI, die aus einem Plain-Text-Skript einen YouTube-Short
produziert und optional direkt hochlädt.

```
.txt-Skript ─► edge-tts ─► Whisper Word-Captions ─► FFmpeg
                ↑                                    │
              (oder Claude generiert Skript)         ▼
                                          Loudnorm + Sidechain-Ducking
                                          + Scene-Pack Fast-Cuts (1080×1920)
                                                     │
                                                     ▼
                                           YouTube Data API v3 Upload
```

**Default ist gratis.** Bezahl-Optionen (Claude für Auto-Skripte,
ElevenLabs für TTS) sind über `.env` einschaltbar.

---

## 2. Repo-Layout

```
yt-automation/
├── pyproject.toml             # Package + entry point `yt-automation`
├── requirements.txt           # gleiche Deps wie pyproject
├── .env.example               # alle Config-Variablen mit Defaults
├── .gitignore                 # ignoriert secrets/, token.json, out/, footage/
├── skript_beispiel.txt        # Beispiel-Skript (Format-Doku)
├── README.md                  # User-Doku
└── src/yt_automation/
    ├── cli.py                 # Typer-CLI, alle Commands
    ├── config.py              # frozen-dataclass Config, .env-Loader
    ├── script.py              # VideoScript (Pydantic), from_text(), Claude-Gen
    ├── tts.py                 # edge-tts | ElevenLabs (TTS_PROVIDER switch)
    ├── audio_mix.py           # mix() = Voice+Music+Ducking+Loudnorm; normalize()
    ├── captions.py            # faster-whisper → ASS, Color-Rotation
    ├── footage.py             # yt-dlp Download, Clip, Background, Fast-Cuts
    ├── scene_pack.py          # PySceneDetect → Scene-Packs mit manifest.json
    ├── video.py               # Render-Pfade (Title-Card, Footage)
    ├── publish.py             # YT Data API v3 OAuth + Resumable-Upload
    └── pipeline.py            # End-to-End-Orchestrator
```

---

## 3. Dependencies

System: **Python ≥3.10**, **ffmpeg + ffprobe im PATH**.

Python-Deps (`pyproject.toml`):
```
anthropic>=0.92.0          # nur fuer Claude-Auto-Skript
elevenlabs>=1.5.0          # nur fuer TTS_PROVIDER=elevenlabs
edge-tts>=6.1.12           # gratis-TTS (default)
python-dotenv>=1.0.0
pydantic>=2.6.0
typer>=0.12.0
rich>=13.7.0
Pillow>=10.0.0             # Title-Card-Render
faster-whisper>=1.0.3      # Word-Captions
yt-dlp>=2024.10.7          # YT-Footage-Download
scenedetect[opencv]>=0.6.4 # Scene-Pack-Extraktion
google-api-python-client>=2.140.0   # YT-Upload
google-auth-oauthlib>=1.2.1
google-auth-httplib2>=0.2.0
```

Install:
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
```

---

## 4. Environment-Variablen (`.env`)

| Variable | Default | Wozu |
|---|---|---|
| `TTS_PROVIDER` | `edge` | `edge` (gratis) oder `elevenlabs` |
| `EDGE_VOICE` | `de-DE-KatjaNeural` | Liste: `yt-automation voices --language de` |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `OUTPUT_DIR` | `./out` | Skript/Audio/Video Output |
| `MUSIC_DIR` | `./assets/music` | Auto-Pick fuer Background-Musik |
| `FOOTAGE_DIR` | `./assets/footage` | Footage-Pool und Scene-Packs |
| `ANTHROPIC_API_KEY` | – | nur fuer `run`/`script` |
| `ANTHROPIC_MODEL` | `claude-opus-4-7` | – |
| `ANTHROPIC_EFFORT` | `high` | `low`/`medium`/`high` |
| `ELEVENLABS_API_KEY` | – | nur wenn TTS_PROVIDER=elevenlabs |
| `ELEVENLABS_VOICE_ID` | (Rachel) | – |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | – |
| `SCENE_THRESHOLD` | `27` | PySceneDetect-Schwelle, niedriger=mehr Cuts |
| `SCENE_MIN_LEN` | `2.0` | Min. Clip-Laenge (Sek.) |
| `SCENE_MAX_LEN` | `6.0` | Max. Clip-Laenge (Sek.) |
| `YT_CLIENT_SECRET` | `./secrets/client_secret.json` | OAuth-Datei aus Google Cloud |
| `YT_TOKEN_CACHE` | `./secrets/token.json` | wird automatisch befuellt |
| `YT_DEFAULT_PRIVACY` | `private` | `private`/`unlisted`/`public` |
| `YT_DEFAULT_CATEGORY` | `24` | 24=Entertainment, 22=People&Blogs, 23=Comedy, 27=Education |
| `YT_DEFAULT_LANGUAGE` | `de` | BCP-47 |

Pipeline läuft **ohne** `ANTHROPIC_API_KEY`, **ohne** `ELEVENLABS_API_KEY` und
**ohne** `YT_CLIENT_SECRET`. Fehlende Keys → entsprechender Schritt wird
übersprungen oder mit klarer Fehlermeldung blockiert.

---

## 5. Google-Cloud-Setup (einmalig, ~15 min)

Nur nötig wenn Auto-Upload genutzt werden soll. Muss der **Channel-Owner**
selbst machen, da OAuth-Identität gebraucht wird.

1. **Projekt anlegen:** console.cloud.google.com → "New Project"
2. **API aktivieren:** APIs & Services → Library → "YouTube Data API v3" → Enable
3. **OAuth-Consent-Screen:** APIs & Services → OAuth consent screen
   - User-Type: **External**
   - App-Name beliebig, Support-Mail = eigene
   - Scopes: nichts manuell hinzufügen (Library-Default reicht)
   - Test-Users: eigene Google-Mail eintragen
4. **OAuth-Client erstellen:** APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - JSON herunterladen → speichern als `./secrets/client_secret.json`
5. **Channel verifizieren:** youtube.com/verify (SMS) — sonst kein Upload >15min, kein public

Erster Run mit `--publish` öffnet Browser einmal für Consent. Token wird in
`./secrets/token.json` gecached und automatisch refreshed.

**Quota:** 1 Upload = 1.600 Units, Default 10.000/Tag → max **6 Uploads/Tag**.

---

## 6. CLI-Reference

```bash
# Stimmen anschauen
yt-automation voices --language de

# Footage holen
yt-automation footage download <youtube-url> --max-height 1080
yt-automation footage clip <video> --start 0:30 --end 0:45 --label scene1
yt-automation footage list

# Scene-Pack extrahieren (motion-gefiltert)
yt-automation footage extract <video> --min-len 2 --max-len 6 --keep-top 30
yt-automation footage packs

# Render aus Plain-Text (gratis)
yt-automation from-text skript.txt --format shorts \
  --background ./assets/footage/<pack> --word-captions

# Render + direkt hochladen
yt-automation from-text skript.txt --background ./assets/footage/<pack> \
  --publish --privacy private

# Render via Claude (braucht ANTHROPIC_API_KEY)
yt-automation run "Topic" --format shorts --word-captions --publish

# Manuelles Upload eines bereits gerenderten Files
yt-automation publish ./out/final.mp4 --script-path ./out/script.json

# Nur Skript (Claude)
yt-automation script "Topic" --duration 60 --style listicle

# Nur TTS
yt-automation tts ./out/script.json

# Nur Video (ohne Footage, mit Title-Card)
yt-automation video ./out/script.json --audio ./out/voiceover.mp3
```

---

## 7. Skript-Datei-Format (`from-text`)

Plain Text. Absätze durch Leerzeilen.

```
# Optionaler Titel
description: Optionale Beschreibung
tags: tag1, tag2, tag3

Erster Absatz wird zum Hook (max 12 Worte ideal).

Mittlere Absätze werden zu Sections.

Letzter Absatz wird zum Call-to-Action.
```

Header optional. Bei nur einem Absatz landet alles in einer Section.

---

## 8. Datenfluss (was `run_from_text` intern tut)

1. `script.from_text(path)` → `VideoScript`
2. `tts.synthesize()` → `out/voiceover.mp3`
3. `audio_mix.pick_music()` aus `MUSIC_DIR`, falls vorhanden:
   - `audio_mix.mix()` → ducking + loudnorm `-14 LUFS` → `out/audio_mixed.mp3`
   - sonst: `audio_mix.normalize()` → loudnorm-only
4. `captions.transcribe()` (Whisper) → `captions.write_ass()` mit Color-Rotation
5. `pipeline._resolve_clips(background)`:
   - Datei → `[Path]`
   - Verzeichnis mit `manifest.json` → Scene-Pack laden
   - Verzeichnis ohne Manifest → alle Videos sortiert
6. Background:
   - `fast_cuts=True` und mehrere Clips → `footage.prepare_fast_cuts()` (1.5–2.5 s Slices)
   - sonst → `footage.prepare_background()` (Loop)
7. `video.render_with_footage()` → `out/final.mp4`
8. Falls `--publish`: `publish.upload_from_script()` → URL

---

## 9. Wichtige Defaults und Verhalten

- **Format-Default:** `from-text` = `shorts` (1080×1920), `run` = `landscape` (1920×1080)
- **Word-Captions:** an bei `from-text`, aus bei `run` (kann via Flag ueberschrieben werden)
- **Fast-Cuts:** an, wenn Background ein Verzeichnis mit ≥2 Clips ist
- **Title bekommt automatisch ` #Shorts` angehängt** beim Upload (in `publish._build_metadata`)
- **Whisper läuft CPU/int8** — auf GPU umstellbar in `captions.transcribe()`
- **Captions:** ASS mit 5-farbiger Rotation (weiß/gelb/orange/grün/magenta)
- **Audio:** Loudnorm-Target `I=-14 LUFS, TP=-1.5 dB, LRA=11` (YouTube-Spec)

---

## 10. Bekannte Limitierungen

- **Keine Trend-Erkennung** — Pipeline weiß nicht, was viral geht
- **Kein A/B-Testing** für Titles/Thumbnails
- **Keine Analytics-Loop** (kein Lernen aus Performance)
- **OAuth-Token läuft im "Testing"-Mode alle 7 Tage ab** — entweder App in Production schalten oder neu auth'en
- **Quota 10k/Tag** — für mehr als 6 Uploads/Tag Quota-Increase bei Google beantragen
- **Re-uploaded-Content-Filter:** YT kann Auto-Cuts aus fremden Videos erkennen → Reach-Drosselung
- **Edge-TTS klingt nach TTS** — für authentischeren Sound: ElevenLabs (kostet)
- **Whisper `base` ist gut genug für DE/EN**, bei Mehrsprachigkeit oder Slang `large-v3` nehmen
- **Keine Garantie auf Views** — Reichweite hängt an Niche, Hook, Channel-Authority, Algorithmus

---

## 11. Sicherheit / .gitignore

Niemals committen:
- `.env`
- `secrets/` (enthält `client_secret.json` und `token.json`)
- `out/`, `assets/footage/`, `assets/music/` (Binär-Daten + evtl. Copyright)

`.gitignore` deckt das ab.

---

## 12. Erweiterungs-Ideen (wenn du was bauen willst)

| Was | Wo | Aufwand |
|---|---|---|
| Thumbnail-Auto-Generator | neue `thumbnail.py`, in `publish.py` `thumbnails.set` aufrufen | M |
| Schedule-Upload via `publishAt` | `publish.upload()` Body-Field ergänzen | S |
| A/B-Title (2 Varianten generieren, manuell wählen) | `script.py` `generate_script` Liste statt einzeln | M |
| Trend-Topics aus YT-Trending-API | neue `trends.py`, in `script.py` als Topic-Source | L |
| Music-Match-by-Mood | `audio_mix.pick_music()` mit Tag-Filter, Music-Library taggen | M |
| Multi-Channel-Support | `Config.yt_*` zu Liste, Channel-ID als CLI-Flag | M |
| Analytics-Loop | YouTube Analytics API v2, Scope `yt-analytics.readonly` ergänzen | L |
| Voiceover skip (eigene Datei einbringen) | `--voice-file` Flag in `cli.py`/`pipeline.py`, Skip-TTS-Branch | S |
| Captions skip (eigene .ass) | `--captions-file` analog | S |
| GPU-Whisper | `captions.transcribe()`: `device="cuda", compute_type="float16"` | XS |

---

## 13. Tests / Smoke-Check

Es gibt aktuell **keine Tests**. Vor Änderungen mindestens:

```bash
# AST-Check
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src/yt_automation').glob('*.py')]"

# CLI lädt
yt-automation --help

# End-to-End ohne Upload
yt-automation from-text skript_beispiel.txt --format shorts \
  --background ./assets/footage/<pack>
```

---

## 14. Rechtliches (wichtig)

- yt-dlp + Scene-Packs aus YouTube-Videos verletzen YouTube-ToS und meist
  Urheberrecht. Content-ID erkennt das. Nur eigenes Material, Stock
  (Pexels/Pixabay), CC-Lizenzen, Public Domain oder echtes Fair-Use
  benutzen. Pipeline enthält **keine** Detection-Evasion.
- §51 UrhG (DE/AT) ist enger als US-Fair-Use; reine Compilations sind
  nicht gedeckt.
- Verantwortlich für veröffentlichte Inhalte ist der Channel-Owner.

---

## 15. Branch + Commits

- Aktiver Branch: `claude/learn-yt-automation-RrjYQ`
- Letzter Commit: `7e80b83` (feat: scene-pack extraction, fast-cuts, loudnorm, YouTube upload)
- Vorher: `e5642f2` (free workflow default), `bb3a663` (word captions, ducking, shorts), `5b2d211` (scaffold)

Pull-Request nicht erstellt — Branch ist bereit für Review/PR-Erstellung.
