"""Beatex Studio — the local web UI server (stdlib only).

Serves the single-page Studio UI plus a small JSON API over the beatex package:
run library, uploads, a sequential generation queue (one model run at a time on
the GPU), instant shaping, tap-along takes and exports.

    python app/studio/server.py            # serve http://127.0.0.1:8765
    python app/studio/server.py --app      # + open a native app window, and
                                           #   quit when that window closes

It also runs inside the Claude desktop app's browser pane (.claude/launch.json).
Only binds to 127.0.0.1. numpy/pydub are needed only for the click-track mp3
export (the [app]/[gui] extras); everything else is stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

FROZEN = getattr(sys, "frozen", False)
if not FROZEN:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from beatex import __version__  # noqa: E402
from beatex.audio import audio_duration_sec  # noqa: E402
from beatex.config import app_base_dir, get_model_config  # noqa: E402
from beatex.osu_parse import ParsedOsu, parse_osu  # noqa: E402
from beatex.pipeline import build_beatmap, extract  # noqa: E402
from beatex.shape import ShapeParams  # noqa: E402
from beatex.store import RunMeta, RunStore  # noqa: E402

STATIC = (Path(sys._MEIPASS) / "studio_static") if FROZEN else Path(__file__).resolve().parent / "static"
BASE = app_base_dir()
DATA = BASE / "data"
SRC_DIR = DATA / "ui-runs"        # model-input copies of the audio (shared with the old UIs)
OSU_DIR = SRC_DIR / "osu"         # raw model output
EXPORT_DIR = DATA / "exports"
DEFAULT_PORT = 8765
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

store = RunStore(DATA / "runs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/manifest+json", ".webmanifest")


# ------------------------------------------------------------------ helpers
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _num(q: dict, key: str, default: float, lo: float, hi: float) -> float:
    try:
        return _clamp(float(q.get(key, default)), lo, hi)
    except (TypeError, ValueError):
        return default


def shape_params(q: dict) -> ShapeParams:
    """ShapeParams from query/JSON fields (same names the UI sends)."""
    return ShapeParams(
        slider_policy="head" if q.get("policy") == "head" else "head_tail",
        include_spinners=str(q.get("spinners", "")).lower() in ("1", "true", "yes"),
        min_spacing_ms=_num(q, "min_spacing", 0.0, 0.0, 1000.0),
        accent_boost=_num(q, "accent", 0.30, 0.0, 1.0),
        offset_ms=_num(q, "offset", 0.0, -500.0, 500.0),
    )


_parsed_cache: dict[str, ParsedOsu] = {}
_parsed_lock = threading.Lock()


def parsed_for(run_id: str) -> ParsedOsu:
    with _parsed_lock:
        if run_id not in _parsed_cache:
            if len(_parsed_cache) > 64:
                _parsed_cache.clear()
            _parsed_cache[run_id] = parse_osu(store.osu_path(run_id))
        return _parsed_cache[run_id]


def beatmap_for(meta: RunMeta, q: dict):
    return build_beatmap(parsed_for(meta.run_id), audio_path=meta.audio_filename,
                         shape_params=shape_params(q), duration_sec=meta.duration_sec,
                         sha256=meta.audio_sha256)


def run_dict(m: RunMeta) -> dict:
    d = asdict(m)
    d["audio_available"] = store.audio_file(m.audio_sha256, m.audio_ext) is not None
    return d


def export_stem(m: RunMeta) -> str:
    stem = Path(m.audio_filename).stem
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem).strip() or "beatmap"
    return f"{stem} [d{m.difficulty:g} {m.year}]"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        cand = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not cand.exists():
            return cand
    return path


def render_mp3(meta: RunMeta, body: dict) -> bytes:
    from beatex.clicktrack import render_click_track  # numpy + pydub, lazily
    audio = store.audio_bytes(meta)
    if audio is None:
        raise FileNotFoundError("The audio for this run is no longer cached.")
    bm = beatmap_for(meta, body)
    return render_click_track(
        audio, [{"t": e.time_sec, "s": e.strength} for e in bm.events],
        clicks_only=body.get("mode") == "clicks",
        song_gain=_num(body, "song_gain", 0.7, 0.0, 2.0),
        click_gain=_num(body, "click_gain", 0.9, 0.0, 2.0),
    )


def _hide_pydub_consoles() -> None:
    """pydub shells out to ffmpeg; stop each call flashing a console window."""
    if os.name != "nt":
        return
    try:
        import pydub.audio_segment as pas
        import pydub.utils as pu
    except ImportError:
        return

    class _Popen(subprocess.Popen):
        def __init__(self, *a, **kw):
            kw.setdefault("creationflags", NO_WINDOW)
            super().__init__(*a, **kw)

    shim = type(sys)("subprocess_nowindow")
    shim.__dict__.update(vars(subprocess))
    shim.Popen = _Popen
    pas.subprocess = shim
    pu.Popen = _Popen


# ------------------------------------------------------------------ health
_gpu_name: str | None = None


def _probe_gpu() -> None:
    global _gpu_name
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW)
        _gpu_name = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        _gpu_name = ""


def health() -> dict:
    cfg = get_model_config()
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    weights = (hf_home / "hub" / "models--OliBomby--Mapperatorinator-v32").exists()
    repo_ok = (cfg.repo_dir / "inference.py").exists()
    py_ok = cfg.python.exists()
    ffmpeg = shutil.which("ffmpeg") is not None
    ffprobe = shutil.which("ffprobe") is not None
    clicks = all(importlib.util.find_spec(m) is not None for m in ("numpy", "pydub"))
    return {
        "version": __version__,
        "ready": repo_ok and py_ok and ffmpeg and ffprobe,
        "model": {"repo_ok": repo_ok, "python_ok": py_ok, "repo_dir": str(cfg.repo_dir),
                  "python": str(cfg.python), "weights_cached": weights},
        "ffmpeg": ffmpeg, "ffprobe": ffprobe, "clicktrack": clicks,
        "gpu": _gpu_name, "data_dir": str(DATA), "exports_dir": str(EXPORT_DIR),
        "app_mode": APP_MODE.enabled,
    }


# ------------------------------------------------------------------ job queue
_TQDM = re.compile(r"(\d+)%\|.*?\|\s*(\d+)/(\d+)")


@dataclass
class Job:
    id: str
    sha256: str
    ext: str
    filename: str
    difficulty: float
    year: int
    cfg_scale: float | None
    super_timing: bool
    seed: int | None
    batch_id: str | None = None
    batch_label: str | None = None
    status: str = "queued"           # queued | running | done | failed | cancelled
    phase: str = "Waiting for the GPU"
    progress: float = 0.0            # 0..1 across all phases
    created_ts: float = field(default_factory=time.time)
    started_ts: float | None = None
    finished_ts: float | None = None
    run_id: str | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    _phases: int = 0
    _proc: object = None
    _cancel: bool = False

    def public(self, log_since: int | None = None) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if not k.startswith("_") and k != "log"}
        d["log_len"] = len(self.log)
        d["log_tail"] = self.log[-1] if self.log else ""
        if log_since is not None:
            d["log"] = self.log[log_since:]
        return d


class JobQueue:
    """Runs model jobs one at a time (they all want the whole GPU)."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._worker, name="beatex-jobs", daemon=True).start()

    def submit(self, job: Job) -> Job:
        with self.lock:
            self.jobs[job.id] = job
        self.q.put(job.id)
        return job

    def list(self) -> list[dict]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created_ts)
            return [j.public() for j in jobs]

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.status not in ("queued", "running"):
                return False
            job._cancel = True
            if job.status == "queued":
                job.status, job.phase, job.finished_ts = "cancelled", "Cancelled", time.time()
            proc = job._proc
        if proc is not None:
            _kill_tree(proc)
        return True

    def clear_finished(self) -> None:
        with self.lock:
            for jid in [j.id for j in self.jobs.values() if j.status in ("done", "failed", "cancelled")]:
                del self.jobs[jid]

    def busy(self) -> bool:
        with self.lock:
            return any(j.status in ("queued", "running") for j in self.jobs.values())

    def cancel_all(self) -> None:
        for jid in list(self.jobs):
            self.cancel(jid)

    # -- worker
    def _log(self, job: Job, line: str) -> None:
        line = line.replace("\r", "").rstrip()
        if not line:
            return
        if line.startswith("Generating "):
            job._phases += 1
            job.phase = line
        elif line.startswith("Model loaded"):
            job.progress = max(job.progress, 0.03)
        m = _TQDM.search(line)
        if m:
            done, total = int(m.group(2)), max(1, int(m.group(3)))
            frac = done / total
            # Two passes: "Generating timing" (~20% of the time), then "Generating map".
            lo, hi = (0.03, 0.22) if job._phases <= 1 else (0.22, 0.99)
            job.progress = _clamp(lo + (hi - lo) * frac, job.progress, 0.99)
            if len(job.log) and _TQDM.search(job.log[-1]):
                job.log[-1] = line  # collapse tqdm redraws into one line
                return
        job.log.append(line)
        if len(job.log) > 4000:
            del job.log[:1000]

    def _worker(self) -> None:
        while True:
            job_id = self.q.get()
            job = self.get(job_id)
            if job is None or job.status != "queued":
                continue
            job.status, job.started_ts, job.phase = "running", time.time(), "Loading the model"
            try:
                self._run(job)
                job.status, job.phase, job.progress = "done", "Done", 1.0
            except Exception as exc:  # noqa: BLE001
                if job._cancel:
                    job.status, job.phase = "cancelled", "Cancelled"
                else:
                    job.status, job.phase = "failed", "Failed"
                    job.error = str(exc).strip().splitlines()[0][:400] if str(exc).strip() else repr(exc)
                    self._log(job, f"ERROR: {exc}")
            finally:
                job.finished_ts = time.time()
                job._proc = None

    def _run(self, job: Job) -> None:
        cached = store.audio_file(job.sha256, job.ext)
        if cached is None:
            raise FileNotFoundError("Audio not in cache — upload the song again.")
        src = SRC_DIR / "src" / job.sha256[:12] / job.filename
        src.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            shutil.copyfile(cached, src)

        def on_proc(proc):
            job._proc = proc
            if job._cancel:
                _kill_tree(proc)

        bm, parsed, osu = extract(
            src, difficulty=job.difficulty, year=job.year, gamemode=0,
            cfg_scale=job.cfg_scale, super_timing=job.super_timing, seed=job.seed,
            output_dir=OSU_DIR, on_log=lambda line: self._log(job, line), on_proc=on_proc,
        )
        if job._cancel:
            raise RuntimeError("cancelled")
        meta = store.save_run(
            audio_bytes=b"", audio_filename=job.filename, audio_sha256=job.sha256,
            audio_ext=job.ext, duration_sec=bm.source.duration_sec, difficulty=job.difficulty,
            year=job.year, gamemode=0, cfg_scale=job.cfg_scale, super_timing=job.super_timing,
            seed=job.seed, n_objects=len(parsed.objects), bpm=parsed.bpm, meter=parsed.meter,
            osu_path=osu, batch_id=job.batch_id, batch_label=job.batch_label,
        )
        job.run_id = meta.run_id
        self._log(job, f"Saved run {meta.run_id}: {len(parsed.objects)} objects, {parsed.bpm:.1f} BPM")


def _kill_tree(proc) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=NO_WINDOW)
        else:
            proc.kill()
    except OSError:
        pass


jobs = JobQueue()


# ------------------------------------------------------------------ app-window mode
class _AppMode:
    """When launched with --app: quit once the Studio window is gone."""

    def __init__(self):
        self.enabled = False
        self.server: ThreadingHTTPServer | None = None
        self._bye_at: float | None = None
        self._lock = threading.Lock()

    def seen(self) -> None:
        with self._lock:
            self._bye_at = None

    def bye(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._bye_at = time.time()
        threading.Timer(4.0, self._maybe_quit).start()  # grace period for reloads

    def _maybe_quit(self) -> None:
        with self._lock:
            gone = self._bye_at is not None and time.time() - self._bye_at >= 3.5
        if gone:
            self.quit()

    def quit(self) -> None:
        jobs.cancel_all()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


APP_MODE = _AppMode()


def find_app_browser() -> str | None:
    """Edge (always on Windows 11) or Chrome, for a chromeless --app window."""
    candidates = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            candidates += [Path(root) / "Microsoft/Edge/Application/msedge.exe",
                           Path(root) / "Google/Chrome/Application/chrome.exe"]
    for name in ("msedge", "google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    return next((str(c) for c in candidates if c.exists()), None)


def open_window(url: str) -> subprocess.Popen | None:
    browser = find_app_browser()
    if not browser:
        webbrowser.open(url)
        return None
    profile = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Beatex" / "studio-window"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1480,940",
        "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
        "--autoplay-policy=no-user-gesture-required",
    ], creationflags=NO_WINDOW)


# ------------------------------------------------------------------ HTTP
ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn.__name__))
        return fn
    return deco


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "BeatexStudio/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet: only errors
        if sys.stderr and len(args) > 1 and str(args[1]).startswith(("4", "5")) and str(args[1]) != "404":
            sys.stderr.write("[studio] " + fmt % args + "\n")

    # -- plumbing
    def _dispatch(self, method: str):
        url = urlparse(self.path)
        self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        path = unquote(url.path)
        self._raw = None
        try:
            # Read small bodies up front so none is ever left on a keep-alive
            # connection (it would corrupt the next request). Uploads stream.
            if method != "GET" and path != "/api/upload":
                self._raw = self._body_bytes()
            for m, rx, name in ROUTES:
                if m == method:
                    match = rx.match(path)
                    if match:
                        return getattr(self, name)(*match.groups())
            if method == "GET":
                return self._static(path)
            raise HttpError(404, "Not found")
        except HttpError as e:
            self._json({"error": str(e)}, e.status)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _body_bytes(self, limit: int = 1 << 20) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise HttpError(413, "Request too large")
        return self.rfile.read(n) if n else b""

    def _body(self) -> dict:
        raw = self._raw if self._raw is not None else self._body_bytes()
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise HttpError(400, "Invalid JSON") from None

    def _send(self, data: bytes, ctype: str, status: int = 200, headers: dict | None = None):
        hdrs = {"Content-Type": ctype, "Content-Length": str(len(data)), "Cache-Control": "no-store"}
        hdrs.update(headers or {})
        if status >= 400:  # the request body may be unread: don't reuse the connection
            hdrs["Connection"] = "close"
            self.close_connection = True
        self.send_response(status)
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, status: int = 200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def _download(self, data: bytes, ctype: str, filename: str):
        disp = f"attachment; filename=\"{filename.encode('ascii', 'replace').decode()}\"; " \
               f"filename*=UTF-8''{quote(filename)}"
        self._send(data, ctype, headers={"Content-Disposition": disp})

    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            raise HttpError(404, "Not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith(("javascript", "json", "svg+xml")):
            ctype += "; charset=utf-8"
        self._send(target.read_bytes(), ctype)

    def _meta(self, run_id: str) -> RunMeta:
        meta = store.get(run_id)
        if meta is None:
            raise HttpError(404, "Run not found")
        return meta

    # -- API: status
    @route("GET", r"/api/health")
    def api_health(self):
        APP_MODE.seen()
        self._json(health())

    @route("POST", r"/api/heartbeat")
    def api_heartbeat(self):
        APP_MODE.seen()
        self._json({"ok": True})

    @route("POST", r"/api/bye")
    def api_bye(self):
        APP_MODE.bye()
        self._json({"ok": True})

    # -- API: runs
    @route("GET", r"/api/runs")
    def api_runs(self):
        self._json({"runs": [run_dict(m) for m in store.list_runs()]})

    @route("GET", r"/api/runs/([\w-]+)")
    def api_run(self, run_id):
        self._json(run_dict(self._meta(run_id)))

    @route("PATCH", r"/api/runs/([\w-]+)")
    def api_run_patch(self, run_id):
        body = self._body()
        meta = store.update(run_id, starred=body.get("starred"), note=body.get("note"))
        if meta is None:
            raise HttpError(404, "Run not found")
        self._json(run_dict(meta))

    @route("DELETE", r"/api/runs/([\w-]+)")
    def api_run_delete(self, run_id):
        self._meta(run_id)
        store.delete(run_id)
        _parsed_cache.pop(run_id, None)
        self._json({"ok": True})

    @route("GET", r"/api/runs/([\w-]+)/events")
    def api_events(self, run_id):
        meta = self._meta(run_id)
        bm = beatmap_for(meta, self.query)
        parsed = parsed_for(run_id)
        kinds: dict[str, int] = {}
        for o in parsed.objects:
            kinds[o.kind] = kinds.get(o.kind, 0) + 1
        self._json({
            "run_id": run_id, "bpm": bm.analysis.bpm, "meter": bm.analysis.meter,
            "duration_sec": meta.duration_sec, "raw_kinds": kinds,
            "events": [{"t": e.time_sec, "s": e.strength, "src": e.source} for e in bm.events],
        })

    @route("GET", r"/api/runs/([\w-]+)/beatmap\.json")
    def api_beatmap_download(self, run_id):
        meta = self._meta(run_id)
        data = beatmap_for(meta, self.query).to_json().encode("utf-8")
        self._download(data, "application/json", export_stem(meta) + ".beatmap.json")

    @route("GET", r"/api/runs/([\w-]+)/clicktrack\.mp3")
    def api_clicktrack_download(self, run_id):
        meta = self._meta(run_id)
        tag = "clicks" if self.query.get("mode") == "clicks" else "clicktrack"
        self._download(render_mp3(meta, self.query), "audio/mpeg", f"{export_stem(meta)} {tag}.mp3")

    @route("POST", r"/api/runs/([\w-]+)/export")
    def api_export(self, run_id):
        meta = self._meta(run_id)
        body = self._body()
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        if body.get("kind") == "mp3":
            tag = "clicks" if body.get("mode") == "clicks" else "clicktrack"
            path = unique_path(EXPORT_DIR / f"{export_stem(meta)} {tag}.mp3")
            path.write_bytes(render_mp3(meta, body))
        else:
            path = unique_path(EXPORT_DIR / f"{export_stem(meta)}.beatmap.json")
            beatmap_for(meta, body).save(path)
        self._json({"path": str(path), "name": path.name})

    @route("POST", r"/api/reveal")
    def api_reveal(self):
        body = self._body()
        target = Path(body.get("path") or EXPORT_DIR).resolve()
        if not str(target).startswith(str(DATA.resolve())):
            raise HttpError(403, "Can only reveal files inside the Beatex data folder")
        if not target.exists():
            target = target.parent if target.parent.exists() else DATA
        if os.name == "nt":
            args = ["explorer", f"/select,{target}"] if target.is_file() else ["explorer", str(target)]
            subprocess.Popen(args)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])
        self._json({"ok": True})

    # -- API: audio + songs
    @route("POST", r"/api/upload")
    def api_upload(self):
        name = Path(unquote(self.headers.get("X-Filename", "song.mp3"))).name or "song.mp3"
        ext = Path(name).suffix.lower()
        if ext not in AUDIO_EXTS:
            raise HttpError(415, f"Unsupported audio type '{ext}'. Use mp3, wav, ogg, m4a or flac.")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 512 << 20:
            raise HttpError(413, "Empty or too large (max 512 MB)")
        tmp = store.audio_dir / f".upload-{uuid.uuid4().hex}{ext}"
        h, left = hashlib.sha256(), n
        try:
            with open(tmp, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        raise HttpError(400, "Upload interrupted")
                    h.update(chunk)
                    f.write(chunk)
                    left -= len(chunk)
            sha = h.hexdigest()
            dest = store.audio_dir / f"{sha}{ext}"
            if dest.exists():
                tmp.unlink()
            else:
                tmp.replace(dest)
        finally:
            if tmp.exists():
                tmp.unlink()
        runs = [m for m in store.list_runs() if m.audio_sha256 == sha]
        self._json({"sha256": sha, "ext": ext, "filename": name, "size": n,
                    "duration_sec": round(audio_duration_sec(dest), 3), "runs": len(runs)})

    @route("GET", r"/api/audio/([0-9a-f]{64})(\.\w+)")
    def api_audio(self, sha, ext):
        path = store.audio_file(sha, ext.lower())
        if path is None:
            raise HttpError(404, "Audio not cached")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(path.read_bytes(), ctype, headers={"Cache-Control": "private, max-age=86400"})

    @route("GET", r"/api/songs/([0-9a-f]{64})/taps")
    def api_taps(self, sha):
        self._json(store.load_taps(sha))

    @route("POST", r"/api/songs/([0-9a-f]{64})/taps")
    def api_taps_save(self, sha):
        body = self._body()
        taps = [float(t) for t in body.get("taps", []) if isinstance(t, (int, float))]
        if len(taps) < 4:
            raise HttpError(400, "Need at least 4 taps")
        take = store.save_taps(sha, taps, duration_sec=float(body.get("duration_sec") or 0))
        self._json(take)

    @route("DELETE", r"/api/songs/([0-9a-f]{64})/taps")
    def api_taps_delete(self, sha):
        store.delete_taps(sha)
        self._json({"ok": True})

    # -- API: jobs
    @route("GET", r"/api/jobs")
    def api_jobs(self):
        self._json({"jobs": jobs.list()})

    @route("POST", r"/api/jobs")
    def api_jobs_submit(self):
        body = self._body()
        sha, ext = str(body.get("sha256", "")), str(body.get("ext", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or store.audio_file(sha, ext) is None:
            raise HttpError(400, "Unknown song — upload it first")
        filename = Path(str(body.get("filename") or f"song{ext}")).name
        combos = body.get("combos") or [[body.get("difficulty", 4.0), body.get("year", 2021)]]
        if not isinstance(combos, list) or not 1 <= len(combos) <= 40:
            raise HttpError(400, "Between 1 and 40 runs per request")
        cfg = body.get("cfg_scale")
        cfg = None if cfg in (None, "", 1, 1.0) else _clamp(float(cfg), 0.5, 20.0)
        seed = body.get("seed")
        seed = None if seed in (None, "") else int(seed)
        batch_id = batch_label = None
        if len(combos) > 1:
            batch_id = time.strftime("%Y%m%d-%H%M%S")
            diffs = sorted({float(c[0]) for c in combos})
            batch_label = "d" + "/".join(f"{d:g}" for d in diffs)
        created = []
        for diff, year in combos:
            created.append(jobs.submit(Job(
                id=uuid.uuid4().hex[:10], sha256=sha, ext=ext, filename=filename,
                difficulty=round(_clamp(float(diff), 0.0, 10.0), 2),
                year=int(_clamp(int(year), 2007, 2025)), cfg_scale=cfg,
                super_timing=bool(body.get("super_timing")), seed=seed,
                batch_id=batch_id, batch_label=batch_label,
            )).public())
        self._json({"jobs": created})

    @route("GET", r"/api/jobs/(\w+)")
    def api_job(self, job_id):
        job = jobs.get(job_id)
        if job is None:
            raise HttpError(404, "Job not found")
        since = int(self.query.get("since", 0) or 0)
        self._json(job.public(log_since=since))

    @route("DELETE", r"/api/jobs/(\w+)")
    def api_job_cancel(self, job_id):
        self._json({"ok": jobs.cancel(job_id)})

    @route("POST", r"/api/jobs/clear")
    def api_jobs_clear(self):
        jobs.clear_finished()
        self._json({"ok": True})


# ------------------------------------------------------------------ main
class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Browsers drop idle keep-alive connections (e.g. when the window closes).
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        if sys.stderr:
            super().handle_error(request, client_address)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _existing_studio(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            return r.headers.get("Server", "").startswith("BeatexStudio")
    except OSError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Beatex Studio — local web UI.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("BEATEX_PORT", DEFAULT_PORT)))
    ap.add_argument("--app", action="store_true", help="Open a native app window; quit when it closes.")
    ap.add_argument("--open", action="store_true", help="Open the UI in the default browser.")
    args = ap.parse_args(argv)
    if FROZEN and not (argv or sys.argv[1:]):
        args.app = True  # Beatex.exe double-clicked: behave like a desktop app

    port = args.port
    if not _port_free(port):
        if _existing_studio(port):  # already running: just show it
            url = f"http://127.0.0.1:{port}/"
            if args.app:
                open_window(url)
            elif args.open:
                webbrowser.open(url)
            print(f"Beatex Studio is already running at {url}")
            return 0
        if not args.app and not args.open:
            print(f"Port {port} is in use by another program (try --port).", file=sys.stderr)
            return 1
        with socket.socket() as s:  # pick any free port
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    for d in (SRC_DIR, OSU_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _hide_pydub_consoles()
    threading.Thread(target=_probe_gpu, daemon=True).start()

    server = StudioServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Beatex Studio {__version__} — {url}  (data: {DATA})", flush=True)

    if args.app:
        APP_MODE.enabled, APP_MODE.server = True, server
        win = open_window(url)
        if win is not None:
            def watch():
                win.wait()
                time.sleep(2.0)  # Edge may hand off to an existing process; the page beacon covers that
                if win.returncode is not None and not APP_MODE._bye_at:
                    # The window process ended without a page goodbye: only quit if nothing reconnects.
                    APP_MODE.bye()
            threading.Thread(target=watch, daemon=True).start()
    elif args.open:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        jobs.cancel_all()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
