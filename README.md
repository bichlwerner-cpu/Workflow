# yt-automation — automated stickman psychology channel

Generate fast-paced, intense, **fully animated** psychology shorts end-to-end —
topic in, finished vertical video + thumbnail + upload-ready metadata out. The
stickman is drawn and animated procedurally in Python (no external animation
tools), the voice and captions are generated automatically, and the whole thing
runs **free and offline** by default.

```
topic ─▶ psychology script (curated / Claude)
      ─▶ TTS voiceover  +  word timings      (edge-tts | espeak | ElevenLabs)
      ─▶ procedural stickman animation         (dark, neon, kinetic)
      ─▶ word-by-word captions  +  music bed
      ─▶ final .mp4  +  thumbnail.jpg  +  metadata.json   ─▶ (optional) YouTube
```

Each spoken sentence becomes one **beat**: a hard cut, a zoom-punch, a screen
flash, an on-screen keyword, and a matching stickman action (point, panic,
think, idea, punch, power, fall, jump …). That's what makes it read as
*fast-paced and intense* rather than a slideshow.

---

## Quickstart (free, ~zero setup)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env

# one finished episode (picks a topic, writes script, voices it, animates it):
yt-automation channel episode "The Spotlight Effect"

# a whole content batch with a publish schedule:
yt-automation channel batch --count 5
```

Output lands in `out/episodes/<slug>/`:

```
out/episodes/nobody-is-watching-you/
├── video.mp4        # the finished vertical short
├── thumbnail.jpg    # 1280×720 thumbnail
├── metadata.json    # title, description, tags, hashtags, schedule, privacy
├── script.json      # the beat-by-beat script
└── work/            # intermediate voiceover, captions, animation bg
```

**Requirements:** `ffmpeg` + `ffprobe` on `PATH`. For the fully-offline voice,
also install `espeak-ng` (`apt-get install espeak-ng` / `brew install
espeak-ng`) and set `TTS_PROVIDER=local`. The default `edge` voice needs
internet but no API key.

---

## The channel commands

```bash
yt-automation channel episode [TOPIC]      # produce one episode
yt-automation channel batch --count N      # produce N episodes + schedule
yt-automation channel topics               # the built-in psychology topic bank
yt-automation channel presets              # available channel presets
yt-automation channel upload <dir>         # upload an episode (or --dry-run)
```

`channel episode` options: `--preset`, `--source auto|curated|template|claude`,
`--theme`, `--fps`, `--supersample 2` (smoother lines, slower).

### Presets

| preset | name | lang | theme | voice |
|---|---|---|---|---|
| `psychology_en` | Mind Mechanics | en | midnight | en-US-Andrew… |
| `psychology_de` | Kopfsache | de | void | de-DE-Killian… |
| `dark_intense` | The Mind Game | en | bloodmoon | en-US-Brian… |

---

## How the content works

Scripts come from one of three sources (quality order):

1. **Claude** — set `ANTHROPIC_API_KEY` and use `--source claude` (or `auto`).
   Writes a fresh, factual, retention-tuned script and picks the stickman
   action + keyword + intensity for every beat.
2. **Curated** — hand-written scripts for popular topics (Spotlight Effect,
   Negativity Bias, Dopamine Trap, Procrastination, Gaslighting, Zeigarnik,
   Dunning-Kruger, 5-Second Rule). Great quality, **offline**.
3. **Template** — structural generator for any topic. Functional, offline.

`--source auto` uses Claude if a key is present, otherwise a curated script if
the topic matches, otherwise the template.

> **Editorial stance:** this is *educational* psychology — understanding your
> own mind and **recognising** manipulation (e.g. spotting gaslighting), not
> how-to-manipulate content.

---

## The animation engine

A stickman is a small skeleton of bones described by absolute joint angles
(`stickman/skeleton.py`), posed in a library (`stickman/poses.py`), animated by
time-sampled, keyframed actions (`stickman/actions.py`) and drawn with Pillow on
a dark neon background (`stickman/render.py`). `stickman/scene.py` turns a list
of timed beats into frames and encodes them with FFmpeg.

```bash
yt-automation stickman demo            # render a showcase clip, no TTS/network
yt-automation stickman actions         # list actions
```

**Actions:** `idle, walk, run, point, point_up, think, idea, shrug, cheer,
panic, facepalm, punch, power, fall, jump, stomp` (plus aliases like `reveal`,
`anxiety`, `confident`, `defeat`).

**Themes:** `midnight` (cyan), `bloodmoon` (red), `void` (purple),
`synthwave` (magenta/cyan).

---

## Voice & captions

| `TTS_PROVIDER` | network | key | quality | word timings |
|---|---|---|---|---|
| `edge` (default) | yes | no | natural | exact (free, from edge-tts) |
| `local` (espeak-ng) | **no** | no | robotic | even-distributed |
| `elevenlabs` | yes | yes | best | even-distributed |

Captions are rendered word-by-word in the lower third, synced to the beat
windows. With `edge` they use Microsoft's exact word boundaries — no Whisper
needed. (The legacy footage workflow can still use Whisper via the `captions`
extra.)

**Music:** drop royalty-free tracks into `assets/music/`. One is auto-picked per
episode and ducked under the voice with sidechain compression. (Bring your own
licensed/royalty-free music — none is bundled.)

---

## Uploading to YouTube

```bash
pip install -e ".[upload]"
yt-automation channel upload out/episodes/<slug> --dry-run          # preview
yt-automation channel upload out/episodes/<slug> --client-secret client_secret.json
```

1. In Google Cloud Console, enable **YouTube Data API v3** and create an OAuth
   **Desktop** client; download `client_secret.json`.
2. First run opens a browser to authorise; the token is cached for later
   headless runs.

`metadata.json` carries `publishAt` (set by `channel batch` to spread releases),
`privacyStatus`, `categoryId` (27 = Education), tags and hashtags. Scheduled
uploads go up as `private` and flip public at `publishAt`.

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `TTS_PROVIDER` | `edge` | `edge` / `local` / `elevenlabs` |
| `EDGE_VOICE` | `en-US-AndrewMultilingualNeural` | Edge voice |
| `LOCAL_VOICE` / `LOCAL_RATE` | `en-us` / `165` | espeak-ng voice & speed |
| `OUTPUT_DIR` | `./out` | where episodes are written |
| `MUSIC_DIR` | `./assets/music` | background-music pool |
| `ANTHROPIC_API_KEY` | – | enables Claude scripts |
| `ELEVENLABS_API_KEY` | – | only for `TTS_PROVIDER=elevenlabs` |

---

## Project layout

```
src/yt_automation/
├── cli.py              # Typer CLI (channel / stickman / footage / …)
├── config.py           # .env loader, provider switches
├── channel.py          # orchestration: episode + batch + thumbnail + metadata
├── content/
│   └── psychology.py   # topic bank, curated + template + Claude scripts
├── stickman/
│   ├── skeleton.py     # bones + forward kinematics
│   ├── poses.py        # key-pose library
│   ├── actions.py      # keyframed, time-sampled actions
│   ├── render.py       # Pillow drawing, themes, effects
│   └── scene.py        # storyboard -> frames -> mp4
├── tts.py              # edge / local(espeak) / elevenlabs + word timings
├── captions.py         # word-by-word ASS captions
├── audio_mix.py        # voice + music sidechain ducking
├── youtube_upload.py   # optional Data API v3 uploader
├── video.py            # final compose (bg + audio + captions)
├── footage.py          # legacy footage path (yt-dlp + ffmpeg)
└── script.py           # legacy plain-text / Claude VideoScript
```

Run the tests:

```bash
pip install -e ".[dev]" && pytest
```

---

## Legacy text/footage workflow

The original pipeline still works for footage-background or title-card videos:

```bash
yt-automation from-text skript.txt --format shorts --background ./assets/footage
yt-automation run "Topic" --format shorts          # needs ANTHROPIC_API_KEY
```

See `skript_beispiel.txt` for the plain-text script format.

> Downloading copyrighted footage from YouTube violates its ToS and infringes
> rights holders' copyright. Use your own material, stock/CC/public-domain
> sources, or genuine fair-use commentary. You are responsible for what you
> publish. The pipeline contains **no** detection evasion.
