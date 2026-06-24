"""Beatex — extract the best-possible beatmap (the hit timings a human would
*feel*) from any song, by reusing Mapperatorinator's pretrained osu! timing
model and keeping only the timing.

Public surface:
    from beatex import BeatmapV1, BeatEvent          # output schema
    from beatex.osu_parse import parse_osu           # .osu -> hit objects
    from beatex.shape import shape, ShapeParams       # hit objects -> events
    from beatex.pipeline import extract               # audio -> BeatmapV1
"""
from .schema import (
    VERSION,
    BeatmapV1,
    BeatEvent,
    SourceInfo,
    AnalysisInfo,
    SectionInfo,
    make_event_id,
)

__version__ = "0.1.0"
__all__ = [
    "VERSION",
    "BeatmapV1",
    "BeatEvent",
    "SourceInfo",
    "AnalysisInfo",
    "SectionInfo",
    "make_event_id",
]
