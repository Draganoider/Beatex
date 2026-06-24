"""Persistent store of past generation runs.

Lets the UI list history, see the exact settings used, and reload/re-shape any
run without re-running the model. Layout (all under data/, gitignored):

    data/runs/<run_id>/meta.json
    data/runs/<run_id>/beatmap.osu
    data/audio-cache/<sha256><ext>     # content-addressed, deduped across runs
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RunMeta:
    run_id: str
    created_at: str          # human-readable local time
    created_ts: float        # epoch seconds, for sorting
    audio_filename: str
    audio_sha256: str
    audio_ext: str
    duration_sec: float
    difficulty: float
    year: int
    gamemode: int
    cfg_scale: float | None
    super_timing: bool
    seed: int | None
    n_objects: int           # raw hit objects (pre-shaping)
    bpm: float
    meter: str
    osu_file: str = "beatmap.osu"
    batch_id: str | None = None
    batch_label: str | None = None

    def label(self) -> str:
        cfg = f" · cfg {self.cfg_scale}" if self.cfg_scale else ""
        st = " · ST" if self.super_timing else ""
        return (f"{self.audio_filename}  ·  d{self.difficulty} · {self.year} · "
                f"seed {self.seed}{cfg}{st}  ·  {self.created_at}")


class RunStore:
    def __init__(self, root):
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.audio_dir = self.root / "audio-cache"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    # ---- write ----
    def _cache_audio(self, audio_bytes: bytes, sha256: str, ext: str) -> Path:
        dest = self.audio_dir / f"{sha256}{ext}"
        if not dest.exists():
            dest.write_bytes(audio_bytes)
        return dest

    def save_run(self, *, audio_bytes, audio_filename, audio_sha256, audio_ext,
                 duration_sec, difficulty, year, gamemode, cfg_scale, super_timing,
                 seed, n_objects, bpm, meter, osu_path,
                 batch_id=None, batch_label=None) -> RunMeta:
        ts = time.time()
        run_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts)) + "-" + uuid.uuid4().hex[:4]
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._cache_audio(audio_bytes, audio_sha256, audio_ext)
        shutil.copyfile(osu_path, run_dir / "beatmap.osu")
        meta = RunMeta(
            run_id=run_id,
            created_at=time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
            created_ts=ts,
            audio_filename=audio_filename,
            audio_sha256=audio_sha256,
            audio_ext=audio_ext,
            duration_sec=round(duration_sec, 3),
            difficulty=difficulty,
            year=year,
            gamemode=gamemode,
            cfg_scale=cfg_scale,
            super_timing=super_timing,
            seed=seed,
            n_objects=n_objects,
            bpm=round(bpm, 3),
            meter=meter,
            batch_id=batch_id,
            batch_label=batch_label,
        )
        (run_dir / "meta.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
        return meta

    # ---- read ----
    def list_runs(self) -> list[RunMeta]:
        runs = []
        for d in self.runs_dir.iterdir():
            mp = d / "meta.json"
            if mp.exists():
                try:
                    runs.append(RunMeta(**json.loads(mp.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, TypeError):
                    continue
        runs.sort(key=lambda r: r.created_ts, reverse=True)
        return runs

    def get(self, run_id) -> RunMeta | None:
        mp = self.runs_dir / run_id / "meta.json"
        if not mp.exists():
            return None
        try:
            return RunMeta(**json.loads(mp.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return None

    def osu_path(self, run_id) -> Path:
        return self.runs_dir / run_id / "beatmap.osu"

    def audio_bytes(self, meta: RunMeta) -> bytes | None:
        p = self.audio_dir / f"{meta.audio_sha256}{meta.audio_ext}"
        return p.read_bytes() if p.exists() else None

    def delete(self, run_id) -> None:
        run_dir = self.runs_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
