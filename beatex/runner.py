"""Run Mapperatorinator V32 inference in its isolated venv via subprocess.

We never import the model into this process — we shell out to the model venv's
Python so the heavy 3.10 + torch env stays decoupled from the app/UI. V32's
config defaults (generate_positions=false, output_type=[TIMING,MAP,SV]) already
give us timing-only output, so no overrides are needed for that.
"""
from __future__ import annotations

import os
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
    on_proc=None,
) -> Path:
    """Run inference and return the path to the produced .osu file.

    `on_proc(proc)` is called with the Popen handle once the model starts, so a
    caller (the Studio job queue) can cancel a run by killing it.
    """
    model = model_cfg or get_model_config()
    model.validate()

    # Absolute paths: the model runs with cwd=its own repo, so relative paths
    # given to the CLI would otherwise resolve against the wrong directory.
    audio_path = Path(audio_path).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    before = _osu_names(output_dir)

    # Double-quote path values so Hydra accepts spaces AND apostrophes in
    # filenames (e.g. "Don't"); single quotes get closed early by an apostrophe.
    # Windows filenames can't contain `"`, so double-quoting is always safe here.
    # Forward slashes avoid backslash-escaping surprises (Windows opens them fine).
    overrides = [
        f'audio_path="{audio_path.as_posix()}"',
        f'output_path="{output_dir.as_posix()}"',
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
    # Unbuffered UTF-8 output so the log streams live and non-ASCII filenames
    # don't break decoding; no console window when launched from a GUI.
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        cmd,
        cwd=str(model.repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if on_proc:
        on_proc(proc)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            log.append(line)
            if on_log:
                on_log(line.rstrip("\n"))
        proc.wait()
    except BaseException:
        proc.kill()  # never leave an orphaned model process on the GPU
        raise

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
