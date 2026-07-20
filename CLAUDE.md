# CLAUDE.md

Guidance for AI assistants working in this repository.

## Project overview

**yt-automation** (v0.1.0) is a lean Python CLI that turns a script or a topic
into a finished YouTube/Shorts `.mp4`. The pipeline:

```
script (.txt or Claude) → TTS voiceover → + ducked music → Whisper captions
                        → FFmpeg composites footage/title-card → final.mp4
```

There are two workflows:

- **Free (default)** — you write the script yourself as a plain-text file;
  `edge-tts` synthesizes the voiceover and `faster-whisper` makes the captions.
  No API keys required.
- **Paid (opt-in)** — Claude writes the script (`ANTHROPIC_API_KEY`) and/or
  ElevenLabs does the voiceover (`TTS_PROVIDER=elevenlabs`).

Requires **Python ≥3.10**. `ffmpeg` and `ffprobe` must be on `PATH` — they are a
hard runtime dependency and are **not** pip-installed.

The package uses a `src/` layout and is installed as the console script
`yt-automation` (entry point `yt_automation.cli:app`, declared in
`pyproject.toml`).

## Language convention

README, docstrings-for-users, and code comments are written in **German**;
code identifiers are English. Match that: keep user-facing strings/comments in
German where the surrounding code is German, and keep symbol names English.

## Architecture & data flow

Layered and one-directional: **CLI → pipeline → building-block modules**. The
CLI only parses args, loads `Config`, and prints. `pipeline.py` sequences the
work. The leaf modules are independent and do not import one another.

```
cli.py
  └─ pipeline.run_from_text / run_pipeline
        └─ pipeline.render_from_script   ← shared core, both funnel here
              ├─ script.from_text | script.generate_script   → VideoScript
              ├─ tts.synthesize                               → voiceover.mp3
              ├─ audio_mix.mix (sidechain ducking)            → audio_mixed.mp3
              ├─ captions.transcribe + write_ass  (word captions)   → captions.ass
              │  OR video.write_srt_from_script   (section captions)→ subtitles.srt
              ├─ footage.prepare_background        (if --background)  → background.mp4
              └─ video.render_with_footage | render_with_title_card → final.mp4
```

- **Typed artifact + files on disk.** The in-memory artifact passed between
  stages is `VideoScript` (Pydantic, `script.py`). Intermediate outputs are
  concrete files in `cfg.output_dir` (`script.json`, `voiceover.mp3`,
  `audio_mixed.mp3`, `captions.ass`/`subtitles.srt`, `background.mp4`,
  `final.mp4`). `pipeline.PipelineResult` bundles the final paths + script.
- **Two render branch points:** captions (`word_captions` → Whisper/ASS vs.
  character-weighted SRT) and background (`--background` given → footage path
  vs. generated title-card path).

## Module map (`src/yt_automation/`)

| File | Responsibility |
|---|---|
| `cli.py` | Typer CLI, the user-facing entry point. All commands live here. |
| `pipeline.py` | Orchestrator: `run_from_text`, `run_pipeline`, shared `render_from_script`. |
| `config.py` | `Config` frozen dataclass loaded from env/`.env`; validation guards. |
| `script.py` | Pydantic `VideoScript`/`ScriptSection`; Claude generator; plain-text parser. |
| `tts.py` | Provider-switchable text-to-speech (edge-tts / ElevenLabs). |
| `audio_mix.py` | Mix voice + music with FFmpeg sidechain ducking. |
| `captions.py` | faster-whisper word timestamps → ASS subtitle file. |
| `footage.py` | yt-dlp download, FFmpeg clip, background prep (scale/crop/loop). |
| `video.py` | Final MP4 render (title-card or footage path) + SRT writer + title-card image. |

## Commands

Setup:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e .
cp .env.example .env              # then edit if you use paid providers
```

CLI (all verbs are in `cli.py`):

```bash
# Free: plain-text script → video  (--format shorts, --word-captions default on)
yt-automation from-text skript_beispiel.txt --format shorts \
  --background ./assets/footage --word-captions

# Paid: Claude writes the script → video  (--format landscape, captions off by default)
yt-automation run "Topic" --format shorts --word-captions

# Building blocks
yt-automation script "Topic"           # Claude → out/script.json (needs Anthropic key)
yt-automation tts out/script.json      # script.json → voiceover.mp3
yt-automation video out/script.json    # render title-card path only
yt-automation voices --language de     # list voices of the active TTS provider

# Footage (Typer sub-app)
yt-automation footage download "https://www.youtube.com/watch?v=..."
yt-automation footage clip ./assets/footage/abc.mp4 --start 0:30 --end 0:45 --label scene1
yt-automation footage list
```

Key defaults worth knowing: `from-text` → `landscape`? **no** → `shorts`, word
captions **on**. `run` → `landscape`, word captions **off**. Formats:
`landscape` = 1920×1080, `shorts` = 1080×1920 (`video.VideoFormat`).

## Configuration

All settings come from environment variables (loaded from `.env` via
`python-dotenv` at import time in `config.py`). Construct once with
`Config.load()` and thread the resulting `cfg` as the first argument into
functions that need it. `Config.load()` auto-creates `OUTPUT_DIR`, `MUSIC_DIR`,
and `FOOTAGE_DIR`.

| Variable | Default | Used for |
|---|---|---|
| `TTS_PROVIDER` | `edge` | `edge` (free) or `elevenlabs` (paid) |
| `EDGE_VOICE` | `de-DE-KatjaNeural` | edge-tts voice |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `OUTPUT_DIR` | `./out` | intermediate + final artifacts |
| `MUSIC_DIR` | `./assets/music` | background-music pool (auto-picked) |
| `FOOTAGE_DIR` | `./assets/footage` | footage pool |
| `ANTHROPIC_API_KEY` | – | required for `run` / `script` only |
| `ANTHROPIC_MODEL` | `claude-opus-4-7` | model for the Claude script generator |
| `ANTHROPIC_EFFORT` | `high` | effort passed to `output_config` |
| `ELEVENLABS_API_KEY` | – | required only when `TTS_PROVIDER=elevenlabs` |
| `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL_ID` | see `.env.example` | ElevenLabs voice/model |

Which commands need which keys:

- `from-text`, `tts` (with edge), `video`, `voices` (edge), `footage *` — **no keys**.
- `run`, `script` — need `ANTHROPIC_API_KEY`. Enforced by `Config.require_anthropic()`.
- Any TTS with `TTS_PROVIDER=elevenlabs` — needs `ELEVENLABS_API_KEY`. Enforced by
  `Config.require_elevenlabs()`.

Call these `require_*` guards lazily, only on the code path that actually needs
the key (that is the existing pattern).

## Code conventions

- Every module opens with a `"""docstring"""` and (except `config.py`)
  `from __future__ import annotations`.
- **Modern type hints throughout**: PEP 604 (`str | None`, `Path | None`,
  `list[tuple[...]]`), `typing.Literal` for closed sets (`TTSProvider`,
  `Style`), a `str`-backed `Enum` for `VideoFormat`.
- **Keyword-only args** (`*`) for optional/behavioral params, e.g.
  `render_from_script(cfg, script, *, fmt=..., background=..., ...)`,
  `clip(..., *, reencode=True)`.
- Naming: `snake_case` functions/vars, `PascalCase` classes, module-level
  `UPPER_CASE` constants (`SYSTEM_PROMPT`, `BG_COLOR`, `MUSIC_EXTS`),
  leading-underscore private helpers (`_synthesize_edge`, `_srt_time`,
  `_check_ffmpeg`, `_font`).
- **`pathlib.Path` everywhere**, never string paths. Functions that write output
  call `out_path.parent.mkdir(parents=True, exist_ok=True)` first and **return
  the `Path` they wrote**.
- Data models: Pydantic `BaseModel` with `Field(description=...)` for the
  LLM-structured types (`ScriptSection`, `VideoScript` — the descriptions double
  as the structured-output schema); `@dataclass(frozen=True)` for internal value
  types (`Config`, `Word`); plain `@dataclass` for results (`PipelineResult`).
- **Lazy imports** of heavy/optional third-party libs *inside* the functions
  that use them (`edge_tts`, `elevenlabs`, `faster_whisper`) to keep startup
  light and optional deps truly optional.
- **Provider abstraction (strategy):** `tts.synthesize`/`list_voices` dispatch
  on `cfg.tts_provider` to private `_..._edge` / `_..._elevenlabs` impls. Extend
  new providers the same way.
- **External tools are shelled out** via `subprocess.run([...], check=True)`
  with explicit arg-lists; every FFmpeg/ffprobe user first guards with
  `shutil.which(...)` and raises `RuntimeError` if the binary is missing.
- CLI style: `typer` with `Annotated[type, typer.Option/Argument(help=...)]`
  params; Rich `Console`/`Table` for all output; success lines use
  `[green]✓[/green]`.
- Fail fast with `raise RuntimeError`/`ValueError` and human-readable (often
  German) messages.

## Gotchas

- **FFmpeg/ffprobe on PATH** is mandatory and checked at runtime — not a pip
  dependency. FFmpeg filtergraphs are the real engine (sidechain ducking in
  `audio_mix.mix`, scale/crop/loop in `footage.prepare_background`, subtitle
  burn-in in `video`).
- `.env`, `out/`, `assets/footage/`, `assets/music/`, and media files
  (`*.mp4/mp3/wav/srt/ass`) are **gitignored** — those dirs are user-populated
  and created at runtime; don't expect them checked in.
- `script.py` uses the newer Anthropic structured-output surface:
  `client.messages.parse(..., output_format=VideoScript,
  thinking={"type": "adaptive"}, output_config={"effort": ...})` (requires
  `anthropic>=0.92.0`). Preserve that call shape when editing script generation;
  the `VideoScript` field descriptions ARE the schema the model fills in.
- Whisper runs `device="cpu", compute_type="int8"` (hardcoded in `captions.py`)
  for portability; the first run downloads the model.
- Copyright: `footage.py` downloads from YouTube via yt-dlp. Reusing
  copyrighted footage infringes rights and violates YouTube ToS — the pipeline
  contains no detection evasion and is intended for licensed/CC/public-domain
  material only. Keep it that way.

## Testing & verification

There is **no test suite, no linter, and no CI** in this repo (no `tests/`, no
`pytest`/`ruff`/`black` config, no `.github/`). There is no command to run after
a change to prove correctness automatically.

Practical checks after editing:

1. Import check — catches syntax/import errors without needing keys or ffmpeg
   (requires `pip install -e .` first so the deps are present):
   ```bash
   python -c "import yt_automation.cli"
   ```
2. End-to-end smoke — needs `ffmpeg` on PATH, uses the free path (no keys):
   ```bash
   yt-automation from-text skript_beispiel.txt --format shorts
   ```
   then inspect `out/final.mp4`.

If you add tests, create a `tests/` directory and add `pytest` as a dev
dependency — none of that scaffolding exists yet.

## Git workflow

Develop on the designated feature branch, commit with clear messages, and push
with `git push -u origin <branch-name>`. Do not push to another branch without
explicit permission, and do not open a pull request unless asked.
