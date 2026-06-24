---
tags: [beatex, mapperatorinator, model, reference]
---

# Mapperatorinator — notes for reuse

Repo: https://github.com/OliBomby/Mapperatorinator — **MIT licensed** (so we can reuse the code and the released weights). Latest model release **V32** (May 2026).

## What it is
A SOTA osu! beatmap generator. It is the successor to the `osuT5` and `osu-diffusion` projects, and it is composed of two independent models:

| Model | Role | Beatex uses it? |
|-------|------|-----------------|
| **osuT5** — modified Whisper transformer, ~219M params | mel-spectrogram → sparse sequence of **event tokens** (hit objects, **time events @10 ms**, new-combo, hitsounds, timing points) | **YES — this is the rhythm finder** |
| **osu_diffusion** — diffusion model | refines **x/y positions** of objects only | **NO — discard, never run** |

The clean split between *timing* (transformer) and *position* (diffusion) is exactly why this repo is a good fit: we keep the first model, drop the second.

## How timing is produced
- Audio → mel-spectrogram, one frame per encoder input position.
- Decoder emits a softmax over a fixed event vocabulary; it predicts events **sparsely** (only when an object occurs), with time quantized to 10 ms.
- A **"super timing generator"** infers timing for the whole song ~20× and averages — improves precision, helps variable-BPM tracks.
- Training added random offsets to time events, forcing the model to correct timing by listening to onsets (so its timing is genuinely audio-grounded, not just grid-snapped).

## Controllability (our density / style knobs)
- `difficulty` — target star rating. **Most important knob for us** (controls note density/intensity). The docs advise *always* passing a difficulty.
- `cfg_scale` — classifier-free guidance strength.
- `mapper_id`, `descriptors`, `negative_descriptors`, `year` — style conditioning.

## What to keep vs throw away
- **Keep:** the decoded time of each hit object (circles + slider heads; decide on slider tails/spinners — see [[open-questions]]), new-combo flag (a usable "accent/importance" signal), and the model's confidence.
- **Throw away:** x/y coordinates, slider curve/control points, slider velocity, hitsounds, combo colors, the whole `osu_diffusion` stage, and `.osu` file packaging.

## How inference is invoked
- `python inference.py` with Hydra overrides (config: `configs/inference/default.yaml`, `v32.yaml`) — fields like `audio_path`, `output_path`, `gamemode`, `difficulty`, `cfg_scale`, `descriptors`.
- `python web-ui.py` (graphical) and `./cli_inference.sh` (guided) also exist.
- **Integration plan:** call the osuT5 inference path programmatically and intercept the decoded event list *before* it is turned into positions / `.osu`. The exact interception point (a function in `inference.py` / `osuT5/`) is TBD — confirm when the repo is cloned.

## Environment requirements
- **Python 3.10** (note: this machine's system Python is 3.13/3.14 → needs a dedicated 3.10 env).
- ffmpeg on PATH.
- PyTorch + CUDA. **RTX 5080 is Blackwell (sm_120)** → requires a recent build (cu128+/PyTorch 2.10-class); older wheels won't have kernels for this GPU.
- Pretrained weights on HuggingFace Hub (auto-downloaded by inference, or fetched via `huggingface_hub`).

## Key files/dirs
`inference.py` (entry), `osuT5/` (the transformer we want), `osu_diffusion/` (positions — ignore), `configs/inference/`, `web-ui.py`, `requirements.txt`.

## Open risks
- osu! difficulty density is tuned for *gameplay challenge*, not pure musical feel — high difficulties over-map (streams). Tune toward lower star ratings + optional post-hoc thinning.

## Verified on this machine (2026-06-23)
Full reproducible setup + first result: [[model-setup]]. Key confirmations/corrections to the notes above:
- **No token interception needed.** `config_name="v32"` is the default in `inference.py`, and v32 already ships `generate_positions: false` — so the diffusion stage never runs and we simply read the **hit-object times** from the output `.osu` (x/y ignored). The earlier "interception point TBD" risk is moot.
- **Attention = SDPA** (precision is fp32), so Flash-Attention is not required (good on Windows).
- **Env that works:** Python 3.10.20 (via uv) + `torch 2.12.1+cu130` / `torchaudio 2.11.0+cu130`; `sm_120` kernels present; RTX 5080 detected. `torchcodec` is dropped on Windows (no wheel, never imported).
- Weights: `OliBomby/Mapperatorinator-v32` (+ `gamemode=0` subfolder) and `openai/whisper-base`/`-small`, auto-downloaded from HF.
