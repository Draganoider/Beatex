"""Validate the beatex core (parse -> shape -> export) on an existing .osu.

No model run: this exercises everything except runner.py against the already
generated Rammstein test map, so it's instant.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # Beatex root

from beatex.osu_parse import parse_osu
from beatex.pipeline import build_beatmap
from beatex.shape import ShapeParams

ROOT = Path(__file__).resolve().parent.parent
OSU = ROOT / "data/test-runs/rammstein-sonne/beatmapbfe14c9a665f48cd931186ea0eee2748.osu"
AUDIO = "C:/Users/Draga/Music/SpookboxMixtape/Rammstein - Sonne.mp3"
DUR = 272.97

p = parse_osu(OSU)
kinds: dict[str, int] = {}
sliders_with_end = 0
for o in p.objects:
    kinds[o.kind] = kinds.get(o.kind, 0) + 1
    if o.kind == "slider" and o.end_time:
        sliders_with_end += 1
print("Parsed:", len(p.objects), "objects", kinds)
print("bpm", round(p.bpm, 2), "meter", p.meter, "sliderMult", p.slider_multiplier)
print("sliders with computed end time:", sliders_with_end)

for params, label in [
    (ShapeParams(), "default (head_tail)"),
    (ShapeParams(slider_policy="head"), "head only"),
    (ShapeParams(min_spacing_ms=140), "head_tail + 140ms min-spacing"),
]:
    bm = build_beatmap(p, audio_path=AUDIO, shape_params=params, duration_sec=DUR)
    srcs: dict[str, int] = {}
    for e in bm.events:
        srcs[e.source] = srcs.get(e.source, 0) + 1
    n = len(bm.events)
    print(f"\n[{label}] {n} events | {n / DUR:.2f} hits/s | sources={srcs}")
    print("  first 5:", [(e.id, e.time_sec, e.source, e.strength) for e in bm.events[:5]])

# Save one and validate the JSON shape matches the Unity contract field-for-field.
bm = build_beatmap(p, audio_path=AUDIO, shape_params=ShapeParams(), duration_sec=DUR, sha256="demo")
out = ROOT / "data/test-runs/rammstein-sonne/sonne.beatmap.json"
bm.save(out)
d = json.loads(out.read_text(encoding="utf-8"))
assert d["version"] == "beatmap-v1"
assert set(d["source"].keys()) == {"filename", "sha256", "duration_sec"}
assert set(d["analysis"].keys()) == {"bpm", "meter", "confidence"}
assert set(d["events"][0].keys()) == {"id", "time_sec", "type", "strength", "confidence", "source", "edited"}
assert isinstance(d["events"][0]["edited"], bool)
print(f"\nSaved {out.name} and validated beatmap-v1 schema field names. OK")
