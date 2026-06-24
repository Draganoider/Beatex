"""Shaping: ParsedOsu hit objects -> beatmap-v1 BeatEvents.

This is the *instant* layer — no model involved — so a UI can re-run it on every
slider change. Knobs: slider tail policy, spinner inclusion, min-spacing
thinning, and an accent boost (new-combo objects read as stronger moments).

`confidence` is a placeholder constant: the model's per-hit probability isn't
exposed in the .osu, so we can't derive a true confidence here yet. (A future
version that intercepts the token stream could fill it in.)
"""
from __future__ import annotations

from dataclasses import dataclass

from .osu_parse import ParsedOsu
from .schema import BeatEvent, make_event_id

# Base strength per derived source, before the accent boost. In [0, 1].
_BASE_STRENGTH = {
    "circle": 0.55,
    "slider_head": 0.60,
    "slider_tail": 0.40,
    "spinner_start": 0.70,
    "spinner_end": 0.45,
    "hold_head": 0.60,
    "hold_tail": 0.40,
}
_DEFAULT_CONFIDENCE = 0.75


@dataclass
class ShapeParams:
    slider_policy: str = "head_tail"   # "head" | "head_tail"
    include_spinners: bool = False
    min_spacing_ms: float = 0.0        # 0 = no thinning
    accent_boost: float = 0.30         # added to strength for new-combo objects
    merge_ms: float = 10.0             # collapse near-duplicate times (keep stronger)
    offset_ms: float = 0.0             # shift ALL hit times (− earlier / + later)


def _strength(source: str, accent: bool, accent_boost: float) -> float:
    base = _BASE_STRENGTH.get(source, 0.5)
    return max(0.05, min(1.0, base + (accent_boost if accent else 0.0)))


def shape(parsed: ParsedOsu, params: ShapeParams | None = None) -> list[BeatEvent]:
    p = params or ShapeParams()

    # 1. Expand hit objects into raw (time, source, strength, confidence) points.
    raw: list[tuple[float, str, float, float]] = []
    for o in parsed.objects:
        emit: list[tuple[str, bool, float]] = []  # (source, accent, time)
        if o.kind == "circle":
            emit.append(("circle", o.new_combo, o.time))
        elif o.kind == "slider":
            emit.append(("slider_head", o.new_combo, o.time))
            if p.slider_policy == "head_tail" and o.end_time is not None:
                emit.append(("slider_tail", False, o.end_time))
        elif o.kind == "hold":
            emit.append(("hold_head", o.new_combo, o.time))
            if p.slider_policy == "head_tail" and o.end_time is not None:
                emit.append(("hold_tail", False, o.end_time))
        elif o.kind == "spinner" and p.include_spinners:
            emit.append(("spinner_start", o.new_combo, o.time))
            if o.end_time is not None:
                emit.append(("spinner_end", False, o.end_time))

        for source, accent, t in emit:
            raw.append((t, source, _strength(source, accent, p.accent_boost), _DEFAULT_CONFIDENCE))

    raw.sort(key=lambda r: r[0])

    # 2. Merge near-duplicate times (keep the stronger).
    merge_s = p.merge_ms / 1000.0
    merged: list[tuple[float, str, float, float]] = []
    for r in raw:
        if merged and (r[0] - merged[-1][0]) < merge_s:
            if r[2] > merged[-1][2]:
                merged[-1] = r
        else:
            merged.append(r)

    # 3. Min-spacing thinning. Within the window an accent/stronger hit replaces
    #    the previously kept weaker one, so accents survive density cuts.
    min_s = p.min_spacing_ms / 1000.0
    kept: list[tuple[float, str, float, float]] = []
    for r in merged:
        if min_s > 0 and kept and (r[0] - kept[-1][0]) < min_s:
            if r[2] > kept[-1][2]:
                kept[-1] = r
        else:
            kept.append(r)

    # 4. Materialize events (applying the global timing offset, clamped to >= 0).
    offset = p.offset_ms / 1000.0
    return [
        BeatEvent(
            id=make_event_id(i),
            time_sec=round(max(0.0, t + offset), 3),
            type="hit",
            strength=round(strength, 3),
            confidence=round(conf, 3),
            source=source,
            edited=False,
        )
        for i, (t, source, strength, conf) in enumerate(kept)
    ]
