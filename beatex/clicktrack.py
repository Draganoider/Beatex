"""Render an audible click-track (clicks baked into the song) to audio bytes.

Ground-truth alignment check with no browser latency in the loop. Optional
feature — needs numpy + pydub (the [app]/[tools] extras), so it's a standalone
module, never imported by the stdlib-only core.

    render_click_track(audio_bytes, events) -> bytes   # an mp3 by default
"""
from __future__ import annotations

import io

import numpy as np
from pydub import AudioSegment

FR = 44100  # working sample rate


def _click(freq: float, dur: float = 0.030, decay: float = 180.0, amp: float = 0.9) -> np.ndarray:
    t = np.arange(int(dur * FR)) / FR
    return (np.sin(2 * np.pi * freq * t) * np.exp(-t * decay) * amp).astype(np.float32)


def render_click_track(audio_bytes: bytes, events, *, fmt: str = "mp3",
                       clicks_only: bool = False, song_gain: float = 0.70,
                       click_gain: float = 0.90) -> bytes:
    """events: iterable of {"t": seconds, "s": strength 0-1}. Returns audio bytes."""
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes)).set_frame_rate(FR).set_channels(2)
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32).reshape((-1, 2))
    full_scale = float(1 << (8 * seg.sample_width - 1))
    song = samples / full_scale
    n = song.shape[0]

    clicks = np.zeros((n, 2), dtype=np.float32)
    lo, hi = _click(1500.0), _click(2300.0, amp=1.0)
    for e in events:
        s = float(e.get("s", 0.5))
        c = hi if s >= 0.8 else lo
        idx = int(round(float(e["t"]) * FR))
        if 0 <= idx < n:
            end = min(idx + len(c), n)
            clicks[idx:end, 0] += c[: end - idx]
            clicks[idx:end, 1] += c[: end - idx]

    mix = clicks * click_gain if clicks_only else song * song_gain + clicks * click_gain
    out = (np.clip(mix, -1.0, 1.0) * 32767.0).astype(np.int16)
    res = AudioSegment(out.tobytes(), frame_rate=FR, sample_width=2, channels=2)
    buf = io.BytesIO()
    res.export(buf, format=fmt)
    return buf.getvalue()
