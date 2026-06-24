"""Tiny audio helpers (stdlib + ffprobe only — keeps the core dependency-free)."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def audio_duration_sec(path) -> float:
    """Duration via ffprobe (ffmpeg is a Beatex prerequisite). 0.0 if unavailable."""
    for probe in ("ffprobe",):  # must be on PATH (a Beatex prerequisite)
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, check=True,
            )
            return float(out.stdout.strip())
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
            continue
    return 0.0
