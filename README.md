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
python -m venv .venv && source .venv/bin/activate   # macOS/Linux
pip install -e .
cp .env.example .env

# one finished episode (picks a topic, writes script, voices it, animates it):
yt-automation channel episode "The Spotlight Effect"

# a whole content batch with a publish schedule:
yt-automation channel batch --count 5
```

### Windows (PowerShell)

PowerShell 5.1 has no `&&`, and the `yt-automation` command only exists after a
successful install — so run the steps one per line **inside the repo folder**
(the one containing `pyproject.toml`):

```powershell
cd path\to\Workflow
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope Process -Bypass
pip install -e .
Copy-Item .env.example .env

yt-automation channel episode "The Spotlight Effect"
```

If `yt-automation` is still "not recognized" (Scripts dir not on PATH), use the
module form — it always works once installed:

```powershell
python -m yt_automation.cli channel episode "The Spotlight Effect"
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

**Requirements:** `ffmpeg` + `ffprobe` on `PATH`.
- Windows: `winget install Gyan.FFmpeg` (then open a new terminal)
- macOS: `brew install ffmpeg`  ·  Debian/Ubuntu: `apt-get install ffmpeg`

For the fully-offline voice,
also install `espeak-ng` (`apt-get install espeak-ng` / `brew install
espeak-ng`) and set `TTS_PROVIDER=local`. The default `edge` voice needs
internet but no API key.

---

## Two formats

| | **Shorts (animation)** | **Long-form (montage)** |
|---|---|---|
| command | `channel episode` | `channel longform` |
| length | 20-60 s | 4-6 min |
| visuals | procedurally **animated** stickman | 150+ **still shots**, hard-cut to the VO |
| best for | TikTok / Reels / Shorts | YouTube long-form, building a brand |

The long-form montage is exactly "no animation, just images stitched together":
each spoken sentence is split into several **still shots** of the same recurring
character in different poses and camera framings (full / close-up / left / right
/ hero), hard-cut on the beat, over the voiceover with ducked music and
word-by-word captions.

```bash
# a 5-minute montage video (offline 'N facts' compilation if no Claude key):
yt-automation channel longform --minutes 5 --character halo

# a single-topic deep dive (needs ANTHROPIC_API_KEY for the long script):
yt-automation channel longform "The psychology of self-sabotage" --minutes 6
```

`channel longform` options: `--minutes`, `--preset`, `--character`,
`--source auto|claude|compilation`, `--shot-len 1.8` (avg seconds per cut —
lower is faster-paced), `--theme`, `--fps`.

Every polish layer is dial-able (all on by default):

```bash
# minimal/raw look:
yt-automation channel longform --no-grain --no-progress --no-watermark
# keep cards & captions but no signature poses:
yt-automation channel longform --no-signature
```

`--intro/--no-intro`, `--outro/--no-outro`, `--progress/--no-progress`,
`--grain/--no-grain`, `--watermark/--no-watermark`, `--captions/--no-captions`,
`--signature/--no-signature`. (`channel episode` takes `--grain` / `--watermark`
/ `--character` too.)

## The channel commands

```bash
yt-automation channel episode [TOPIC]      # one animated short
yt-automation channel longform [TOPIC]     # 4-6 min montage (still-image cut)
yt-automation channel batch --count N      # N shorts + a publish schedule
yt-automation channel topics               # the built-in psychology topic bank
yt-automation channel presets              # channel presets
yt-automation stickman characters          # brand mascot presets
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

## Your brand character (the recognisable bit)

A personal brand needs one instantly-recognisable mascot. Every frame draws the
**same character** with a signature trademark — pick one and keep it forever.

```bash
yt-automation stickman characters
```

| preset | trademark |
|---|---|
| `halo` | glowing **antenna** (default) |
| `iko` | magenta **headband + shades** |
| `boss` | gold **crown + shades** |
| `sage` | **glasses** |
| `rookie` | **cap** |
| `cyber` | **visor** |

Set it per video with `--character`, or as the channel default in
`channel.ChannelConfig.character`. Trademarks combine headwear
(`headband/cap/beanie/crown/horns/antenna`), eyewear
(`shades/glasses/visor`) and props (`bowtie/scarf`) — define your own in
`stickman/character.py` for a unique mascot.

**Signature poses.** Punchy/emphasis beats drop in distinctive brand poses
(`mind_blown`, `finger_guns`, `salute`, `mic_drop`, `lean`, `arms_crossed`) for
recognisable flavour. Disable with `--no-signature`.

---

## Production polish (built in)

Every video gets a layer of finish automatically:

1. **Branded intro card** — channel name + tagline + hero character (over a clean lead-in).
2. **Branded outro card** — big `FOLLOW` + handle + character cheering.
3. **Karaoke captions** — the spoken word is highlighted in your brand colour and tracks the voice.
4. **Brand watermark** — your `@handle` on every frame (recognisability + anti-repost).
5. **Stepped progress bar** — advances on each cut to pull viewers to the end.
6. **Background variety** — neon grid / radial rays / dot field rotate so no two cuts look alike.
7. **Ground shadow** — a soft contact shadow grounds the character.
8. **Keyword styling** — chromatic punch + accent underline, alternating colours.
9. **Film grain + scanlines** — subtle cinematic texture.
10. **Audio mastering** — loudness-normalised, faded in/out, music ducked under the voice.

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
│   ├── character.py    # brand mascot: trademark accessories
│   ├── render.py       # Pillow drawing, themes, effects
│   ├── scene.py        # animation: storyboard -> frames -> mp4 (shorts)
│   └── montage.py      # long-form: still shots -> hard-cut video
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
