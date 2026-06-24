---
tags: [beatex, architecture, pipeline]
---

# Architecture (target)

```
        audio file (mp3/wav/ogg)
                 │
                 ▼
  ┌───────────────────────────────────┐
  │ Mapperatorinator osuT5 transformer │  mel-spectrogram → event tokens
  │ (TIMING ONLY — diffusion skipped)  │
  └───────────────────────────────────┘
                 │  decoded event sequence
                 ▼
  ┌───────────────────────────────────┐
  │ Rhythm extractor                   │  parse time tokens; keep hit objects
  │  → [{time_sec, obj_type,           │  (circle / slider head+tail / spinner),
  │      is_new_combo, model_prob}]    │  drop x/y, hitsounds, slider curves
  └───────────────────────────────────┘
                 │
                 ▼
  ┌───────────────────────────────────┐
  │ Flatten + shape                    │  difficulty/cfg knob controls density;
  │  - slider policy (head? head+tail) │  strength from new-combo / obj type /
  │  - optional thinning / min-spacing │  model prob; optional snap/merge
  └───────────────────────────────────┘
                 │
                 ▼
        beatmap-v1 JSON  ──►  game (Unity loader already exists)
                 │
                 ▼ (optional, later)
  ┌───────────────────────────────────┐
  │ Personalization re-ranker          │  trained on user's taps/ratings
  │ (reuse Beat_Extractor tooling)     │  nudges/filters toward personal taste
  └───────────────────────────────────┘
```

## Two layers, deliberately separated
1. **General prior** (Mapperatorinator): "where would a competent human map a hit." Solves the data problem — trained on the whole ranked osu! corpus.
2. **Personal taste** (optional, later): the user's own tap/rating data applied as a re-rank / filter on top. This is where the prior `Beat_Extractor` work is reused rather than thrown away.

## Why skip the diffusion model
Mapperatorinator already separates *timing* (transformer decoder tokens) from *position* (a separate diffusion pass over x/y). We only need timing, so we never run diffusion — less compute, fewer dependencies, cleaner output.

## Density control
Primary knobs are the model's `difficulty` (star rating), `cfg_scale`, and `descriptors`. Post-hoc thinning (min spacing, keep-top-N-per-bar) is the backstop. See [[open-questions]] for the policy still to be decided.

## Output contract
`beatmap-v1` JSON (see [[prior-work]] for the exact shape). The extractor maps model output onto existing fields: `time_sec` from time tokens, `source` from osu object type, `strength` from new-combo / object importance / model probability, `confidence` from model probability.

## Fallback
If weights or the model env are unavailable, fall back to the `auto_determining` librosa detector from `Beat_Extractor` so the pipeline still produces *something*.
