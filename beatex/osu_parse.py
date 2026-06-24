"""Parse a generated .osu file into Beatex hit objects.

We only care about *timing* plus two cheap signals: the object type and the
new-combo "accent" flag. Positions, hitsounds and slider shapes are ignored.
Slider end times are computed from the timing points + SliderMultiplier so the
shaping layer can optionally emit slider tails.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path

# osu! hit-object type bitfield
T_CIRCLE = 1 << 0
T_SLIDER = 1 << 1
T_NEW_COMBO = 1 << 2
T_SPINNER = 1 << 3
T_HOLD = 1 << 7  # mania hold note


@dataclass
class HitObject:
    time: float                    # seconds, object start
    kind: str                      # "circle" | "slider" | "spinner" | "hold"
    new_combo: bool                # the model's accent / importance flag
    end_time: float | None = None  # seconds, for sliders / spinners / holds


@dataclass
class ParsedOsu:
    objects: list[HitObject]
    bpm: float
    meter: str
    slider_multiplier: float


def _iter_sections(lines):
    section = None
    for raw in lines:
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        yield section, s


def _parse_timing_points(rows):
    """Return (effective_points, meter, first_uninherited_beat_length).

    effective_points is a sorted list of (time_ms, beat_length_ms, sv) where the
    SV multiplier resets to 1.0 at each uninherited (red) timing point, per the
    osu! rules.
    """
    pts = []
    for s in rows:
        f = s.split(",")
        if len(f) < 2:
            continue
        try:
            t = float(f[0])
            bl = float(f[1])
        except ValueError:
            continue
        uninherited = (len(f) < 7) or (f[6].strip() == "1")
        meter = f[2].strip() if len(f) >= 3 else "4"
        pts.append((t, bl, uninherited, meter))

    pts.sort(key=lambda p: p[0])
    eff = []
    cur_bl, cur_sv, meter = 500.0, 1.0, "4"
    first_uninh_bl = None
    for t, bl, uninh, m in pts:
        if uninh:
            cur_bl = bl
            cur_sv = 1.0  # red line resets slider velocity
            meter = m
            if first_uninh_bl is None:
                first_uninh_bl = bl
        else:
            cur_sv = (-100.0 / bl) if bl < 0 else 1.0
        eff.append((t, cur_bl, cur_sv))
    return eff, meter, (first_uninh_bl or cur_bl)


def _effective_at(eff, t):
    if not eff:
        return 500.0, 1.0
    i = bisect.bisect_right([e[0] for e in eff], t) - 1
    if i < 0:
        i = 0
    return eff[i][1], eff[i][2]


def parse_osu(path) -> ParsedOsu:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

    slider_multiplier = 1.4
    timing_rows: list[str] = []
    hit_rows: list[str] = []
    for section, s in _iter_sections(lines):
        if not s:
            continue
        if section == "Difficulty" and s.startswith("SliderMultiplier"):
            try:
                slider_multiplier = float(s.split(":", 1)[1])
            except (IndexError, ValueError):
                pass
        elif section == "TimingPoints":
            timing_rows.append(s)
        elif section == "HitObjects":
            hit_rows.append(s)

    eff, meter, first_bl = _parse_timing_points(timing_rows)
    bpm = (60000.0 / first_bl) if first_bl else 0.0
    try:
        meter_str = f"{int(float(meter))}/4"
    except ValueError:
        meter_str = "4/4"

    objects: list[HitObject] = []
    for s in hit_rows:
        f = s.split(",")
        if len(f) < 4:
            continue
        try:
            t_ms = float(f[2])
            type_bits = int(f[3])
        except ValueError:
            continue

        new_combo = bool(type_bits & T_NEW_COMBO)
        end_ms = None

        if type_bits & T_SPINNER:
            kind = "spinner"
            if len(f) >= 6:
                try:
                    end_ms = float(f[5])
                except ValueError:
                    pass
        elif type_bits & T_SLIDER:
            kind = "slider"
            try:
                slides = int(f[6])
                length = float(f[7])
                beat_length, sv = _effective_at(eff, t_ms)
                px_per_beat = slider_multiplier * 100.0 * sv
                if px_per_beat:
                    end_ms = t_ms + (length / px_per_beat) * beat_length * slides
            except (IndexError, ValueError, ZeroDivisionError):
                end_ms = None
        elif type_bits & T_HOLD:
            kind = "hold"
            if len(f) >= 6 and ":" in f[5]:
                try:
                    end_ms = float(f[5].split(":")[0])
                except ValueError:
                    pass
        else:
            kind = "circle"

        objects.append(
            HitObject(
                time=t_ms / 1000.0,
                kind=kind,
                new_combo=new_combo,
                end_time=(end_ms / 1000.0) if end_ms is not None else None,
            )
        )

    objects.sort(key=lambda o: o.time)
    return ParsedOsu(
        objects=objects,
        bpm=bpm,
        meter=meter_str,
        slider_multiplier=slider_multiplier,
    )
