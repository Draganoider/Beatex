"""Synthesize a royalty-free demo song to try Beatex with (no samples, no downloads).

Each preset is a short arranged track (intro, groove, break, build, drop, outro)
with drums, bass, pads, a lead melody and FX, so the model has percussive *and*
melodic moments to map.

    python tools/demo_track.py                       # -> data/demo/Beatex Demo - Neon Pulse.mp3
    python tools/demo_track.py --preset lanterns     # lo-fi, swung, 86 BPM
    python tools/demo_track.py --preset midnight -o song.wav

Needs numpy; writes .wav directly, or .mp3 through ffmpeg.
"""
from __future__ import annotations

import argparse
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
TAU = 2 * np.pi
ROOT = Path(__file__).resolve().parent.parent

PRESETS = {
    "neon": dict(title="Neon Pulse", bpm=124, key=57, scale="minor", prog=[0, -4, 3, -2],
                 swing=0.0, groove="house", seed=3),
    "midnight": dict(title="Midnight Run", bpm=140, key=50, scale="minor", prog=[0, 3, -2, -4],
                     swing=0.0, groove="breaks", seed=11),
    "lanterns": dict(title="Paper Lanterns", bpm=86, key=60, scale="major", prog=[0, -3, -7, -5],
                     swing=0.18, groove="lofi", seed=5),
}
SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11]}


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


class Mix:
    def __init__(self, seconds: float):
        self.buf = np.zeros((int(seconds * SR) + SR, 2), dtype=np.float64)

    def add(self, t: float, sig: np.ndarray, gain: float = 1.0, pan: float = 0.0):
        i = int(round(t * SR))
        if i >= len(self.buf) or i < 0:
            return
        sig = sig[: len(self.buf) - i]
        left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        if sig.ndim == 1:
            self.buf[i:i + len(sig), 0] += sig * gain * left * 1.414
            self.buf[i:i + len(sig), 1] += sig * gain * right * 1.414
        else:
            self.buf[i:i + len(sig)] += sig * gain


def tvec(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def env_adsr(n: int, a=0.005, d=0.1, s=0.7, r=0.08) -> np.ndarray:
    t = np.arange(n) / SR
    dur = n / SR
    e = np.where(t < a, t / max(a, 1e-6), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-6)))
    rel = np.clip((dur - t) / max(r, 1e-6), 0, 1)
    return e * rel


def highpass(x: np.ndarray, times: int = 1) -> np.ndarray:
    for _ in range(times):
        x = np.diff(x, prepend=0.0)
    return x


# ------------------------------------------------------------------ instruments
def kick(rng, punch=1.0):
    t = tvec(0.42)
    f0, f1, k = 150 * punch, 46, 32
    ph = TAU * (f1 * t + (f0 - f1) * (1 - np.exp(-k * t)) / k)
    click = rng.standard_normal(len(t)) * np.exp(-t * 400) * 0.25
    return (np.sin(ph) * np.exp(-t * 7.5) + click) * np.minimum(1, t * 3000)


def snare(rng, tone=190):
    t = tvec(0.28)
    noise = highpass(rng.standard_normal(len(t))) * 0.35 * np.exp(-t * 18)
    body = np.sin(TAU * tone * t) * np.exp(-t * 28) * 0.55
    return noise + body


def clap(rng):
    t = tvec(0.3)
    n = highpass(rng.standard_normal(len(t))) * 0.4
    e = np.zeros_like(t)
    for off in (0.0, 0.011, 0.022):
        e += np.where(t >= off, np.exp(-(t - off) * 140), 0) * 0.6
    e += np.where(t >= 0.03, np.exp(-(t - 0.03) * 16), 0) * 0.5
    return n * e


def hat(rng, open_=False):
    t = tvec(0.32 if open_ else 0.07)
    n = highpass(rng.standard_normal(len(t)), 2) * 0.22
    return n * np.exp(-t * (11 if open_ else 85))


def crash(rng):
    t = tvec(2.2)
    return highpass(rng.standard_normal(len(t)), 2) * 0.16 * np.exp(-t * 1.6)


def bass(f, dur, bright=6):
    t = tvec(dur)
    sig = sum(np.sin(TAU * f * k * t) / k for k in range(1, bright + 1))
    return sig * env_adsr(len(t), a=0.004, d=0.18, s=0.55, r=0.04) * 0.5


def pad(freqs, dur):
    t = tvec(dur)
    out = np.zeros((len(t), 2))
    for f in freqs:
        for ch, det in ((0, -0.006), (1, 0.006)):
            ff = f * (1 + det)
            out[:, ch] += sum(np.sin(TAU * ff * k * t + k) / (k * 1.6) for k in range(1, 7))
    e = env_adsr(len(t), a=0.35, d=0.8, s=0.8, r=0.5)
    return out * e[:, None] * 0.07


def lead(f, dur, vib=True):
    t = tvec(dur)
    vibrato = 1 + (0.004 * np.sin(TAU * 5.5 * t) * np.clip(t * 3, 0, 1) if vib else 0)
    ph = TAU * f * np.cumsum(vibrato) / SR
    sig = sum(np.sin(ph * k) / k for k in (1, 3, 5, 7, 9)) * 0.8 + np.sin(ph * 2) * 0.25
    return sig * env_adsr(len(t), a=0.012, d=0.25, s=0.6, r=0.06) * 0.22


def pluck(f, dur=0.35):
    t = tvec(dur)
    return sum(np.sin(TAU * f * k * t) * np.exp(-t * (6 + 5 * k)) / k for k in range(1, 6)) * 0.22


def riser(rng, dur):
    t = tvec(dur)
    n = highpass(rng.standard_normal(len(t))) * 0.12
    sweep = np.sin(TAU * np.cumsum(220 + 1800 * (t / dur) ** 2) / SR) * 0.06
    return (n + sweep) * (t / dur) ** 2


# ------------------------------------------------------------------ arrangement
def make_track(preset: dict) -> np.ndarray:
    rng = np.random.default_rng(preset["seed"])
    bpm, key = preset["bpm"], preset["key"]
    beat = 60.0 / bpm
    bar = beat * 4
    s16 = beat / 4
    scale = SCALES[preset["scale"]]
    groove = preset["groove"]
    # bars: intro 4, groove 8, break 4, build 2, drop 10, outro 4
    sections = [("intro", 4), ("groove", 8), ("break", 4), ("build", 2), ("drop", 10), ("outro", 4)]
    total_bars = sum(n for _, n in sections)
    mix = Mix(total_bars * bar + 3)

    def swing(step):  # 16th-step -> seconds, with swing on odd 8ths
        sw = preset["swing"] * s16 if step % 4 == 2 else 0.0
        return step * s16 + sw

    def chord(i):
        root = key - 12 + preset["prog"][i % len(preset["prog"])]
        q = 3 if preset["scale"] == "minor" and preset["prog"][i % 4] in (0,) else 4
        return root, [hz(root + 12), hz(root + 12 + q), hz(root + 19)]

    # melody: a 4-bar phrase on the scale, rhythm from a template, reused with variation
    rhythm = [0, 3, 6, 8, 10, 12, 14] if groove != "lofi" else [0, 4, 6, 10, 12]
    degrees = rng.integers(0, 7, size=64)
    for i in range(1, 64):  # mostly stepwise
        degrees[i] = np.clip(degrees[i - 1] + rng.choice([-2, -1, -1, 0, 1, 1, 2]), 0, 9)

    def mel_note(idx):
        d = int(degrees[idx % 64])
        return key + 12 + 12 * (d // 7) + scale[d % 7]

    b0 = 0
    for name, nbars in sections:
        for b in range(nbars):
            t0 = (b0 + b) * bar
            root, ch = chord(b0 + b)
            last = b == nbars - 1
            # pads everywhere except the drop's first bar (it hits harder without)
            if name != "build":
                mix.add(t0, pad(ch, bar + 0.4), 1.0 if name in ("intro", "break", "outro") else 0.7)
            # drums
            if name in ("groove", "drop") or (name == "outro" and b < 2):
                for step in range(16):
                    t = t0 + swing(step)
                    if groove == "house":
                        if step % 4 == 0:
                            mix.add(t, kick(rng), 0.9)
                        if step in (4, 12):
                            mix.add(t, clap(rng), 0.7, pan=0.05)
                    elif groove == "breaks":
                        if step in (0, 6, 10):
                            mix.add(t, kick(rng, 1.1), 0.9)
                        if step in (4, 12):
                            mix.add(t, snare(rng, 200), 0.8)
                        if step == 15 and b % 2:
                            mix.add(t, snare(rng, 230), 0.35)
                    else:  # lofi
                        if step in (0, 7, 10):
                            mix.add(t, kick(rng, 0.8), 0.75)
                        if step in (4, 12):
                            mix.add(t, snare(rng, 170), 0.55)
                    hats_every = 1 if (name == "drop" and groove != "lofi") else 2
                    if step % hats_every == 0:
                        mix.add(t, hat(rng), 0.55 if step % 4 else 0.3, pan=0.3)
                    if groove == "house" and step % 4 == 2:
                        mix.add(t, hat(rng, open_=True), 0.35, pan=-0.25)
            elif name == "intro" and b >= 2:
                for step in range(0, 16, 2):
                    mix.add(t0 + swing(step), hat(rng), 0.35, pan=0.3)
            elif name == "build":
                n = 8 if b == 0 else 16
                for k in range(n):
                    vel = 0.25 + 0.6 * ((b * n + k) / (2 * n))
                    mix.add(t0 + k * bar / n, snare(rng, 210), vel)
                mix.add(t0, kick(rng), 0.6)
                if b == 0:
                    mix.add(t0, riser(rng, 2 * bar), 1.0)
            # bass
            if name in ("groove", "drop"):
                pattern = [0, 3, 6, 8, 11, 14] if groove != "lofi" else [0, 6, 8, 14]
                for step in pattern:
                    note = root + (12 if step in (6, 14) and groove == "house" else 0)
                    mix.add(t0 + swing(step), bass(hz(note), s16 * 2.2, 7 if name == "drop" else 5), 0.85)
            # lead melody: break + drop (+ outro echo)
            if name in ("break", "drop") or (name == "outro" and b < 2):
                for j, step in enumerate(rhythm):
                    nxt = rhythm[j + 1] if j + 1 < len(rhythm) else 16
                    dur = (nxt - step) * s16 * 0.92
                    m = mel_note(((b0 + b) % 4) * len(rhythm) + j)
                    sig = lead(hz(m), dur)
                    mix.add(t0 + swing(step), sig, 1.0)
                    mix.add(t0 + swing(step) + beat * 0.75, sig, 0.28, pan=0.6)  # echo
            # pluck arpeggio in intro/groove
            if name in ("intro", "groove"):
                for k, step in enumerate(range(0, 16, 2)):
                    f = ch[k % 3] * (2 if k % 4 == 3 else 1)
                    mix.add(t0 + swing(step), pluck(f), 0.55, pan=-0.35 if k % 2 else 0.35)
            if name == "drop" and b == 0:
                mix.add(t0, crash(rng), 0.9)
            if last and name == "groove":
                mix.add(t0 + 3 * beat, crash(rng) * 0.5, 0.6)
        b0 += nbars

    x = mix.buf
    x = np.tanh(x * 1.1)
    x /= max(1e-9, np.abs(x).max()) / 0.89
    fade = int(1.5 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return x


def write(x: np.ndarray, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    wav = out if out.suffix.lower() == ".wav" else out.with_suffix(".tmp.wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    if wav != out:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "192k", str(out)], check=True)
        wav.unlink()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", choices=sorted(PRESETS), default="neon")
    ap.add_argument("-o", "--out", default=None, help="Output .mp3 or .wav (default: data/demo/...).")
    args = ap.parse_args(argv)
    p = PRESETS[args.preset]
    out = Path(args.out) if args.out else ROOT / "data" / "demo" / f"Beatex Demo - {p['title']}.mp3"
    x = make_track(p)
    write(x, out)
    print(f"Wrote {out}  ({len(x) / SR:.0f}s, {p['bpm']} BPM)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
