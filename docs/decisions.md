---
tags: [beatex, decisions, log]
---

# Decision log

Newest first. Each entry: what was decided, why, and what it rules out.

## 2026-06-24 — Published to GitHub (public, MIT)
**Outcome:** Live at https://github.com/Draganoider/Beatex (public, MIT), pushed via the gh CLI; remote `origin`, branch `main`. Initial commit + a fix for a Hydra crash on apostrophes in audio filenames (double-quote the override path values; Windows filenames can't contain `"`). `external/`, `data/`, and the venvs are gitignored, so no model weights and **none of the user's audio** are published. README badges + an Acknowledgements section credit Mapperatorinator (the upstream timing model) and mark Beatex as independent / not affiliated.
**Convention:** commit messages follow the user's style — past-tense subject, no body, no trailers.

## 2026-06-23 — Beatex tool + UI built (package, CLI, Streamlit)
**Outcome:** Implemented the actual extractor: a dependency-light `beatex` package (`schema`/`osu_parse`/`shape`/`runner`/`pipeline`/`cli`) that shells out to the isolated model venv and emits Unity-compatible `beatmap-v1` JSON; plus a Streamlit app (generate-once / shape-instantly) with an embedded wavesurfer.js waveform, Web-Audio click playback synced to the song, a density chart, and JSON export. Core validated on the existing `.osu`; full CLI run validated end-to-end (Rammstein – Sonne → 1093 events, 4.0 hits/s). Publish scaffolding (README, MIT LICENSE, .gitignore) added.
**Why this shape:** core stays stdlib-only and calls the model via subprocess, so the heavy 3.10/torch env never contaminates the app; the slow model run is separated from instant shaping so UI tweaks are real-time. App deps live in their own `.venv` (3.12).
**Rules out:** importing the model in-process; a single mixed env.

## 2026-06-23 — Model env built and V32 timing inference validated on the RTX 5080
**Outcome:** The Mapperatorinator env is set up and a first end-to-end run works. Clone in `external/Mapperatorinator/` with an isolated Python 3.10 venv; `torch 2.12.1+cu130` runs Blackwell `sm_120`. V32's default `generate_positions: false` means we get hit-object timing without diffusion — no code fork needed; we read times from the output `.osu`. First run (Rammstein – Sonne, difficulty=4) produced 710 hits at 2.6 hits/s covering 96.6% of the song, density tracking song structure. Full runbook: [[model-setup]].
**Why it matters:** Validates the core bet — the pretrained osu! timing model places musically-varying hits across the whole song on our hardware. Remaining unknown is the *audible* "feels right" judgement (click-track listen).
**Rules out:** needing a custom Python 3.10 / CUDA toolkit install, a flash-attention build, or hacking the token stream — all avoided.

## 2026-06-23 — The `docs/` wiki is an Obsidian vault
**Decision:** Treat `docs/` as an Obsidian vault. Cross-link notes with `[[wikilinks]]`; [[Home]] is the Map-of-Content hub and entry point. New notes get wikilinked and added to [[Home]].
**Why:** The user reads and edits the wiki in Obsidian, where backticked filenames don't render as links — wikilinks give working links, backlinks, and a navigable graph view.
**Rules out:** nothing structural; this is a docs/authoring convention only.

## 2026-06-18 — Beatex is a fresh, self-contained project
**Decision:** Build Beatex as a new, **self-contained** project. **Copy** the small `beatmap-v1` schema/models into Beatex rather than importing from `Beat_Extractor` — no cross-repo Python dependency. The heavy Mapperatorinator model env stays isolated here too.
**Why:** Cleanest separation; avoids two-venv / path-hack coupling between repos; keeps the model's Python 3.10 + CUDA env from contaminating anything else. `Beat_Extractor` remains a reference and a source to copy small pieces from (the schema now, the personalization tooling later).
**Rules out:** importing `Beat_Extractor` as a live dependency; extending it in place.

## 2026-06-18 — Use Mapperatorinator's timing model as the human-feel prior
**Decision:** Build Beatex around the pretrained **osuT5 transformer from Mapperatorinator** as the song→hit-timing engine. Discard all osu-specific output (positions, slider shapes, hitsounds, combos) and the `osu_diffusion` stage.
**Why:** It is pretrained on the entire human-authored ranked osu! corpus, where mappers map to vocals/melody/drums/everything — exactly the "what a human feels" signal we want. It removes the two blockers of the prior `Beat_Extractor` approach (needing the user to hand-label data, and a DSP detector that can't propose non-percussive hits). MIT licensed, weights on HF, and the user's RTX 5080 runs it easily.
**Rules out (for now):** training our own timing model from scratch; relying on the librosa-only detector as the primary engine (it becomes a fallback).
**Status:** adopted; build not started. Pending the open questions in [[open-questions]].

## 2026-06-18 — Keep the `beatmap-v1` JSON contract
**Decision:** The new pipeline emits the existing `beatmap-v1` JSON shape from `Beat_Extractor`.
**Why:** A working Unity loader and a defined schema already exist; preserving the contract means existing/future consumers keep working and the model swap is invisible downstream.
