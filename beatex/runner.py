"""Run Mapperatorinator V32 inference in its isolated venv via subprocess.

We never import the model into this process — we shell out to the model venv's
Python so the heavy 3.10 + torch env stays decoupled from the app/UI. V32's
config defaults (generate_positions=false, output_type=[TIMING,MAP,SV]) already
give us timing-only output, so no overrides are needed for that.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import ModelConfig, get_model_config


def _osu_names(out_dir: Path) -> set[str]:
    return {p.name for p in out_dir.glob("*.osu")}


def run_inference(
    audio_path,
    output_dir,
    *,
    difficulty: float = 4.0,
    year: int = 2021,
    gamemode: int = 0,
    cfg_scale: float | None = None,
    super_timing: bool = False,
    seed: int | None = None,
    extra_overrides: list[str] | None = None,
    model_cfg: ModelConfig | None = None,
    on_log=None,
) -> Path:
    """Run inference and return the path to the produced .osu file."""
    model = model_cfg or get_model_config()
    model.validate()

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    before = _osu_names(output_dir)

    # Single-quote path values so Hydra accepts spaces; forward slashes avoid
    # backslash-escaping surprises (Windows Python opens them fine).
    overrides = [
        f"audio_path='{audio_path.as_posix()}'",
        f"output_path='{output_dir.as_posix()}'",
        f"gamemode={gamemode}",
        f"difficulty={difficulty}",
        f"year={year}",
    ]
    if cfg_scale is not None:
        overrides.append(f"cfg_scale={cfg_scale}")
    if super_timing:
        overrides.append("super_timing=true")
    if seed is not None:
        overrides.append(f"seed={seed}")
    if extra_overrides:
        overrides.extend(extra_overrides)

    cmd = [str(model.python), "inference.py", *overrides]
    log: list[str] = []
    proc = subprocess.Popen(
        cmd,
        cwd=str(model.repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log.append(line)
        if on_log:
            on_log(line.rstrip("\n"))
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            f"inference.py failed (exit {proc.returncode}).\n" + "".join(log[-20:])
        )

    new = sorted(_osu_names(output_dir) - before)
    if new:
        return output_dir / new[-1]
    osus = sorted(output_dir.glob("*.osu"), key=lambda p: p.stat().st_mtime)
    if not osus:
        raise RuntimeError("Inference produced no .osu file.\n" + "".join(log[-20:]))
    return osus[-1]
