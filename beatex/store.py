"""Persistent store of past generation runs.

Lets the UI list history, see the exact settings used, and reload/re-shape any
run without re-running the model. Layout (all under data/, gitignored):

    data/runs/<run_id>/meta.json
    data/runs/<run_id>/beatmap.osu
    data/audio-cache/<sha256><ext>     # content-addressed, deduped across runs
    data/taps/<sha256>.json            # tap-along takes per song (Studio)
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
    starred: bool = False
    note: str = ""

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
        self.taps_dir = self.root / "taps"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    # ---- write ----
    def cache_audio(self, audio_bytes: bytes, sha256: str, ext: str) -> Path:
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
        self.cache_audio(audio_bytes, audio_sha256, audio_ext)
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
        self._write_meta(meta)
        return meta

    def _write_meta(self, meta: RunMeta) -> None:
        path = self.runs_dir / meta.run_id / "meta.json"
        path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")

    def update(self, run_id, *, starred: bool | None = None, note: str | None = None) -> RunMeta | None:
        """Edit the user-owned fields of a run (star, note)."""
        meta = self.get(run_id)
        if meta is None:
            return None
        if starred is not None:
            meta.starred = bool(starred)
        if note is not None:
            meta.note = str(note)[:2000]
        self._write_meta(meta)
        return meta

    def save_taps(self, audio_sha256: str, taps: list[float], *, duration_sec: float = 0.0) -> dict:
        """Append a tap-along take (seconds, latency-corrected) for a song."""
        self.taps_dir.mkdir(parents=True, exist_ok=True)
        data = self.load_taps(audio_sha256)
        take = {
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "created_ts": time.time(),
            "duration_sec": round(float(duration_sec), 3),
            "taps": [round(float(t), 4) for t in sorted(taps)],
        }
        data["takes"].append(take)
        path = self.taps_dir / f"{audio_sha256}.json"
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        return take

    def load_taps(self, audio_sha256: str) -> dict:
        path = self.taps_dir / f"{audio_sha256}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data.get("takes"), list):
                    return data
            except (json.JSONDecodeError, AttributeError):
                pass
        return {"audio_sha256": audio_sha256, "takes": []}

    def delete_taps(self, audio_sha256: str) -> None:
        (self.taps_dir / f"{audio_sha256}.json").unlink(missing_ok=True)

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

    def audio_file(self, sha256: str, ext: str) -> Path | None:
        p = self.audio_dir / f"{sha256}{ext}"
        return p if p.exists() else None

    def audio_bytes(self, meta: RunMeta) -> bytes | None:
        p = self.audio_file(meta.audio_sha256, meta.audio_ext)
        return p.read_bytes() if p else None

    def delete(self, run_id) -> None:
        run_dir = self.runs_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
