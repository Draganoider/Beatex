"""Command-line entry: `beatex extract song.mp3 -o map.json`."""
from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import extract
from .shape import ShapeParams


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="beatex",
        description="Extract a beatmap-v1 JSON (felt hit timings) from a song.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="Run the model and emit beatmap-v1 JSON.")
    ex.add_argument("audio", help="Path to the input audio (mp3/wav/ogg/...).")
    ex.add_argument("-o", "--out", default=None,
                    help="Output JSON path (default: <audio>.beatmap.json).")
    ex.add_argument("--difficulty", type=float, default=4.0,
                    help="Model star rating; lower = sparser, more 'felt' (default 4.0).")
    ex.add_argument("--year", type=int, default=2021, help="Style year 2007-2024 (default 2021).")
    ex.add_argument("--gamemode", type=int, default=0, help="0=std,1=taiko,2=ctb,3=mania.")
    ex.add_argument("--slider-policy", choices=["head", "head_tail"], default="head_tail",
                    help="Emit slider heads only, or heads and tails (default head_tail).")
    ex.add_argument("--min-spacing", type=float, default=0.0,
                    help="Minimum ms between hits; thins density (0=off).")
    ex.add_argument("--spinners", action="store_true", help="Include spinners as hits.")
    ex.add_argument("--cfg-scale", type=float, default=None, help="Classifier-free guidance scale.")
    ex.add_argument("--super-timing", action="store_true",
                    help="Slow, accurate variable-BPM timing pass.")
    ex.add_argument("--seed", type=int, default=None, help="Random seed (reproducible runs).")
    ex.add_argument("--run-dir", default=None, help="Where to write the intermediate .osu.")

    args = ap.parse_args(argv)

    if args.command == "extract":
        params = ShapeParams(
            slider_policy=args.slider_policy,
            include_spinners=args.spinners,
            min_spacing_ms=args.min_spacing,
        )
        beatmap, _parsed, osu = extract(
            args.audio,
            difficulty=args.difficulty,
            year=args.year,
            gamemode=args.gamemode,
            shape_params=params,
            output_dir=args.run_dir,
            cfg_scale=args.cfg_scale,
            super_timing=args.super_timing,
            seed=args.seed,
            on_log=print,
        )
        out = Path(args.out) if args.out else Path(args.audio).with_suffix(".beatmap.json")
        beatmap.save(out)
        n = len(beatmap.events)
        dur = beatmap.source.duration_sec or 1.0
        print(f"\nWrote {out}")
        print(f"{n} events | {n / dur:.2f} hits/sec | bpm {beatmap.analysis.bpm:.1f} "
              f"| meter {beatmap.analysis.meter} | from {osu.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
