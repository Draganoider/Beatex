---
tags: [beatex, moc]
---

# Beatex — Home

> **Map of Content. Start here.** This vault is the Beatex project wiki — how we turn any song into the "best possible" beatmap: the hit timings a human would *feel*, across drums, bass, vocals and melody.

## Status (2026-10-12)
**Working tool + desktop app.** The full pipeline runs: `song → Mapperatorinator V32 (timing) → parse → shape → beatmap-v1 JSON`, as a dependency-light `beatex` package + CLI ([[architecture]]). **Beatex Studio** ([[studio]]) is the main UI. Double-click `Beatex.bat` to open it in its own window, or run it in the Claude desktop app's browser pane. It covers generation queue, live shaping with synced clicks, run comparison, game preview, tap-along scoring and export. Env/runbook: [[model-setup]]. **Published** at https://github.com/Draganoider/Beatex (public, MIT). **Next:** tap a few songs in the Studio and use the scores to pick default difficulty/density.

## The map
- [[vision]] — what "best possible beatmap" means, and why naive beat-tracking isn't enough.
- [[mapperatorinator-notes]] — the model we reuse: what to keep (timing), what to discard (positions/diffusion), how to run it.
- [[model-setup]] — verified setup + run commands + first test result (the runbook).
- [[architecture]] — the target pipeline: audio → osuT5 timing tokens → flatten/shape → `beatmap-v1` JSON.
- [[studio]] — Beatex Studio, the desktop UI: launch modes, features, tap scoring, server API.
- [[prior-work]] — the previous `Beat_Extractor` attempt: what we reuse (schema, Unity loader, tap tooling) and why we moved on.
- [[decisions]] — decision log (newest first).
- [[open-questions]] — what still gates the build.

## Reading order (new here?)
[[vision]] → [[mapperatorinator-notes]] → [[model-setup]] → [[architecture]] → [[studio]] → [[open-questions]] → [[decisions]] → [[prior-work]].

## How this wiki works
- This `docs/` folder is an **Obsidian vault** — open it as a vault. Notes link with `[[wikilinks]]`; use Obsidian's graph view and backlinks to navigate.
- `CLAUDE.md` (one level up) is the machine-facing project brief Claude auto-loads on each session; it mirrors this **Status**. Keep the two in sync when direction changes.
