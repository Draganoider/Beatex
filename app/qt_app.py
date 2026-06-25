"""Beatex desktop GUI (PyQt6).

Run Beatex as a windowed program — pick a song, generate, shape, preview (with
the clicks baked into one synced audio stream), and export — without launching
Streamlit from a terminal. Shares the same run History as the Streamlit app.

Launch:  double-click Beatex.bat   (or  .venv/Scripts/python app/qt_app.py)
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)

from beatex.audio import audio_duration_sec
from beatex.config import app_base_dir
from beatex.osu_parse import parse_osu
from beatex.pipeline import build_beatmap, extract
from beatex.shape import ShapeParams
from beatex.store import RunStore

BASE = app_base_dir()  # repo root in dev; exe folder when frozen
RUN_DIR = BASE / "data" / "ui-runs"
PREVIEW = RUN_DIR / "_preview.mp3"


def audio_envelope(audio_bytes: bytes, buckets: int = 1400):
    """Mono peak envelope (0..1) + duration, for drawing the waveform."""
    import numpy as np
    from pydub import AudioSegment

    seg = AudioSegment.from_file(io.BytesIO(audio_bytes)).set_channels(1)
    a = np.array(seg.get_array_of_samples(), dtype=np.float32)
    if a.size == 0:
        return [], 0.0
    a = np.abs(a) / (float(1 << (8 * seg.sample_width - 1)) or 1.0)
    n = min(buckets, a.size)
    idx = (np.arange(n + 1) * a.size // n)
    env = [float(a[idx[i]:idx[i + 1]].max()) if idx[i + 1] > idx[i] else 0.0 for i in range(n)]
    return env, seg.duration_seconds


# --------------------------- background model worker ---------------------------
class GenerateWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    one_done = pyqtSignal(object, object)   # (RunMeta, ParsedOsu)
    failed = pyqtSignal(str)
    all_done = pyqtSignal()

    def __init__(self, store, audio_file, audio_bytes, name, combos, base):
        super().__init__()
        self.store, self.audio_file, self.audio_bytes, self.name = store, audio_file, audio_bytes, name
        self.combos, self.base = combos, base

    def run(self):
        total = len(self.combos)
        for i, (diff, yr) in enumerate(self.combos):
            self.progress.emit(i, total)
            self.log.emit(f"--- Run {i + 1}/{total}: difficulty {diff}, year {yr} ---")
            try:
                bm, parsed, osu = extract(
                    self.audio_file, difficulty=diff, year=yr, gamemode=0,
                    cfg_scale=self.base["cfg_scale"], super_timing=self.base["super_timing"],
                    seed=self.base["seed"], output_dir=RUN_DIR / "osu",
                    on_log=lambda line: self.log.emit(line),
                )
                meta = self.store.save_run(
                    audio_bytes=self.audio_bytes, audio_filename=self.name,
                    audio_sha256=bm.source.sha256, audio_ext=Path(self.name).suffix.lower(),
                    duration_sec=bm.source.duration_sec, difficulty=diff, year=yr, gamemode=0,
                    cfg_scale=self.base["cfg_scale"], super_timing=self.base["super_timing"],
                    seed=self.base["seed"], n_objects=len(parsed.objects), bpm=parsed.bpm,
                    meter=parsed.meter, osu_path=osu,
                    batch_id=self.base.get("batch_id"), batch_label=self.base.get("batch_label"),
                )
                self.one_done.emit(meta, parsed)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(f"difficulty {diff}, year {yr}: {exc}")
        self.progress.emit(total, total)
        self.all_done.emit()


# --------------------------- waveform widget ---------------------------
class WaveformView(QWidget):
    seeked = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self._env, self._dur, self._markers, self._pos = [], 1.0, [], 0.0

    def set_audio(self, env, dur):
        self._env, self._dur = env, max(0.001, dur)
        self.update()

    def set_markers(self, markers):
        self._markers = markers
        self.update()

    def set_position(self, sec):
        self._pos = sec
        self.update()

    def mousePressEvent(self, e):
        if self.width() > 0:
            self.seeked.emit(max(0.0, min(self._dur, e.position().x() / self.width() * self._dur)))

    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#10151c"))
        mid = h / 2
        if self._env:
            p.setPen(QPen(QColor("#2c4a63")))
            n = len(self._env)
            for x in range(w):
                v = self._env[min(n - 1, int(x / w * n))]
                p.drawLine(x, int(mid - v * mid), x, int(mid + v * mid))
        for t, s in self._markers:
            x = int(t / self._dur * w)
            col = QColor(int(43 + 212 * s), int(214 - 34 * s), int(198 - 114 * s))
            col.setAlphaF(0.45 + 0.5 * s)
            p.setPen(QPen(col, 1 + s))
            p.drawLine(x, h, x, int(h - (0.25 + 0.75 * s) * h))
        px = int(self._pos / self._dur * w)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(px, 0, px, h)
        p.end()


# --------------------------- main window ---------------------------
class BeatexWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beatex — felt-beat extractor")
        self.resize(1120, 740)
        self.store = RunStore(BASE / "data" / "runs")
        RUN_DIR.mkdir(parents=True, exist_ok=True)

        self.parsed = self.audio_bytes = self.audio_name = self.run_meta = None
        self.duration, self.events, self.worker = 0.0, [], None

        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.player.positionChanged.connect(lambda ms: self._tick(ms))
        self.player.durationChanged.connect(lambda ms: self.pos_slider.setMaximum(max(1, ms)))
        self.player.playbackStateChanged.connect(self._on_play_state)

        self._build_ui()
        self._refresh_history()

    # ---- construction ----
    def _build_ui(self):
        split = QSplitter()
        split.addWidget(self._controls())
        split.addWidget(self._stage())
        split.setStretchFactor(1, 1)
        split.setSizes([370, 750])
        self.setCentralWidget(split)
        self.status = self.statusBar()
        self.status.showMessage("Pick a song and Generate — or double-click a past run.")

    def _controls(self):
        box = QVBoxLayout()

        g_song = QGroupBox("1 · Song")
        s = QHBoxLayout(g_song)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("path to an mp3/wav…")
        self.path_edit.editingFinished.connect(self._load_from_path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        s.addWidget(self.path_edit)
        s.addWidget(browse)
        box.addWidget(g_song)

        g_model = QGroupBox("2 · Model — slow, needs Generate")
        f = QFormLayout(g_model)
        self.difficulty = QDoubleSpinBox(); self.difficulty.setRange(1.0, 8.0); self.difficulty.setSingleStep(0.5); self.difficulty.setValue(4.0)
        self.year = QSpinBox(); self.year.setRange(2007, 2024); self.year.setValue(2021)
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(1.0, 8.0); self.cfg.setSingleStep(0.5); self.cfg.setValue(1.0)
        self.super_timing = QCheckBox("Super timing (slow)")
        self.seed = QSpinBox(); self.seed.setRange(0, 999999); self.seed.setValue(7)
        f.addRow("Difficulty", self.difficulty)
        f.addRow("Year", self.year)
        f.addRow("CFG scale", self.cfg)
        f.addRow("", self.super_timing)
        f.addRow("Seed", self.seed)
        self.gen_btn = QPushButton("⚡ Generate")
        self.gen_btn.clicked.connect(self._generate)
        f.addRow(self.gen_btn)
        self.batch_edit = QLineEdit("3, 4, 5")
        self.batch_btn = QPushButton("⚡ Run batch (difficulties)")
        self.batch_btn.clicked.connect(self._batch)
        f.addRow("Batch diffs", self.batch_edit)
        f.addRow(self.batch_btn)
        box.addWidget(g_model)

        g_shape = QGroupBox("3 · Shape — instant")
        f2 = QFormLayout(g_shape)
        self.policy = QComboBox(); self.policy.addItems(["head_tail", "head"])
        self.spinners = QCheckBox("Include spinners")
        self.min_spacing = self._slider(0, 500, 0)
        self.accent = self._slider(0, 50, 30)
        self.offset = self._slider(-150, 150, 0)
        for wdg in (self.policy,):
            wdg.currentIndexChanged.connect(self._reshape)
        self.spinners.stateChanged.connect(self._reshape)
        for sl in (self.min_spacing, self.accent, self.offset):
            sl.valueChanged.connect(self._reshape)
        f2.addRow("Sliders", self.policy)
        f2.addRow("", self.spinners)
        f2.addRow("Min spacing ms", self.min_spacing)
        f2.addRow("Accent ×100", self.accent)
        f2.addRow("Offset ms", self.offset)
        box.addWidget(g_shape)

        g_prev = QGroupBox("4 · Preview (clicks baked in)")
        f3 = QFormLayout(g_prev)
        self.prev_mode = QComboBox(); self.prev_mode.addItems(["song + clicks", "clicks only"])
        self.music_vol = self._slider(0, 100, 70)
        self.click_vol = self._slider(0, 150, 90)
        self.build_btn = QPushButton("🎧 Build && Play")
        self.build_btn.clicked.connect(self._build_preview)
        f3.addRow("Mode", self.prev_mode)
        f3.addRow("Music vol", self.music_vol)
        f3.addRow("Click vol", self.click_vol)
        f3.addRow(self.build_btn)
        box.addWidget(g_prev)

        g_exp = QGroupBox("5 · Export")
        e = QHBoxLayout(g_exp)
        b_json = QPushButton("Save JSON…"); b_json.clicked.connect(self._save_json)
        b_mp3 = QPushButton("Save mp3…"); b_mp3.clicked.connect(self._save_mp3)
        e.addWidget(b_json); e.addWidget(b_mp3)
        box.addWidget(g_exp)
        box.addStretch(1)

        inner = QWidget(); inner.setLayout(box)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(inner)
        scroll.setMinimumWidth(360)
        return scroll

    def _stage(self):
        v = QVBoxLayout()
        self.caption = QLabel("No map loaded.")
        self.caption.setStyleSheet("color:#9aa;")
        self.metrics = QLabel("")
        self.metrics.setStyleSheet("font-size:15px;")
        v.addWidget(self.caption)
        v.addWidget(self.metrics)

        self.wave = WaveformView()
        self.wave.seeked.connect(lambda sec: self.player.setPosition(int(sec * 1000)))
        v.addWidget(self.wave, 1)

        t = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play"); self.play_btn.clicked.connect(self._toggle_play)
        self.pos_slider = QSlider(Qt.Orientation.Horizontal); self.pos_slider.setRange(0, 1)
        self.pos_slider.sliderMoved.connect(lambda ms: self.player.setPosition(ms))
        self.time_lbl = QLabel("0.0s")
        vol = self._slider(0, 100, 90); vol.valueChanged.connect(lambda val: self.audio_out.setVolume(val / 100))
        self.audio_out.setVolume(0.9)
        t.addWidget(self.play_btn); t.addWidget(self.pos_slider, 1); t.addWidget(self.time_lbl)
        t.addWidget(QLabel("🔊")); t.addWidget(vol)
        v.addLayout(t)

        v.addWidget(QLabel("History — double-click to load:"))
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(self._load_history_item)
        self.history.setMaximumHeight(150)
        v.addWidget(self.history)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        v.addWidget(self.progress)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(120)
        self.log.setPlaceholderText("Model log appears here during Generate…")
        v.addWidget(self.log)

        w = QWidget(); w.setLayout(v)
        return w

    def _slider(self, lo, hi, val):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi); s.setValue(val)
        return s

    # ---- audio loading ----
    def _browse(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Choose a song", "",
                                            "Audio (*.mp3 *.wav *.ogg *.m4a *.flac)")
        if fn:
            self.path_edit.setText(fn)
            self._load_from_path()

    def _load_from_path(self):
        p = Path(self.path_edit.text().strip())
        if p.exists() and p.is_file():
            self._set_audio(p.read_bytes(), p.name)

    def _set_audio(self, audio_bytes, name):
        self.audio_bytes, self.audio_name = audio_bytes, name
        try:
            env, dur = audio_envelope(audio_bytes)
        except Exception:  # noqa: BLE001
            env, dur = [], audio_duration_sec(name) or 0.0
        self.duration = dur or self.duration
        self.wave.set_audio(env, self.duration)
        self.status.showMessage(f"Loaded {name}")

    # ---- generate / batch ----
    def _base(self):
        return dict(cfg_scale=(self.cfg.value() if self.cfg.value() != 1.0 else None),
                    super_timing=self.super_timing.isChecked(), seed=self.seed.value())

    def _start(self, combos, batch=None):
        if not self.audio_bytes:
            QMessageBox.warning(self, "No song", "Pick a song first (Browse or a path).")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Busy", "A generation is already running.")
            return
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        audio_file = RUN_DIR / self.audio_name
        audio_file.write_bytes(self.audio_bytes)
        base = self._base()
        if batch:
            base["batch_id"], base["batch_label"] = batch
        self.log.clear()
        self.progress.setVisible(True)
        self.gen_btn.setEnabled(False); self.batch_btn.setEnabled(False)
        self.worker = GenerateWorker(self.store, audio_file, self.audio_bytes, self.audio_name, combos, base)
        self.worker.log.connect(lambda l: self.log.appendPlainText(l))
        self.worker.progress.connect(lambda d, t: (self.progress.setMaximum(t), self.progress.setValue(d)))
        self.worker.one_done.connect(self._on_one_done)
        self.worker.failed.connect(lambda m: self.log.appendPlainText("FAILED: " + m))
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()
        self.status.showMessage("Generating… (model run, ~3 min each)")

    def _generate(self):
        self._start([(self.difficulty.value(), self.year.value())])

    def _batch(self):
        import time
        diffs = []
        for tok in self.batch_edit.text().replace(";", ",").split(","):
            tok = tok.strip()
            try:
                diffs.append(float(tok))
            except ValueError:
                pass
        if not diffs:
            QMessageBox.warning(self, "Batch", "Enter difficulties like  3, 4, 5")
            return
        label = "d" + "/".join(f"{d:g}" for d in diffs)
        self._start([(d, self.year.value()) for d in diffs],
                    batch=(time.strftime("%Y%m%d-%H%M%S"), label))

    def _on_one_done(self, meta, parsed):
        self.parsed, self.run_meta = parsed, meta
        self.duration = meta.duration_sec
        self._reshape()

    def _on_all_done(self):
        self.progress.setVisible(False)
        self.gen_btn.setEnabled(True); self.batch_btn.setEnabled(True)
        self._refresh_history()
        self.status.showMessage("Done — saved to History.")

    # ---- history ----
    def _refresh_history(self):
        self.history.clear()
        self._runs = self.store.list_runs()
        for r in self._runs:
            self.history.addItem(r.label())

    def _load_history_item(self, item):
        r = self._runs[self.history.row(item)]
        self.run_meta = r
        self.parsed = parse_osu(self.store.osu_path(r.run_id))
        ab = self.store.audio_bytes(r)
        self.duration = r.duration_sec
        if ab:
            self._set_audio(ab, r.audio_filename)
        self._reshape()
        self.status.showMessage(f"Loaded {r.label()}")

    # ---- shaping (instant) ----
    def _params(self):
        return ShapeParams(
            slider_policy=self.policy.currentText(),
            include_spinners=self.spinners.isChecked(),
            min_spacing_ms=float(self.min_spacing.value()),
            accent_boost=self.accent.value() / 100.0,
            offset_ms=float(self.offset.value()),
        )

    def _reshape(self):
        if self.parsed is None:
            return
        bm = build_beatmap(self.parsed, audio_path=self.audio_name or "song",
                           shape_params=self._params(), duration_sec=self.duration)
        self.events = bm.events
        self._beatmap = bm
        self.wave.set_markers([(e.time_sec, e.strength) for e in bm.events])
        n, dur = len(bm.events), (self.duration or 1.0)
        self.metrics.setText(f"Hits {n}   ·   {n / dur:.2f}/s   ·   BPM {bm.analysis.bpm:.1f}   ·   {dur:.0f}s")
        m = self.run_meta
        if m:
            self.caption.setText(f"{m.audio_filename} — difficulty {m.difficulty} · year {m.year} · "
                                 f"seed {m.seed}" + (f" · batch {m.batch_label}" if m.batch_label else ""))

    # ---- preview (baked) ----
    def _build_preview(self):
        if self.parsed is None or not self.audio_bytes:
            QMessageBox.information(self, "Preview", "Generate or load a run first.")
            return
        from beatex.clicktrack import render_click_track
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status.showMessage("Rendering synced preview…")
        try:
            data = render_click_track(
                self.audio_bytes, [{"t": e.time_sec, "s": e.strength} for e in self.events],
                clicks_only=(self.prev_mode.currentText() == "clicks only"),
                song_gain=self.music_vol.value() / 100, click_gain=self.click_vol.value() / 100,
            )
            self.player.stop()
            self.player.setSource(QUrl())
            PREVIEW.write_bytes(data)
            self.player.setSource(QUrl.fromLocalFile(str(PREVIEW)))
            self.player.play()
        finally:
            QApplication.restoreOverrideCursor()
            self.status.showMessage("Playing synced preview.")

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_play_state(self, st):
        self.play_btn.setText("⏸ Pause" if st == QMediaPlayer.PlaybackState.PlayingState else "▶ Play")

    def _tick(self, ms):
        self.pos_slider.setValue(ms)
        self.time_lbl.setText(f"{ms / 1000:.1f}s")
        self.wave.set_position(ms / 1000.0)

    # ---- export ----
    def _save_json(self):
        if self.parsed is None:
            return
        default = (self.audio_name and Path(self.audio_name).stem or "beatmap") + ".beatmap.json"
        fn, _ = QFileDialog.getSaveFileName(self, "Save beatmap-v1 JSON", default, "JSON (*.json)")
        if fn:
            self._beatmap.save(fn)
            self.status.showMessage(f"Saved {fn}")

    def _save_mp3(self):
        if self.parsed is None or not self.audio_bytes:
            return
        from beatex.clicktrack import render_click_track
        default = (self.audio_name and Path(self.audio_name).stem or "beatmap") + "_clicktrack.mp3"
        fn, _ = QFileDialog.getSaveFileName(self, "Save click-track mp3", default, "mp3 (*.mp3)")
        if not fn:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data = render_click_track(
                self.audio_bytes, [{"t": e.time_sec, "s": e.strength} for e in self.events],
                clicks_only=(self.prev_mode.currentText() == "clicks only"),
                song_gain=self.music_vol.value() / 100, click_gain=self.click_vol.value() / 100)
            Path(fn).write_bytes(data)
        finally:
            QApplication.restoreOverrideCursor()
        self.status.showMessage(f"Saved {fn}")


def main():
    app = QApplication(sys.argv)
    win = BeatexWindow()
    win.show()
    if os.environ.get("BEATEX_SMOKE") == "1":  # headless launch check (CI/build)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(400, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
