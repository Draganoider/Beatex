---
tags: [beatex, open-questions]
---

# Open questions

Decisions that gate the build. Resolve, then move them into [[decisions]].

> **Resolved 2026-06-18:** build location → *fresh, self-contained Beatex* (see [[decisions]]).

## Next action when resuming
Build was deferred (user reviewing the wiki). When given the go-ahead, the first build step is the **model environment setup**: clone Mapperatorinator, create a Python 3.10 env, install a Blackwell-compatible PyTorch/CUDA build (cu128+/2.10-class for the RTX 5080), download the **V32** weights, and run one sample song to confirm raw inference works. Then build the token→`beatmap-v1` adapter. See [[mapperatorinator-notes]].

## 1. Slider / spinner flattening policy
osu! objects aren't all instantaneous. For the beatmap:
- Circles → one hit (obvious).
- Sliders → **head only**, or **head + tail**, or head + ticks? (Affects density and "feel" on held notes.)
- Spinners → ignore, or emit start (and maybe end)?
Proposed default: circle = hit, slider = head+tail, spinner = ignore — and make it configurable. Needs a listening test to confirm.

## 2. Target difficulty / density
What density feels right for the intended use? The `difficulty` star-rating knob is the main control. Likely default to a low–medium star rating and expose it as a parameter; add post-hoc thinning (min spacing) as a backstop. Needs listening tests on a few genres.

## 3. Final consumer
Is Unity + `beatmap-v1` JSON the actual target engine, or is there another consumer (web, Godot, custom)? Affects only the output adapter, not the core. Default assumption: preserve `beatmap-v1` JSON.
