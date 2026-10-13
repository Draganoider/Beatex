# Beatex — project guide

Beatex turns **any song into the "best possible" beatmap**: the sequence of hit timings a human would *feel* — across drums, bass, vocals, and melody, not just percussion. The output drives music-reactive games and similar real-time-to-music use cases.

## Status (2026-10-12)
**Working tool + desktop app.** Full pipeline implemented and validated: `song → Mapperatorinator V32 (timing only) → parse → shape → beatmap-v1 JSON`, as the `beatex` package + `beatex` CLI. The main UI is **Beatex Studio** (`app/studio/`): a stdlib HTTP server (`server.py`, JSON API + one-at-a-time GPU job queue) and a no-build HTML/JS front end (`static/`). It opens as its own app window via `Beatex.bat` / `Beatex.exe` (Edge/Chrome `--app`; closing the window stops the server) and in the Claude desktop app's browser pane via `.claude/launch.json` (`beatex-studio`, port 8765). Features: live Web Audio click playback, run-comparison lanes, game preview, tap-along scoring, exports to `data/exports/`. See `docs/studio.md`. The old Streamlit/PyQt UIs (`app/streamlit_app.py`, `app/qt_app.py`) are legacy. Core is stdlib-only and calls the isolated model venv via subprocess (`external/Mapperatorinator`); app deps live in their own `.venv` (3.12). Reused from `Beat_Extractor`: the `beatmap-v1` schema + Unity contract. Runbook: `docs/model-setup.md`; decisions: `docs/decisions.md`. **Published** at https://github.com/Draganoider/Beatex (public, MIT; remote `origin`, branch `main`). **Next:** tap songs in the Studio and use the scores to tune default difficulty/density/feel.

## The core idea
osu! mappers place hit objects on the musically meaningful moments of a song — vocals, melody, drums, everything — which is exactly the "where does a human feel a hit" signal we want, and there is a huge human-authored corpus of it. **Mapperatorinator** (OliBomby, MIT) is a model pretrained on that corpus. We reuse only its **timing** output and discard all osu-specific data (x/y positions, slider shapes, hitsounds, combos). See `docs/mapperatorinator-notes.md`.

## Target pipeline
audio → Mapperatorinator osuT5 transformer (timing only; diffusion skipped) → parse hit-time tokens → flatten + density/strength shaping (difficulty knob) → `beatmap-v1` JSON → game. Optional later: a personalization re-ranker trained on the user's own taps/ratings. See `docs/architecture.md`.

## Reused from prior work (`Beat_Extractor`)
- `beatmap-v1` JSON schema + Unity `BeatmapLoaderExample.cs` → keep as the output / integration format.
- Tap-capture + rating + ranker tooling → future personalization layer.
- `auto_determining` librosa detector → deterministic fallback when the model is unavailable.
See `docs/prior-work.md`.

## Environment
- Machine: RTX 5080 (16 GB), Windows, PowerShell. System Python 3.13 / 3.14 present.
- Mapperatorinator needs its **own Python 3.10 env** + ffmpeg + a Blackwell-compatible PyTorch/CUDA build (cu128+/2.10-class). Keep it isolated from any Beatex application-code env.

## Conventions
- Wiki lives in `docs/` and is an **Obsidian vault** — entry point `docs/Home.md` (Map of Content). Cross-link notes with `[[wikilinks]]`, give each a small `tags:` frontmatter, and list new notes in `Home`. Update `docs/decisions.md` whenever a direction changes; keep this file's **Status** and `docs/Home.md`'s **Status** in sync.
- Do not commit model weights or audio. Generated beatmaps go under a gitignored `data/` dir unless they are test fixtures.
- When you (a future session) learn something durable about the model, the pipeline, or a decision — write it into the right `docs/` page, not just the chat.

## Open questions
See `docs/open-questions.md` — slider flattening policy, target difficulty/density, final consumer engine.
