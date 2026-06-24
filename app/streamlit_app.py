"""Beatex Streamlit UI — generate once (model), shape instantly (no model).

Run:  streamlit run app/streamlit_app.py

Playback: the preview is the song with clicks *baked in* (one stream → no drift).
History lives in a sortable, multi-select table in the main area; batch runs are
tagged so they group together.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
for p in (str(ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from beatex.osu_parse import parse_osu  # noqa: E402
from beatex.pipeline import build_beatmap, extract  # noqa: E402
from beatex.shape import ShapeParams  # noqa: E402
from beatex.store import RunStore  # noqa: E402
from waveform import waveform_html  # noqa: E402

st.set_page_config(page_title="Beatex", layout="wide")
st.title("🎵 Beatex — felt-beat extractor")

store = RunStore(ROOT / "data" / "runs")
RUN_DIR = ROOT / "data" / "ui-runs"

ss = st.session_state
for k, v in dict(parsed=None, audio_bytes=None, audio_name=None, duration=0.0,
                 run_meta=None, preview_bytes=None, preview_key=None, preview_name=None).items():
    ss.setdefault(k, v)

if ss.get("flash"):
    st.success(ss.pop("flash"))

DEFAULT_SONG = ""  # no personal default — upload a file or type a path
DIFF_OPTS = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0]
YEAR_OPTS = [2010, 2012, 2014, 2016, 2018, 2020, 2021, 2022, 2024]


def _load_audio():
    if upload is not None:
        return upload.getvalue(), upload.name
    p = Path(path)
    if p.exists():
        return p.read_bytes(), p.name
    return None, None


def _set_loaded(parsed, audio_bytes, name, duration, meta):
    ss.parsed, ss.audio_bytes, ss.audio_name = parsed, audio_bytes, name
    ss.duration, ss.run_meta = duration, meta
    ss.preview_bytes, ss.preview_key = None, None  # stale: force rebuild


def _run_one(audio_file, name, audio_bytes, *, difficulty, year,
             batch_id=None, batch_label=None, on_log=None):
    bm, parsed, osu = extract(
        audio_file, difficulty=difficulty, year=year, gamemode=0,
        cfg_scale=(cfg_scale if cfg_scale != 1.0 else None),
        super_timing=super_timing, seed=int(seed),
        output_dir=RUN_DIR / "osu", on_log=on_log,
    )
    meta = store.save_run(
        audio_bytes=audio_bytes, audio_filename=name,
        audio_sha256=bm.source.sha256, audio_ext=Path(name).suffix.lower(),
        duration_sec=bm.source.duration_sec,
        difficulty=difficulty, year=year, gamemode=0,
        cfg_scale=(cfg_scale if cfg_scale != 1.0 else None),
        super_timing=super_timing, seed=int(seed),
        n_objects=len(parsed.objects), bpm=parsed.bpm, meter=parsed.meter,
        osu_path=osu, batch_id=batch_id, batch_label=batch_label,
    )
    return meta, parsed


# ============================== Sidebar (controls) ==============================
with st.sidebar:
    st.header("1 · Song")
    upload = st.file_uploader("Upload audio", type=["mp3", "wav", "ogg", "m4a", "flac"])
    path = st.text_input("…or local path", value=DEFAULT_SONG,
                         placeholder="e.g. C:/Music/song.mp3")

    st.header("2 · Model — slow, needs Generate")
    difficulty = st.slider("Difficulty (star rating)", 1.0, 8.0, 4.0, 0.5,
                           help="Lower = sparser, more 'felt'; higher = denser / streams.")
    year = st.slider("Style year", 2007, 2024, 2021)
    cfg_scale = st.slider("CFG scale", 1.0, 8.0, 1.0, 0.5, help="Higher = follow style cues harder.")
    super_timing = st.checkbox("Super timing (slow, accurate variable BPM)", value=False)
    seed = st.number_input("Seed", value=7, step=1)
    generate = st.button("⚡ Generate beatmap", type="primary", use_container_width=True)

    with st.expander("🧪 Batch — sweep several runs"):
        batch_diffs = st.multiselect("Difficulties", DIFF_OPTS, default=[3.0, 4.0, 5.0])
        batch_years = st.multiselect("Years (empty = use slider year)", YEAR_OPTS, default=[])
        _years = batch_years or [year]
        n_combos = len(batch_diffs) * len(_years)
        run_batch = st.button(f"⚡ Run {n_combos} run(s)  ·  ~{n_combos * 3} min",
                              disabled=n_combos == 0, use_container_width=True)

    st.header("3 · Shape — instant")
    slider_policy = st.radio("Sliders", ["head_tail", "head"], horizontal=True,
                             help="head_tail also marks the slider release.")
    include_spinners = st.checkbox("Include spinners", value=False)
    min_spacing = st.slider("Min spacing (ms)", 0, 500, 0, 10, help="Thins density.")
    accent_boost = st.slider("Accent boost", 0.0, 0.5, 0.30, 0.05)
    offset_ms = st.slider("Timing offset (ms)", -150, 150, 0, 5,
                          help="Shift ALL hits earlier (−) / later (+). Baked into export.")


# ============================== Runs browser (main) ==============================
runs = store.list_runs()
do_load = do_delete = False
sel_ids: list[str] = []

with st.expander(f"📚 Runs ({len(runs)})", expanded=(ss.parsed is None)):
    if not runs:
        st.caption("No runs yet — **Generate** one from the sidebar, or **Batch** a sweep.")
    else:
        songs = sorted({r.audio_filename for r in runs})
        fcol, _ = st.columns([2, 3])
        song_filter = fcol.selectbox("Filter by song", ["All songs"] + songs)
        filtered = [r for r in runs if song_filter == "All songs" or r.audio_filename == song_filter]
        view_ids = [r.run_id for r in filtered]
        view_df = pd.DataFrame([{
            "When": r.created_at, "Song": r.audio_filename, "Diff": r.difficulty, "Year": r.year,
            "Seed": r.seed, "Objects": r.n_objects, "BPM": round(r.bpm, 1),
            "Batch": r.batch_label or "—",
        } for r in filtered])

        event = st.dataframe(
            view_df, key="runs_table", on_select="rerun", selection_mode="multi-row",
            use_container_width=True, hide_index=True,
            height=min(380, 60 + 35 * len(view_df)),
            column_config={"Diff": st.column_config.NumberColumn(format="%.1f")},
        )
        sel = list(event.selection.rows)
        sel_ids = [view_ids[i] for i in sel if i < len(view_ids)]

        st.caption("Click rows to select · sort by any column header.")
        b1, b2, _ = st.columns([1, 1, 4])
        do_load = b1.button("📂 Load", disabled=len(sel_ids) != 1, use_container_width=True,
                            help="Select exactly one run to load.")
        do_delete = b2.button("🗑 Delete", disabled=not sel_ids, use_container_width=True)


# ============================== Action handlers ==============================
if do_delete and sel_ids:
    for rid in sel_ids:
        store.delete(rid)
    if ss.run_meta and ss.run_meta.run_id in sel_ids:
        ss.parsed, ss.run_meta, ss.preview_bytes = None, None, None
    st.rerun()

if do_load and len(sel_ids) == 1:
    meta = store.get(sel_ids[0])
    if meta:
        _set_loaded(parse_osu(store.osu_path(meta.run_id)), store.audio_bytes(meta),
                    meta.audio_filename, meta.duration_sec, meta)
    st.rerun()

if generate:
    audio_bytes, name = _load_audio()
    if not audio_bytes:
        st.error("No audio — upload a file or enter a valid local path.")
    else:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        audio_file = RUN_DIR / name
        audio_file.write_bytes(audio_bytes)
        log_box, logs = st.empty(), []
        with st.status("Running Mapperatorinator V32…", expanded=True) as status:
            try:
                meta, parsed = _run_one(audio_file, name, audio_bytes, difficulty=difficulty, year=year,
                                        on_log=lambda l: (logs.append(l), log_box.code("\n".join(logs[-12:]))))
                _set_loaded(parsed, audio_bytes, name, meta.duration_sec, meta)
                ss.flash = "Generated — saved to Runs."
                status.update(label="Done", state="complete")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                status.update(label="Failed", state="error")
                st.exception(exc)

if run_batch:
    audio_bytes, name = _load_audio()
    combos = [(d, y) for y in (batch_years or [year]) for d in batch_diffs]
    if not audio_bytes:
        st.error("No audio — upload a file or enter a valid local path.")
    elif not combos:
        st.error("Pick at least one difficulty for the batch.")
    else:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        audio_file = RUN_DIR / name
        audio_file.write_bytes(audio_bytes)
        batch_id = time.strftime("%Y%m%d-%H%M%S")
        batch_label = "d" + "/".join(f"{d:g}" for d in batch_diffs)
        prog, live = st.progress(0.0, text=f"Batch: 0/{len(combos)}"), st.empty()
        ok, last = 0, None
        for i, (d, y) in enumerate(combos):
            prog.progress(i / len(combos), text=f"Run {i + 1}/{len(combos)} — difficulty {d}, year {y}")
            try:
                meta, parsed = _run_one(audio_file, name, audio_bytes, difficulty=d, year=y,
                                        batch_id=batch_id, batch_label=batch_label,
                                        on_log=lambda l: live.caption(l))
                ok += 1
                last = (parsed, meta)
            except Exception as exc:  # noqa: BLE001
                live.warning(f"difficulty {d}, year {y} failed: {exc}")
        if last:
            parsed, meta = last
            _set_loaded(parsed, audio_bytes, name, meta.duration_sec, meta)
        ss.flash = f"Batch '{batch_label}' complete — {ok}/{len(combos)} runs saved to Runs."
        st.rerun()


# ============================== Workbench (loaded map) ==============================
if ss.parsed is None:
    st.info("Pick a song and settings, then **Generate** (or **Batch** a sweep) from the sidebar, "
            "or select a past run in **Runs** above. Shaping then updates instantly.")
else:
    m = ss.run_meta
    if m:
        st.caption(
            f"📄 **{m.audio_filename}** — {m.created_at} · difficulty {m.difficulty} · year {m.year} · "
            f"seed {m.seed}" + (f" · cfg {m.cfg_scale}" if m.cfg_scale else "")
            + (" · super_timing" if m.super_timing else "")
            + (f" · batch {m.batch_label}" if m.batch_label else "")
            + f" · {m.n_objects} raw objects · {m.bpm:.1f} BPM"
        )

    params = ShapeParams(
        slider_policy=slider_policy, include_spinners=include_spinners,
        min_spacing_ms=float(min_spacing), accent_boost=accent_boost, offset_ms=float(offset_ms),
    )
    bm = build_beatmap(ss.parsed, audio_path=ss.audio_name or "song",
                       shape_params=params, duration_sec=ss.duration)
    n, dur = len(bm.events), (ss.duration or 1.0)
    events = [{"t": e.time_sec, "s": e.strength} for e in bm.events]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hits", n)
    c2.metric("Density", f"{n / dur:.2f}/s")
    c3.metric("BPM", f"{bm.analysis.bpm:.1f}")
    c4.metric("Duration", f"{dur:.0f}s")

    st.subheader("Synced preview")
    preview_mode = st.segmented_control(
        "Preview mode", ["song + clicks", "clicks only"],
        default="song + clicks", label_visibility="collapsed") or "song + clicks"
    v1, v2 = st.columns(2)
    music_vol = v1.slider("🎵 Music volume", 0, 100, 70, 5,
                          help="Song level baked into the preview/export.",
                          disabled=(preview_mode == "clicks only"))
    click_vol = v2.slider("🔔 Click volume", 0, 150, 90, 5,
                          help="Click level baked in (can exceed 100% to cut through loud songs).")
    bcol, _ = st.columns([1, 2])
    build = bcol.button("🎧 Build synced preview", type="primary",
                        use_container_width=True, disabled=ss.audio_bytes is None)

    sig = (slider_policy, include_spinners, float(min_spacing), accent_boost, float(offset_ms))
    current_key = (m.run_id if m else "loaded", sig, preview_mode, music_vol, click_vol)

    if build and ss.audio_bytes is not None:
        with st.spinner("Rendering synced preview (clicks baked in)…"):
            from beatex.clicktrack import render_click_track
            ss.preview_bytes = render_click_track(
                ss.audio_bytes, events, clicks_only=(preview_mode == "clicks only"),
                song_gain=music_vol / 100, click_gain=click_vol / 100,
            )
            ss.preview_key = current_key
            tag = "_clicksonly" if preview_mode == "clicks only" else "_clicktrack"
            ss.preview_name = Path(ss.audio_name).stem + tag + ".mp3"

    fresh = ss.preview_bytes is not None and ss.preview_key == current_key
    if fresh:
        components.html(waveform_html(ss.preview_bytes, "preview.mp3", events, height=180), height=270)
    elif ss.audio_bytes is None:
        st.caption("(No cached audio for this run — preview unavailable.)")
    else:
        note = "Click **Build synced preview** to hear the song with clicks baked in (always in sync)."
        if ss.preview_bytes is not None:
            note += "  ·  *Settings changed — rebuild to refresh.*"
        st.info(note)

    st.subheader("Density over time")
    bucket, counts = 2, {}
    for e in bm.events:
        b = int(e.time_sec // bucket) * bucket
        counts[b] = counts.get(b, 0) + 1
    if counts:
        df = (pd.DataFrame({"sec": list(counts), "hits": list(counts.values())})
              .sort_values("sec").set_index("sec"))
        st.bar_chart(df, height=160)

    st.subheader("Export")
    x1, x2 = st.columns(2)
    with x1:
        st.download_button("⬇ beatmap-v1 JSON", data=bm.to_json(),
                           file_name=Path(ss.audio_name).stem + ".beatmap.json",
                           mime="application/json", type="primary", use_container_width=True)
    with x2:
        if fresh:
            label = "clicks-only" if preview_mode == "clicks only" else "click-track"
            st.download_button(f"⬇ {label} mp3", data=ss.preview_bytes, file_name=ss.preview_name,
                               mime="audio/mpeg", use_container_width=True)
        else:
            st.caption("Build a synced preview to download its mp3.")

    with st.expander("First 40 events"):
        st.dataframe(
            [{"id": e.id, "time_sec": e.time_sec, "source": e.source, "strength": e.strength}
             for e in bm.events[:40]],
            use_container_width=True, hide_index=True,
        )
