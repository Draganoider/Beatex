---
tags: [beatex, vision]
---

# Vision

**Goal:** extract the *best possible* beatmap from any song — the hit timings a human would naturally feel — and use it to make things react to music well.

- "Best possible" = what a human likes, not just what a beat-tracker detects. Hits land on whatever carries the moment: a vocal accent, a melodic hit, a snare, a bass drop.
- It must generalize to *any* song / genre — not a result hand-tuned per song.
- The output is musical timing (plus relative intensity), independent of any one game.

## Use cases
- Games that react to music (visuals, enemies, platforming, rhythm gameplay).
- Anything that needs the "interesting moments" of a track laid out on a timeline.

## Why naive beat-tracking isn't enough
Classic onset/beat detection finds the metronomic grid and percussive onsets. It misses the *taste* part — which onsets actually matter, and the non-percussive hits (vocals/melody) a human would map. That "taste" is the whole point, and it's why Beatex leans on a model trained on human-authored maps rather than pure DSP. See [[mapperatorinator-notes]].

## What "done" looks like (first milestone)
Given an arbitrary `song.mp3`, produce a `beatmap-v1` JSON whose hits, when previewed as clicks over the audio, *feel right* to the user across a few genres — at a controllable density.
