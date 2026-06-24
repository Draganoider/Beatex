"""End-to-end: audio -> beatmap-v1.

Split so a UI can do the slow part once and the fast part repeatedly:
  - run_inference + parse_osu  -> ParsedOsu   (slow: the model; cache this)
  - build_beatmap(parsed, ...) -> BeatmapV1   (instant: shaping only)
"""
from __future__ import annotations

from pathlib import Path

from .audio import audio_duration_sec, sha256_file
from .osu_parse import ParsedOsu, parse_osu
from .runner import run_inference
from .schema import AnalysisInfo, BeatmapV1, SourceInfo
from .shape import ShapeParams, shape


def build_beatmap(
    parsed: ParsedOsu,
    *,
    audio_path,
    shape_params: ShapeParams | None = None,
    duration_sec: float | None = None,
    sha256: str | None = None,
    analysis_confidence: float = 0.8,
) -> BeatmapV1:
    """Shape an already-parsed .osu into a beatmap-v1 (instant, no model)."""
    audio_path = Path(audio_path)
    events = shape(parsed, shape_params)
    source = SourceInfo(
        filename=audio_path.name,
        sha256=sha256 or "",
        duration_sec=round(duration_sec or 0.0, 3),
    )
    analysis = AnalysisInfo(
        bpm=round(parsed.bpm, 3),
        meter=parsed.meter,
        confidence=analysis_confidence,
    )
    return BeatmapV1(source=source, analysis=analysis, events=events, sections=[])


def extract(
    audio_path,
    *,
    difficulty: float = 4.0,
    year: int = 2021,
    gamemode: int = 0,
    shape_params: ShapeParams | None = None,
    output_dir=None,
    cfg_scale: float | None = None,
    super_timing: bool = False,
    seed: int | None = None,
    on_log=None,
) -> tuple[BeatmapV1, ParsedOsu, Path]:
    """Full run: model -> parse -> shape. Returns (beatmap, parsed, osu_path).

    `parsed` is returned so callers (the UI) can cache it and re-shape with
    different ShapeParams without re-running the model.
    """
    audio_path = Path(audio_path)
    out_dir = Path(output_dir) if output_dir else (audio_path.parent / "beatex_out")
    osu_path = run_inference(
        audio_path, out_dir,
        difficulty=difficulty, year=year, gamemode=gamemode,
        cfg_scale=cfg_scale, super_timing=super_timing, seed=seed, on_log=on_log,
    )
    parsed = parse_osu(osu_path)
    beatmap = build_beatmap(
        parsed,
        audio_path=audio_path,
        shape_params=shape_params,
        duration_sec=audio_duration_sec(audio_path),
        sha256=sha256_file(audio_path),
    )
    return beatmap, parsed, osu_path
