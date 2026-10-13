# Beatex

![status](https://img.shields.io/badge/status-alpha-orange)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![built on](https://img.shields.io/badge/built%20on-Mapperatorinator-8a63d2)

Turn **any song into the "best possible" beatmap** — the sequence of hit timings a
human would actually *feel*, across drums, bass, vocals and melody, not just
percussion. The output is musical timing (plus relative intensity) for
music-reactive games and other real-time-to-music use cases.

Beatex reuses **[Mapperatorinator](https://github.com/OliBomby/Mapperatorinator)**
(OliBomby, MIT) — a model pretrained on the huge human-authored osu! beatmap
corpus — purely as a **timing** engine. osu! mappers place hit objects on the
musically meaningful moments of a song, which is exactly the "where does a human
feel a hit" signal we want. Beatex keeps only those hit *times* and discards
everything osu-specific (x/y positions, slider shapes, hitsounds, combos, and the
whole diffusion stage).

## How it works

```
audio → Mapperatorinator V32 (timing only; positions/diffusion skipped)
      → parse .osu hit-object times
      → shape (slider policy · min-spacing · strength/accents · density)
      → beatmap-v1 JSON → your game
```

- **Generate** (slow, GPU) runs the model once.
- **Shape** (instant, no model) re-derives the beatmap from the cached hit-times,
  so density/spacing/slider tweaks are real-time.

## Setup

> Tested on **Windows 11 + an NVIDIA GPU**. The model env is heavy and isolated;
> the app env is light. Linux/macOS work too, but the torch wheel index and venv
> paths (`bin/` vs `Scripts/`) differ — adjust accordingly.

**Prerequisites:** [git](https://git-scm.com), [uv](https://docs.astral.sh/uv/),
[ffmpeg](https://ffmpeg.org) on your `PATH`, and an NVIDIA GPU with a recent driver
(Blackwell / RTX 50-series needs a CUDA-13-capable driver). No CUDA *toolkit*
install is required — the PyTorch wheels bundle the runtime.

```powershell
# 1. Clone Beatex
git clone https://github.com/Draganoider/Beatex.git
cd Beatex

# 2. Model env — clone Mapperatorinator into external/ and build its Python 3.10 venv
git clone --recurse-submodules https://github.com/OliBomby/Mapperatorinator.git external/Mapperatorinator
uv venv external/Mapperatorinator/.venv --python 3.10
#    Blackwell torch stack (cu130). torchcodec is intentionally omitted on Windows
#    (no wheel there, and the code never imports it).
uv pip install --python external/Mapperatorinator/.venv torch torchaudio --index-url https://download.pytorch.org/whl/cu130
uv pip install --python external/Mapperatorinator/.venv -r setup/mapperatorinator-requirements-win.txt

# 3. App env — the Beatex package + UI deps
uv venv .venv --python 3.12
uv pip install --python .venv -e ".[app]"
```
(Beatex Studio itself only needs the standard library. `numpy` and `pydub` from the
`[app]` extra are used for the click-track mp3 export.)

The **first generate downloads the V32 weights** (safetensors — no pickle) and the
Whisper base/small encoders from HuggingFace into `~/.cache/huggingface`. Beatex
finds the model env automatically at `external/Mapperatorinator` (override with the
`BEATEX_MODEL_DIR` / `BEATEX_MODEL_PYTHON` env vars). Full, verified runbook:
[`docs/model-setup.md`](docs/model-setup.md).

## Use

### Beatex Studio (desktop app)

**Double-click `Beatex.bat`.** Beatex Studio opens in its own window (no terminal),
and closing the window stops it. It also runs in any browser
(`python app/studio/server.py --open`), and in the Claude desktop app's browser
pane via `.claude/launch.json`.

- **Generate**: drop in a song, pick a difficulty and style year (or sweep several
  difficulties). Runs queue on the GPU with live progress and can be cancelled.
- **Shape live**: minimum spacing, accent boost, slider policy and timing offset
  update instantly, even while the song plays.
- **Listen**: the song and clicks run on one Web Audio clock, so clicks stay
  sample-accurate. Choose beep/tick/wood/kick clicks, set volumes, play at
  0.5×/0.75×/1×, and flip between runs of a song mid-playback.
- **See it**: a zoomable waveform with strength-coloured hits, a density overview,
  lanes comparing every run of the song, and a rhythm-game preview.
- **Tap along**: tap the beats you feel. Beatex scores every run of the song against
  your taps (precision, recall, F1, your timing bias) and points you to the best one.
- **Export**: `beatmap-v1` JSON or a click-track mp3, saved to `data/exports/`.

Details: [`docs/studio.md`](docs/studio.md). To build a one-file `Beatex.exe`
launcher, run `powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1` (keep the
exe in the repo root so it finds `external/` and `data/`).

### CLI
```sh
beatex extract "song.mp3" --difficulty 4 --year 2021 -o song.beatmap.json
```

### Older UIs
The earlier Streamlit app (`streamlit run app/streamlit_app.py`) and PyQt6 window
(`.venv/Scripts/python app/qt_app.py`, needs the `[gui]` extra) still work and share
the same run history.

## Output: `beatmap-v1`

```json
{
  "version": "beatmap-v1",
  "source":   { "filename": "...", "sha256": "...", "duration_sec": 96.04 },
  "analysis": { "bpm": 150.3, "meter": "4/4", "confidence": 0.8 },
  "events":   [ { "id": "evt_000001", "time_sec": 1.16, "type": "hit",
                  "strength": 0.55, "confidence": 0.75, "source": "circle",
                  "edited": false } ],
  "sections": []
}
```
Deserializes directly with Unity `JsonUtility` (see the loader in the docs).

## Acknowledgements

Beatex is **built on [Mapperatorinator](https://github.com/OliBomby/Mapperatorinator)**
(OliBomby, MIT) — a model trained on the human-authored osu! beatmap corpus. Beatex
clones that project into `external/Mapperatorinator/` (not vendored in this repo) and
reuses **only its timing output**, discarding everything osu-specific. Huge thanks to
OliBomby and to the osu! mapping community whose maps the model learned from.

Beatex is an independent project and is **not affiliated with or endorsed by** the
Mapperatorinator authors. As that project requests: always disclose AI-generated
content where appropriate.

## License

[MIT](LICENSE) © 2026 Yevhen Mishchenko.
The `beatmap-v1` schema/contract is carried over from the author's earlier
Beat_Extractor project.
