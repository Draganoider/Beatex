"""Render an audible click-track over a song from a generated .osu.

Overlays a short click at each hit-object time so you can *hear* whether the
model's hits land where the song feels like they should. New-combo objects
(the model's "accents") get a higher-pitched, louder click so you can tell
whether accents fall on strong beats.

Usage:
    python tools/click_track.py "<.osu>" --audio "<song>" --out "<out.mp3>"
    python tools/click_track.py "<.osu>" --audio "<song>" --out "<out.wav>" --clicks-only
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from inspect_osu import parse_hit_objects  # same tools/ dir

FR = 44100  # working sample rate


def make_click(freq: float, dur_s: float = 0.030, decay: float = 180.0,
               amp: float = 0.9) -> np.ndarray:
    t = np.arange(int(dur_s * FR)) / FR
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * decay)
    return (wave * amp).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osu")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clicks-only", action="store_true",
                    help="Render only the clicks (no song) for a clean timing check.")
    ap.add_argument("--song-gain", type=float, default=0.70,
                    help="Multiplier applied to the song before mixing (default 0.70).")
    ap.add_argument("--click-gain", type=float, default=0.85,
                    help="Peak amplitude of clicks as fraction of full scale (default 0.85).")
    args = ap.parse_args()

    objs = parse_hit_objects(Path(args.osu))
    if not objs:
        raise SystemExit("No hit objects found in the .osu file.")

    # Load + normalize song to stereo float at FR
    seg = AudioSegment.from_file(args.audio).set_frame_rate(FR).set_channels(2)
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32).reshape((-1, 2))
    full_scale = float(1 << (8 * seg.sample_width - 1))  # e.g. 32768 for 16-bit
    song = samples / full_scale  # now in [-1, 1]
    n = song.shape[0]

    clicks = np.zeros((n, 2), dtype=np.float32)
    click_hit = make_click(1500.0)
    click_accent = make_click(2300.0, amp=1.0)

    placed = 0
    for time_ms, _kind, new_combo in objs:
        idx = int(round(time_ms / 1000.0 * FR))
        c = click_accent if new_combo else click_hit
        end = min(idx + len(c), n)
        if 0 <= idx < n:
            seg_len = end - idx
            clicks[idx:end, 0] += c[:seg_len]
            clicks[idx:end, 1] += c[:seg_len]
            placed += 1

    if args.clicks_only:
        mix = clicks * args.click_gain
    else:
        mix = song * args.song_gain + clicks * args.click_gain

    # Clip to [-1, 1] and back to int16
    mix = np.clip(mix, -1.0, 1.0)
    out_i16 = (mix * 32767.0).astype(np.int16)

    out_seg = AudioSegment(
        out_i16.tobytes(), frame_rate=FR, sample_width=2, channels=2,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = out_path.suffix.lstrip(".").lower() or "mp3"
    out_seg.export(out_path, format=fmt)

    print(f"Placed {placed}/{len(objs)} clicks "
          f"({'clicks only' if args.clicks_only else 'mixed with song'}).")
    print(f"Wrote {out_path}  ({out_seg.duration_seconds:.1f}s, {fmt})")


if __name__ == "__main__":
    main()
