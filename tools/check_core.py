"""Validate the beatex core (parse -> shape -> export) on an existing .osu.

No model run — exercises everything except the runner against a generated map.

    python tools/check_core.py <path-to.osu> [--audio <song>]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from beatex.audio import audio_duration_sec
from beatex.osu_parse import parse_osu
from beatex.pipeline import build_beatmap
from beatex.shape import ShapeParams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osu", help="Path to a generated .osu file.")
    ap.add_argument("--audio", default=None, help="Optional source audio (for duration + filename).")
    args = ap.parse_args()

    p = parse_osu(args.osu)
    dur = audio_duration_sec(args.audio) if args.audio else (p.objects[-1].time if p.objects else 1.0)
    audio_name = Path(args.audio).name if args.audio else "song"

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
        bm = build_beatmap(p, audio_path=audio_name, shape_params=params, duration_sec=dur)
        srcs: dict[str, int] = {}
        for e in bm.events:
            srcs[e.source] = srcs.get(e.source, 0) + 1
        n = len(bm.events)
        print(f"\n[{label}] {n} events | {n / dur:.2f} hits/s | sources={srcs}")
        print("  first 5:", [(e.id, e.time_sec, e.source, e.strength) for e in bm.events[:5]])

    bm = build_beatmap(p, audio_path=audio_name, shape_params=ShapeParams(), duration_sec=dur, sha256="demo")
    out = Path(args.osu).with_suffix(".beatmap.json")
    bm.save(out)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["version"] == "beatmap-v1"
    assert set(d["source"].keys()) == {"filename", "sha256", "duration_sec"}
    assert set(d["analysis"].keys()) == {"bpm", "meter", "confidence"}
    assert set(d["events"][0].keys()) == {"id", "time_sec", "type", "strength", "confidence", "source", "edited"}
    assert isinstance(d["events"][0]["edited"], bool)
    print(f"\nSaved {out.name} and validated beatmap-v1 schema field names. OK")


if __name__ == "__main__":
    main()
