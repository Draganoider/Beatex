// Rhythm-game preview: hits fly in from the right and land on the hit ring,
// bigger and warmer for stronger hits. A quick gut-check for how the map would
// feel in a game. Also the tap pad during tap-along.

import { strengthColor } from './ui.js';

const APPROACH = 1.5;   // seconds of upcoming hits visible
const TRAIL = 0.45;     // seconds a passed hit stays visible

function bsearch(events, t) {
  let lo = 0, hi = events.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (events[m].t < t) lo = m + 1; else hi = m; }
  return lo;
}

export class GameView {
  constructor(canvas) {
    this.c = canvas;
    this.g = canvas.getContext('2d');
    this.events = [];
    this.taps = [];
    this.recording = false;
    this.spec = new Uint8Array(256);
    this.lastDraw = 0;
    this.resize();
  }

  setEvents(events) { this.events = events || []; this.dirty = true; }
  setTaps(taps, recording) { this.taps = taps || []; this.recording = recording; this.dirty = true; }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.c.getBoundingClientRect();
    const w = Math.max(10, Math.round(r.width * dpr)), h = Math.max(10, Math.round(r.height * dpr));
    if (this.c.width !== w || this.c.height !== h) { this.c.width = w; this.c.height = h; }
    this.dpr = dpr;
    this.dirty = true;
  }

  /** Draw one frame. `spectrum(arr)` fills frequency bins (or returns null). */
  frame(pos, playing, spectrum) {
    const now = performance.now();
    if (!playing && !this.dirty && now - this.lastDraw > 600) return;
    if (playing || this.dirty) this.lastDraw = now;
    this.dirty = false;

    const g = this.g, dpr = this.dpr;
    const W = this.c.width / dpr, H = this.c.height / dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);

    const X0 = Math.max(70, W * 0.15);
    const cy = H * 0.5;
    const laneH = Math.min(84, H * 0.42);
    const ev = this.events;

    // most recent hit -> pulse
    const li = bsearch(ev, pos + 1e-4) - 1;
    const last = li >= 0 ? ev[li] : null;
    const since = last ? pos - last.t : 99;
    const pulse = last ? Math.exp(-since * 7) * (0.35 + 0.65 * last.s) : 0;

    // background: vignette + flash on strong hits
    const bg = g.createRadialGradient(X0, cy, 10, X0, cy, W * 0.9);
    bg.addColorStop(0, `rgba(43,214,198,${0.07 + pulse * 0.12})`);
    bg.addColorStop(1, 'rgba(5,8,12,0)');
    g.fillStyle = bg;
    g.fillRect(0, 0, W, H);

    // spectrum skyline
    const spec = playing && spectrum ? spectrum(this.spec) : null;
    if (spec) {
      const bars = 64, bw = W / bars;
      for (let i = 0; i < bars; i++) {
        const k = Math.floor(Math.pow(i / bars, 1.6) * 180) + 2;
        const v = spec[k] / 255;
        const h = v * v * H * 0.55;
        g.fillStyle = `rgba(${i < bars / 2 ? '43,214,198' : '255,180,84'},${0.05 + v * 0.1})`;
        g.fillRect(i * bw + 1, H - h, bw - 2, h);
      }
    }

    // lane
    const lg = g.createLinearGradient(0, 0, W, 0);
    lg.addColorStop(0, 'rgba(255,255,255,0.02)');
    lg.addColorStop(0.15, 'rgba(255,255,255,0.05)');
    lg.addColorStop(1, 'rgba(255,255,255,0.015)');
    g.fillStyle = lg;
    g.fillRect(0, cy - laneH / 2, W, laneH);
    g.fillStyle = 'rgba(255,255,255,0.07)';
    g.fillRect(0, cy - laneH / 2, W, 1);
    g.fillRect(0, cy + laneH / 2, W, 1);

    const pxPerSec = (W - X0) / APPROACH;
    const X = (t) => X0 + (t - pos) * pxPerSec;

    const iStart = bsearch(ev, pos - TRAIL);
    const iEnd = bsearch(ev, pos + APPROACH);

    // hit ring
    const ringR = 22 + pulse * 10;
    g.lineWidth = 2.5;
    g.strokeStyle = last ? strengthColor(last.s, 0.55 + pulse * 0.45) : 'rgba(255,255,255,0.25)';
    g.beginPath();
    g.arc(X0, cy, ringR, 0, Math.PI * 2);
    g.stroke();
    if (pulse > 0.01) {
      const glow = g.createRadialGradient(X0, cy, 0, X0, cy, ringR * 2.2);
      glow.addColorStop(0, strengthColor(last.s, pulse * 0.55));
      glow.addColorStop(1, strengthColor(last.s, 0));
      g.fillStyle = glow;
      g.beginPath();
      g.arc(X0, cy, ringR * 2.2, 0, Math.PI * 2);
      g.fill();
    }
    g.fillStyle = 'rgba(255,255,255,0.10)';
    g.fillRect(X0 - 1, cy - laneH / 2, 2, laneH);

    // passed hits: burst rings
    for (let i = iStart; i < iEnd && ev[i].t <= pos; i++) {
      const e = ev[i];
      const age = pos - e.t;
      const k = 1 - age / TRAIL;
      if (k <= 0) continue;
      g.strokeStyle = strengthColor(e.s, k * 0.8);
      g.lineWidth = 2;
      g.beginPath();
      g.arc(X0, cy, 14 + e.s * 8 + age * 90, 0, Math.PI * 2);
      g.stroke();
    }

    // incoming hits
    for (let i = iEnd - 1; i >= iStart; i--) {
      const e = ev[i];
      if (e.t < pos) break;
      const x = X(e.t);
      const r = 7 + 9 * e.s;
      const fade = Math.min(1, (W - x) / 60);
      g.fillStyle = strengthColor(e.s, 0.18 * fade);
      g.beginPath(); g.arc(x, cy, r + 6, 0, Math.PI * 2); g.fill();
      g.fillStyle = strengthColor(e.s, 0.95 * fade);
      g.beginPath(); g.arc(x, cy, r, 0, Math.PI * 2); g.fill();
      g.fillStyle = `rgba(255,255,255,${0.55 * fade})`;
      g.beginPath(); g.arc(x - r * 0.3, cy - r * 0.3, r * 0.35, 0, Math.PI * 2); g.fill();
    }

    // taps (tap-along): diamonds that drift left from the ring
    if (this.taps.length) {
      for (let k = this.taps.length - 1; k >= 0; k--) {
        const t = this.taps[k];
        const age = pos - t;
        if (age > 1.2) break;
        if (age < -0.05) continue;
        const x = X0 - age * pxPerSec * 0.6;
        const a = Math.max(0, 1 - age / 1.2);
        g.fillStyle = `rgba(205,188,255,${a})`;
        const yy = cy + laneH / 2 + 14;
        g.beginPath();
        g.moveTo(x, yy - 6); g.lineTo(x + 5, yy); g.lineTo(x, yy + 6); g.lineTo(x - 5, yy);
        g.fill();
        if (age < 0.25) {
          g.strokeStyle = `rgba(205,188,255,${(1 - age / 0.25) * 0.8})`;
          g.lineWidth = 2;
          g.beginPath(); g.arc(X0, cy, ringR + 6 + age * 60, 0, Math.PI * 2); g.stroke();
        }
      }
    }

    // HUD
    g.font = '700 11px "Segoe UI Variable Text", "Segoe UI", sans-serif';
    g.textBaseline = 'top';
    g.fillStyle = 'rgba(200,215,230,0.55)';
    const done = li + 1;
    g.fillText(this.recording ? 'TAPS' : 'HITS', 14, 12);
    let local = 0;
    for (let i = bsearch(ev, pos - 1); i < ev.length && ev[i].t <= pos + 1; i++) local++;
    g.textAlign = 'right';
    g.fillText('HITS / SEC', W - 14, 12);
    g.font = '650 22px "Segoe UI Variable Display", "Segoe UI", sans-serif';
    g.fillStyle = '#e8eef5';
    g.fillText((local / 2).toFixed(1), W - 14, 26);
    g.textAlign = 'left';
    g.fillText(this.recording ? String(this.taps.length) : `${done}`, 14, 26);
    if (!this.recording) {
      const w = g.measureText(`${done}`).width;
      g.font = '600 13px "Segoe UI Variable Text", "Segoe UI", sans-serif';
      g.fillStyle = 'rgba(200,215,230,0.45)';
      g.fillText(` / ${ev.length}`, 14 + w, 34);
    }

    if (!ev.length) {
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.font = '600 13px "Segoe UI Variable Text", "Segoe UI", sans-serif';
      g.fillStyle = 'rgba(200,215,230,0.5)';
      g.fillText('No hits to preview', W / 2, cy);
      g.textAlign = 'left';
    } else if (!playing && pos === 0 && !this.recording) {
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.font = '600 12.5px "Segoe UI Variable Text", "Segoe UI", sans-serif';
      g.fillStyle = 'rgba(200,215,230,0.55)';
      g.fillText('Press Space to play', (X0 + W) / 2, cy + laneH / 2 + 22);
      g.textAlign = 'left';
    }
  }
}
