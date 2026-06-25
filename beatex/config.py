"""Locate the isolated Mapperatorinator model env that Beatex shells out to.

Beatex keeps the heavy model (Python 3.10 + torch) in its own venv and calls it
as a subprocess, so the app/UI layer stays light and the model env can't
contaminate it. Defaults point at the local clone under external/; override with
the BEATEX_MODEL_DIR / BEATEX_MODEL_PYTHON environment variables.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def app_base_dir() -> Path:
    """Base dir for `external/` and `data/`.

    In dev this is the repo root (parent of the beatex package). In a frozen
    PyInstaller build, `__file__` lives inside the unpacked bundle, so we use the
    folder that contains the executable instead (keep Beatex.exe in the repo root).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parent


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@dataclass
class ModelConfig:
    repo_dir: Path
    python: Path

    def validate(self) -> None:
        if not self.repo_dir.exists():
            raise FileNotFoundError(
                f"Mapperatorinator repo not found at {self.repo_dir}. "
                "Clone it there (see docs/model-setup.md) or set BEATEX_MODEL_DIR."
            )
        if not (self.repo_dir / "inference.py").exists():
            raise FileNotFoundError(
                f"inference.py not found in {self.repo_dir}; is this the Mapperatorinator repo?"
            )
        if not self.python.exists():
            raise FileNotFoundError(
                f"Model venv Python not found at {self.python}. "
                "Build it (see docs/model-setup.md) or set BEATEX_MODEL_PYTHON."
            )


def get_model_config() -> ModelConfig:
    default_model_dir = app_base_dir() / "external" / "Mapperatorinator"
    repo_dir = Path(os.environ.get("BEATEX_MODEL_DIR", str(default_model_dir))).resolve()
    py_env = os.environ.get("BEATEX_MODEL_PYTHON")
    python = Path(py_env).resolve() if py_env else _venv_python(repo_dir / ".venv")
    return ModelConfig(repo_dir=repo_dir, python=python)
