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

## Install

Two environments, kept separate on purpose:

1. **Model env** (heavy: Python 3.10 + Blackwell-capable PyTorch). One-time setup
   and the exact commands are in [`docs/model-setup.md`](docs/model-setup.md).
2. **App env** (light): the Beatex package + UI deps.
   ```sh
   uv venv .venv --python 3.12
   uv pip install --python .venv -e ".[app]"
   ```

Beatex finds the model env automatically at `external/Mapperatorinator` (override
with `BEATEX_MODEL_DIR` / `BEATEX_MODEL_PYTHON`).

## Use

CLI:
```sh
beatex extract "song.mp3" --difficulty 4 --year 2021 -o song.beatmap.json
```

UI (tweak + visualize):
```sh
streamlit run app/streamlit_app.py
```
Pick a song and model settings, hit **Generate**, then play the waveform with hit
markers, listen to synced clicks, balance the music/click volumes, adjust the
shaping sliders live (including a global timing offset), and export the
**beatmap-v1 JSON** or a **click-track mp3** (clicks baked into the song — a
browser-latency-free alignment check). **Batch** mode sweeps several
difficulties/years in one click. Every run is saved to a **History** panel (with
the exact settings used) that you can reload and re-shape instantly — no model
re-run — so you can compare difficulties/years/seeds. Run data lives under
`data/` (audio is content-addressed by sha256, so the same song isn't duplicated
across runs).

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
