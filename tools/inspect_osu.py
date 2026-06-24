"""Quick inspector for a generated .osu file.

Beatex only cares about the *timing* of hit objects (the moments a human would
feel a hit). This script extracts those times, classifies object types, and
reports density/distribution so we can judge whether the map "feels right"
without opening osu!.

Usage:
    python tools/inspect_osu.py "<path to .osu>" [--audio "<path to audio>"]
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
from pathlib import Path

# osu! hit-object type bitfield
T_CIRCLE = 1 << 0
T_SLIDER = 1 << 1
T_NEW_COMBO = 1 << 2
T_SPINNER = 1 << 3
T_HOLD = 1 << 7


def parse_hit_objects(osu_path: Path):
    lines = osu_path.read_text(encoding="utf-8", errors="replace").splitlines()
    section = None
    objs = []
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        if section != "HitObjects" or not s:
            continue
        parts = s.split(",")
        if len(parts) < 4:
            continue
        try:
            time_ms = int(parts[2])
            type_bits = int(parts[3])
        except ValueError:
            continue
        if type_bits & T_SPINNER:
            kind = "spinner"
        elif type_bits & T_SLIDER:
            kind = "slider"
        elif type_bits & T_HOLD:
            kind = "hold"
        else:
            kind = "circle"
        objs.append((time_ms, kind, bool(type_bits & T_NEW_COMBO)))
    objs.sort(key=lambda o: o[0])
    return objs


def audio_duration_sec(audio_path: Path) -> float | None:
    for probe in ("ffprobe",):  # must be on PATH
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                capture_output=True, text=True, check=True,
            )
            return float(out.stdout.strip())
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osu")
    ap.add_argument("--audio", default=None)
    args = ap.parse_args()

    osu_path = Path(args.osu)
    objs = parse_hit_objects(osu_path)
    if not objs:
        print("No hit objects found.")
        return

    times = [t / 1000.0 for t, _, _ in objs]
    first, last = times[0], times[-1]
    span = last - first
    n = len(objs)

    kinds = {}
    new_combos = 0
    for _, kind, nc in objs:
        kinds[kind] = kinds.get(kind, 0) + 1
        new_combos += int(nc)

    iois = [b - a for a, b in zip(times, times[1:])]

    print(f"File: {osu_path.name}")
    print(f"Hit objects: {n}")
    print(f"  by type: {kinds}")
    print(f"  new-combo (accents): {new_combos}")
    print(f"First hit: {first:6.2f}s   Last hit: {last:6.2f}s   Span: {span:6.2f}s")

    dur = audio_duration_sec(Path(args.audio)) if args.audio else None
    if dur:
        print(f"Audio duration: {dur:6.2f}s   Coverage: {100*span/dur:4.1f}%")
    denom = dur or span
    print(f"Mean density: {n/denom:5.2f} hits/sec")
    if iois:
        print(f"Inter-onset gap: min {min(iois)*1000:4.0f}ms  "
              f"median {statistics.median(iois)*1000:4.0f}ms  "
              f"max {max(iois)*1000:5.0f}ms")

    # 10-second density buckets
    print("\nDensity over time (hits per 10s bucket):")
    end = int(dur or last) + 1
    for b0 in range(0, end, 10):
        c = sum(1 for t in times if b0 <= t < b0 + 10)
        bar = "#" * c
        print(f"  {b0:3d}-{b0+10:3d}s | {c:3d} {bar}")

    print("\nFirst 30 hit times (s):")
    print("  " + ", ".join(f"{t:.2f}" for t in times[:30]))


if __name__ == "__main__":
    main()
