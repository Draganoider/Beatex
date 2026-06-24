---
tags: [beatex, model-setup, runbook, reference]
---

# Model setup & run (verified 2026-06-23)

Reproducible steps that actually worked on this machine (RTX 5080, Windows 11, PowerShell). The Mapperatorinator clone lives in `external/Mapperatorinator/` with its own isolated Python 3.10 venv. See [[mapperatorinator-notes]] for what the model is and [[architecture]] for how its output feeds Beatex.

## Machine facts (confirmed)
- GPU driver advertises **CUDA 13.3** (`nvidia-smi`), so Blackwell `sm_120` is fully supported. No CUDA toolkit install needed — the PyTorch wheels bundle the runtime.
- No system Python 3.10 (3.11–3.14 present); `uv` provides an isolated 3.10.20.
- `git`, `ffmpeg`, `uv` already on PATH.

## Setup (one time)
Run from the cloned **Beatex** root (uv downloads Python 3.10 itself).
```powershell
# 1. Model env: clone Mapperatorinator into external/, isolated Python 3.10 venv
git clone --recurse-submodules https://github.com/OliBomby/Mapperatorinator.git external/Mapperatorinator
uv venv external/Mapperatorinator/.venv --python 3.10

# 2. Blackwell torch stack (cu130). torchcodec is omitted on Windows
#    (0.10.0+cu130 has no Windows wheel and the code never imports it).
uv pip install --python external/Mapperatorinator/.venv torch torchaudio --index-url https://download.pytorch.org/whl/cu130

# 3. Remaining model deps, minus torchcodec (this list ships with Beatex)
uv pip install --python external/Mapperatorinator/.venv -r setup/mapperatorinator-requirements-win.txt

# 4. App env: the Beatex package + UI deps
uv venv .venv --python 3.12
uv pip install --python .venv -e ".[app]"
```
Result: `torch 2.12.1+cu130`, `torchaudio 2.11.0+cu130`. `torch.cuda.get_arch_list()` includes `sm_120`; device = `NVIDIA GeForce RTX 5080`, capability `(12, 0)`. (The README nominally asks for torch 2.10 / CUDA 13.0; cu130 currently serves 2.12.1 and it works fine.)

## Run (timing map, positions skipped)
`config_name="v32"` is the **default** in `inference.py`, and v32 already sets `generate_positions: false` (diffusion never runs) and `output_type: [TIMING, MAP, SV]`. Must run **from the repo directory**.
```powershell
Set-Location "C:\My programs\Beatex\external\Mapperatorinator"
& ".\.venv\Scripts\python.exe" inference.py audio_path="'<song>'" output_path="'<out dir>'" gamemode=0 difficulty=4 year=2021
```
- Quote paths as `"'...'"` (outer double for PowerShell, inner single for Hydra) so spaces/backslashes survive.
- Attention auto-selects **SDPA** (precision is fp32), so Flash-Attention is NOT required — important on Windows.
- First run downloads weights from HF: `OliBomby/Mapperatorinator-v32` (+ a `gamemode=0` subfolder) and `openai/whisper-base`/`-small`. Cached under `~/.cache/huggingface`.
- Output: `beatmap<hex>.osu` in the output dir. Beatex reads the hit-object **times** from `[HitObjects]`; x/y are ignored.

## Inspect output
`tools/inspect_osu.py` parses a generated `.osu` and prints count, type breakdown, a density histogram, and the first hit times:
```powershell
& "<venv>\Scripts\python.exe" "C:\My programs\Beatex\tools\inspect_osu.py" "<the .osu>" --audio "<the song>"
```

## First test result — Rammstein – Sonne (difficulty=4, gamemode=0)
- 710 hit objects (415 circles, 292 sliders, 3 spinners), 122 new-combos.
- Covers 4.19 s → 267.90 s of a 272.97 s song = **96.6% coverage** (whole song, no dead zones).
- Mean density **2.60 hits/sec**; inter-onset gap median 200 ms, max 2.4 s.
- Density tracks song structure (denser in choruses, sparser in quiet parts) — it responds to the music rather than laying a metronomic grid.
- Generation: ~37 s timing pass + ~2:12 map pass on the 5080 (fp32 / SDPA), plus first-time weight download.
- **Still open:** the *audible* "feels right" judgement (click-track listen), the slider tail policy (see [[open-questions]]), and the right default difficulty/density.

## Provenance & safety (pinned 2026-06-23)
- Repo commit: `25923b4f570889e2899f3fdb82de02ddd68ac81c`, remote `github.com/OliBomby/Mapperatorinator` (MIT).
- V32 weights snapshot `74f2258…`: files are **`model.safetensors`** + `tokenizer.json` + `config.json` + `generation_config.json` — **no executable pickle**. safetensors cannot run code on load.
- The pickle-loaded `osu-diffusion-v2` model is **never fetched or loaded** because `generate_positions: false`.
- Also cached: `openai/whisper-base` and `openai/whisper-small` (official OpenAI models — the audio-encoder base).
- Code scan of the inference path: no network uploads, no destructive file ops, no `exec`/`eval` of remote code. `subprocess`/`socket` use is local-only and confined to the web UI / training scripts we do not run.
- Caveat: the `.venv` isolates *dependencies*, not OS permissions — it is not a sandbox. Stronger isolation (WSL/Docker — the repo ships a `Dockerfile`/`compose.yaml`, or a VM / separate user) is optional and only worth it if you want belt-and-suspenders.

## Performance notes (2026-06-23)
Generation is **latency-bound, not compute-bound**: batch-size-1 autoregressive decoding of a 219M model, so the GPU sits ~1% utilized and per-token launch/memory overhead dominates.
- **fp32 vs bf16 make no difference** (idle-GPU bench, first 40 s of Sonne: map pass 23 s fp32 vs 24 s bf16; fp32 marginally faster). Do **not** add a precision toggle — it can't help.
- A full-song generate is **~3 min on an idle GPU**; cost scales with the number of hit objects/tokens, not just duration. Other GPU work contends hard — a busy GPU pushed the same map pass 23 s → 35 s.
- Real speed levers (only if it ever matters): `torch.compile` / CUDA graphs kill the per-token overhead that *is* the bottleneck — but need Triton, so **WSL/Linux only**, not Windows; or reduce window overlap (`lookback`/`lookahead`); or distill a timing-only student model. Otherwise treat speed as a one-time, offline, per-song cost (generate once, shape instantly).
