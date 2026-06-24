"""beatmap-v1 schema — the Beatex output contract.

Mirrors exactly the fields the Unity loader (Beat_Extractor/unity/
BeatmapLoaderExample.cs) deserializes with JsonUtility, so the JSON Beatex emits
is drop-in compatible with existing game consumers:

    {
      "version": "beatmap-v1",
      "source":   {"filename", "sha256", "duration_sec"},
      "analysis": {"bpm", "meter", "confidence"},
      "events":   [{"id", "time_sec", "type", "strength", "confidence",
                    "source", "edited"}],
      "sections": [{"time_sec", "type"}]
    }

JsonUtility is strict about field *names* and *types* (float vs int, bool), so
keep numeric fields floats and `edited` a bool.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = "beatmap-v1"


@dataclass
class SourceInfo:
    filename: str = ""
    sha256: str = ""
    duration_sec: float = 0.0


@dataclass
class AnalysisInfo:
    bpm: float = 0.0
    meter: str = "4/4"
    confidence: float = 0.0


@dataclass
class BeatEvent:
    id: str
    time_sec: float
    type: str = "hit"
    strength: float = 0.5
    confidence: float = 0.5
    source: str = "model"
    edited: bool = False


@dataclass
class SectionInfo:
    time_sec: float
    type: str = ""


@dataclass
class BeatmapV1:
    source: SourceInfo = field(default_factory=SourceInfo)
    analysis: AnalysisInfo = field(default_factory=AnalysisInfo)
    events: list[BeatEvent] = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    version: str = VERSION

    def to_dict(self) -> dict:
        # version first for readability; JsonUtility ignores key order.
        return {
            "version": self.version,
            "source": asdict(self.source),
            "analysis": asdict(self.analysis),
            "events": [asdict(e) for e in self.events],
            "sections": [asdict(s) for s in self.sections],
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def make_event_id(index: int) -> str:
    """Stable, sortable event id, e.g. evt_000001."""
    return f"evt_{index:06d}"
