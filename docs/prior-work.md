---
tags: [beatex, prior-work, reference]
---

# Prior work — `C:\My programs\Beat_Extractor`

The previous attempt at this problem. It works, but is bottlenecked on hand-labeled data. We keep its useful parts and replace its core.

## What it does
Two Python packages:
- **`auto_determining`** — a deterministic librosa pipeline: `load_audio` → `extract_features` (onset strength, RMS, low-energy, novelty, beat/downbeat tracking, sections) → `build_candidates` (multi-source candidate onsets) → `select_events`. Produces a beatmap with no ML.
- **`beat_extractor`** — a human-in-the-loop ML layer on top:
  - `taps.py` — capture human taps (Space/mouse) with per-input **latency calibration**; clean + dedupe.
  - `features.py` — for each `auto_determining` candidate, build a 14-dim feature vector (candidate strength/confidence/score, source priority, onset/RMS/low-energy/novelty at that time, distance to nearest beat/downbeat/section, beat-fit, time-norm, local density).
  - `dataset.py` — label candidates positive/negative by whether they matched a human tap.
  - `ml.py` — train a `HistGradientBoostingClassifier` ("ranker-v1"); versioned runs under `data/models/runs/`, active model pointer in `current_model.json`.
  - `ai_generator.py` — run detector → score candidates with the ranker → `select_events` → `beatmap-v1` JSON. Falls back to the deterministic detector when no model exists.
  - A Streamlit app (`app.py`) drives record → review → approve → train → generate, plus a contribution-bundle system to collect taps from friends.

## Why we're moving on
- **Data-hungry:** the ranker needs many approved tap takes; the user is effectively the only labeler. Collected data so far is tiny (≈1 song's beatmap, a few takes, 3 model runs).
- **Ceiling on quality:** the ranker can only *filter/re-rank candidates the librosa detector already proposed*. If the detector never proposes a vocal/melodic onset, the model can't add it — so it structurally can't reach "hits on any part of the song."

Mapperatorinator removes both limits: pretrained on a huge human corpus, and it proposes hits directly from audio (no DSP candidate bottleneck). See [[mapperatorinator-notes]].

## What we reuse
- **`beatmap-v1` JSON schema + Unity `BeatmapLoaderExample.cs`** — the output / integration contract (see shape below). Keep it.
- **Tap-capture + rating + ranker tooling** — repurposed later as the *personalization* layer on top of the Mapperatorinator prior.
- **`auto_determining` detector** — deterministic fallback.

## `beatmap-v1` JSON shape
```json
{
  "version": "beatmap-v1",
  "source":   { "filename": "...", "sha256": "...", "duration_sec": 96.04 },
  "analysis": { "bpm": 161.5, "meter": "4/4", "confidence": 0.86 },
  "events":   [ { "id": "evt_000001", "time_sec": 1.16, "type": "hit",
                  "strength": 0.54, "confidence": 0.78, "source": "downbeat",
                  "edited": false } ],
  "sections": [ { "time_sec": 0.0, "type": "..." } ]
}
```
The Unity loader deserializes exactly these fields with `JsonUtility.FromJson<BeatmapData>`. The new extractor must emit the same shape so existing consumers keep working.

## Note
`Beat_Extractor` also contains a 323 MB `Beat_Extractor.zip` (a self-backup) and a `.venv` (Python 3.14) — ignore both.
