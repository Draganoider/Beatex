// Waveform timeline: a full-song overview (waveform + hit density + viewport)
// and a zoomable detail view (waveform, strength-coloured hit markers, ruler,
// optional lanes for your taps and the other runs of the song).

import { fmtTime, strengthColor } from './ui.js';

const RULER_H = 20;
const WAVE_H = 150;
const LANE_H = 24;
const LABEL_W = 92;

/** Min/max peak pyramid of a decoded AudioBuffer (mono mix). */
export class Peaks {
  constructor(buffer) {
    this.sr = buffer.sampleRate;
    this.duration = buffer.duration;
    const a = buffer.getChannelData(0);
    const b = buffer.numberOfChannels > 1 ? buffer.getChannelData(1) : null;
    const B = 64;
    const n = Math.ceil(a.length / B);
    const mn = new Float32Array(n), mx = new Float32Array(n);
    for (let i = 0, j = 0; i < n; i++) {
      let lo = 1, hi = -1;
      const end = Math.min(a.length, j + B);
      if (b) {
        for (; j < end; j++) { const v = (a[j] + b[j]) * 0.5; if (v < lo) lo = v; if (v > hi) hi = v; }
      } else {
        for (; j < end; j++) { const v = a[j]; if (v < lo) lo = v; if (v > hi) hi = v; }
      }
      mn[i] = lo; mx[i] = hi;
    }
    this.levels = [{ block: B, mn, mx }];
    let prev = this.levels[0];
    while (prev.mn.length > 1500) {
      const m = Math.ceil(prev.mn.length / 8);
      const lo = new Float32Array(m), hi = new Float32Array(m);
      for (let i = 0; i < m; i++) {
        let l = 1, h = -1;
        const end = Math.min(prev.mn.length, i * 8 + 8);
        for (let k = i * 8; k < end; k++) { if (prev.mn[k] < l) l = prev.mn[k]; if (prev.mx[k] > h) h = prev.mx[k]; }
        lo[i] = l; hi[i] = h;
      }
      prev = { block: prev.block * 8, mn: lo, mx: hi };
      this.levels.push(prev);
    }
    let peak = 0;
    for (let i = 0; i < prev.mn.length; i++) peak = Math.max(peak, -prev.mn[i], prev.mx[i]);
    this.norm = peak > 0 ? 1 / peak : 1;
  }

  /** Per-pixel (lo, hi) in -1..1 (normalized) for [t0, t1] over w columns. */
  columns(t0, t1, w) {
    const lo = new Float32Array(w), hi = new Float32Array(w);
    const spp = ((t1 - t0) / w) * this.sr;
    let L = this.levels[0];
    for (const lv of this.levels) if (lv.block <= spp) L = lv;
    const per = this.sr / L.block, n = L.mn.length;
    const dt = (t1 - t0) / w;
    for (let x = 0; x < w; x++) {
      let i0 = Math.floor((t0 + x * dt) * per);
      let i1 = Math.floor((t0 + (x + 1) * dt) * per);
      if (i1 <= i0) i1 = i0 + 1;
      if (i0 >= n || i1 <= 0) continue;
      i0 = Math.max(0, i0); i1 = Math.min(n, i1);
      let l = 1, h = -1;
      for (let i = i0; i < i1; i++) { if (L.mn[i] < l) l = L.mn[i]; if (L.mx[i] > h) h = L.mx[i]; }
      lo[x] = l * this.norm; hi[x] = h * this.norm;
    }
    return { lo, hi };
  }
}

function niceStep(span, width) {
  const steps = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  for (const s of steps) if ((s / span) * width >= 74) return s;
  return 600;
}

function bsearch(events, t) {
  let lo = 0, hi = events.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (events[m].t < t) lo = m + 1; else hi = m; }
  return lo;
}

export class Timeline {
  constructor({ overview, detail, wrap, tooltip, onSeek, onFollowChange, onLaneClick }) {
    this.ov = overview;
    this.dt = detail;
    this.wrap = wrap;
    this.tip = tooltip;
    this.onSeek = onSeek;
    this.onFollowChange = onFollowChange;
    this.onLaneClick = onLaneClick;
    this.peaks = null;
    this.duration = 0;
    this.events = [];
    this.lanes = [];
    this.pos = 0;
    this.playing = false;
    this.start = 0;
    this.span = 12;
    this.follow = true;
    this.dirty = true;
    this.ovDirty = true;
    this.hoverX = null;
    this.density = null;
    this._ovCache = document.createElement('canvas');
    this._bind();
    this._sizeDetail();
    this.resize();
  }

  // ---- data
  setAudio(peaks, duration) {
    this.peaks = peaks;
    this.duration = duration || peaks?.duration || 0;
    this.span = Math.min(this.span, Math.max(2, this.duration));
    this._clampView();
    this.ovDirty = this.dirty = true;
  }

  setEvents(events) {
    this.events = events || [];
    // hits/second, smoothed — drawn as the density curve in the overview
    const n = Math.max(1, Math.ceil(this.duration || (this.events.at(-1)?.t ?? 1)));
    const raw = new Float32Array(n);
    for (const e of this.events) { const i = Math.floor(e.t); if (i >= 0 && i < n) raw[i]++; }
    const sm = new Float32Array(n);
    const K = [1, 2, 3, 2, 1], ks = 9;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let k = -2; k <= 2; k++) { const j = i + k; if (j >= 0 && j < n) s += raw[j] * K[k + 2]; }
      sm[i] = s / ks;
    }
    let max = 0;
    for (const v of sm) max = Math.max(max, v);
    this.density = { values: sm, max: max || 1 };
    this.ovDirty = this.dirty = true;
  }

  setLanes(lanes) {
    this.lanes = lanes || [];
    this._sizeDetail();
    this.dirty = true;
  }

  setPosition(pos, playing) {
    const changed = pos !== this.pos || playing !== this.playing;
    this.pos = pos;
    this.playing = playing;
    if (this.follow) {
      if (playing) {
        this.start = pos - this.span * 0.3;
        this._clampView();
      } else if (pos < this.start || pos > this.start + this.span) {
        this.start = pos - this.span * 0.3;
        this._clampView();
      }
    }
    if (changed) this.dirty = true;
  }

  setFollow(on) {
    this.follow = on;
    if (on) this.setPosition(this.pos, this.playing);
    this.dirty = true;
  }

  zoom(factor, anchorT = null) {
    if (!this.duration) return;
    const a = anchorT ?? (this.follow ? this.pos : this.start + this.span / 2);
    const k = (a - this.start) / this.span;
    this.span = Math.max(1.5, Math.min(Math.max(1.5, this.duration), this.span * factor));
    this.start = a - k * this.span;
    this._clampView();
    this.dirty = this.ovDirty = true;
  }

  _clampView() {
    const maxStart = Math.max(0, this.duration - this.span);
    this.start = Math.max(0, Math.min(maxStart, this.start));
  }

  // ---- layout
  _sizeDetail() {
    const h = RULER_H + WAVE_H + this.lanes.length * LANE_H + (this.lanes.length ? 4 : 0);
    if (this._dh !== h) {
      this._dh = h;
      this.dt.style.height = `${h}px`;
      this.resize();
    }
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    for (const c of [this.ov, this.dt]) {
      const r = c.getBoundingClientRect();
      const w = Math.max(10, Math.round(r.width * dpr)), h = Math.max(10, Math.round(r.height * dpr));
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    }
    this.dpr = dpr;
    this.ovDirty = this.dirty = true;
  }

  // ---- interaction
  _timeAtX(clientX, canvas = this.dt) {
    const r = canvas.getBoundingClientRect();
    const x = clientX - r.left;
    if (canvas === this.ov) return (x / r.width) * this.duration;
    return this.start + (x / r.width) * this.span;
  }

  _bind() {
    let drag = null;
    const dt = this.dt;
    dt.addEventListener('pointerdown', (e) => {
      if (!this.duration || e.button !== 0) return;
      dt.setPointerCapture(e.pointerId);
      drag = { x: e.clientX, y: e.clientY, start: this.start, moved: false };
    });
    dt.addEventListener('pointermove', (e) => {
      if (drag) {
        const dx = e.clientX - drag.x;
        if (!drag.moved && Math.abs(dx) > 3) {
          drag.moved = true;
          this.wrap.classList.add('grabbing');
          if (this.follow) { this.follow = false; this.onFollowChange?.(false); }
        }
        if (drag.moved) {
          const r = dt.getBoundingClientRect();
          this.start = drag.start - (dx / r.width) * this.span;
          this._clampView();
          this.dirty = this.ovDirty = true;
        }
      }
      this._hover(e);
    });
    const end = (e) => {
      if (!drag) return;
      const wasDrag = drag.moved;
      drag = null;
      this.wrap.classList.remove('grabbing');
      if (wasDrag) return;
      const r = dt.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const lane = this._laneAt(y);
      if (lane && x < LABEL_W && lane.kind === 'run') { this.onLaneClick?.(lane.id); return; }
      this.onSeek?.(this._timeAtX(e.clientX));
    };
    dt.addEventListener('pointerup', end);
    dt.addEventListener('pointercancel', () => { drag = null; this.wrap.classList.remove('grabbing'); });
    dt.addEventListener('pointerleave', () => { this.hoverX = null; this.tip.hidden = true; this.dirty = true; });
    dt.addEventListener('wheel', (e) => {
      if (!this.duration) return;
      e.preventDefault();
      const r = dt.getBoundingClientRect();
      if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        const d = e.shiftKey ? e.deltaY : e.deltaX;
        this.start += (d / r.width) * this.span;
        this._clampView();
        if (this.follow) { this.follow = false; this.onFollowChange?.(false); }
      } else {
        this.zoom(Math.exp(e.deltaY * 0.0016), this._timeAtX(e.clientX));
      }
      this.dirty = this.ovDirty = true;
    }, { passive: false });

    let ovDrag = false;
    const ovSeek = (e) => {
      const t = Math.max(0, Math.min(this.duration, this._timeAtX(e.clientX, this.ov)));
      this.start = t - this.span * 0.3;
      this._clampView();
      this.onSeek?.(t);
      this.dirty = this.ovDirty = true;
    };
    this.ov.addEventListener('pointerdown', (e) => {
      if (!this.duration) return;
      this.ov.setPointerCapture(e.pointerId);
      ovDrag = true;
      ovSeek(e);
    });
    this.ov.addEventListener('pointermove', (e) => { if (ovDrag) ovSeek(e); });
    this.ov.addEventListener('pointerup', () => { ovDrag = false; });
  }

  _laneAt(y) {
    const top = RULER_H + WAVE_H + 4;
    if (y < top) return null;
    return this.lanes[Math.floor((y - top) / LANE_H)] || null;
  }

  _hover(e) {
    const r = this.dt.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    this.hoverX = x;
    this.dirty = true;
    if (!this.duration) return;
    const t = this._timeAtX(e.clientX);
    const lane = this._laneAt(y);
    let html = `<b>${fmtTime(t, 2)}</b>`;
    if (lane) {
      html += lane.kind === 'run' && x < LABEL_W ? ` <span>· switch to ${lane.label}</span>` : ` <span>· ${lane.label}</span>`;
    } else {
      const pxT = (6 / r.width) * this.span;
      const i = bsearch(this.events, t - pxT);
      let best = null;
      for (let k = i; k < this.events.length && this.events[k].t <= t + pxT; k++) {
        if (!best || Math.abs(this.events[k].t - t) < Math.abs(best.t - t)) best = this.events[k];
      }
      if (best) html = `<b>${fmtTime(best.t, 3)}</b> <span>· ${best.src.replace('_', ' ')} · strength ${best.s.toFixed(2)}</span>`;
    }
    this.tip.innerHTML = html;
    this.tip.hidden = false;
    const tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(tw / 2 + 4, Math.min(r.width - tw / 2 - 4, x))}px`;
    this.tip.style.top = `${y > 60 ? y - 38 : y + 16}px`;
  }

  // ---- drawing
  render() {
    if (this.ovDirty) this._drawOverviewCache();
    if (this.dirty || this.ovDirty) {
      this._drawOverview();
      this._drawDetail();
    }
    this.dirty = this.ovDirty = false;
  }

  _drawOverviewCache() {
    const c = this._ovCache;
    c.width = this.ov.width; c.height = this.ov.height;
    const g = c.getContext('2d');
    const W = c.width, H = c.height;
    g.clearRect(0, 0, W, H);
    if (!this.duration) return;
    const mid = H / 2;
    if (this.peaks) {
      const { lo, hi } = this.peaks.columns(0, this.duration, W);
      g.fillStyle = 'rgba(150,175,205,0.28)';
      for (let x = 0; x < W; x++) {
        const y0 = mid - hi[x] * mid * 0.86, y1 = mid - lo[x] * mid * 0.86;
        g.fillRect(x, y0, 1, Math.max(1, y1 - y0));
      }
    }
    if (this.density && this.events.length) {
      const v = this.density.values, n = v.length, max = this.density.max;
      const grad = g.createLinearGradient(0, 0, W, 0);
      grad.addColorStop(0, 'rgba(43,214,198,0.40)');
      grad.addColorStop(1, 'rgba(255,180,84,0.40)');
      g.beginPath();
      g.moveTo(0, H);
      for (let i = 0; i < n; i++) g.lineTo(((i + 0.5) / this.duration) * W, H - (v[i] / max) * H * 0.82);
      g.lineTo(W, H);
      g.closePath();
      g.fillStyle = grad;
      g.fill();
      g.beginPath();
      for (let i = 0; i < n; i++) {
        const x = ((i + 0.5) / this.duration) * W, y = H - (v[i] / max) * H * 0.82;
        if (i) g.lineTo(x, y); else g.moveTo(x, y);
      }
      const sg = g.createLinearGradient(0, 0, W, 0);
      sg.addColorStop(0, 'rgba(43,214,198,0.95)');
      sg.addColorStop(1, 'rgba(255,180,84,0.95)');
      g.strokeStyle = sg;
      g.lineWidth = 1.5 * this.dpr;
      g.stroke();
    }
  }

  _drawOverview() {
    const c = this.ov, g = c.getContext('2d');
    const W = c.width, H = c.height, dpr = this.dpr;
    g.clearRect(0, 0, W, H);
    if (!this.duration) return;
    g.drawImage(this._ovCache, 0, 0);
    const x0 = (this.start / this.duration) * W, x1 = ((this.start + this.span) / this.duration) * W;
    g.fillStyle = 'rgba(255,255,255,0.07)';
    g.fillRect(x0, 0, Math.max(2, x1 - x0), H);
    g.strokeStyle = 'rgba(255,255,255,0.35)';
    g.lineWidth = dpr;
    g.strokeRect(x0 + 0.5, 0.5, Math.max(2, x1 - x0) - 1, H - 1);
    const px = (this.pos / this.duration) * W;
    g.fillStyle = '#fff';
    g.fillRect(px - dpr * 0.75, 0, dpr * 1.5, H);
  }

  _drawDetail() {
    const c = this.dt, g = c.getContext('2d');
    const dpr = this.dpr;
    const W = c.width / dpr, H = c.height / dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    if (!this.duration) return;
    const t0 = this.start, span = this.span, t1 = t0 + span;
    const X = (t) => ((t - t0) / span) * W;

    // ruler
    g.fillStyle = 'rgba(255,255,255,0.025)';
    g.fillRect(0, 0, W, RULER_H);
    const step = niceStep(span, W);
    g.font = '10.5px "Cascadia Code", Consolas, monospace';
    g.textBaseline = 'middle';
    for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
      const x = Math.round(X(t)) + 0.5;
      g.fillStyle = 'rgba(255,255,255,0.16)';
      g.fillRect(x, RULER_H - 6, 1, 6);
      g.fillStyle = 'rgba(255,255,255,0.05)';
      g.fillRect(x, RULER_H, 1, WAVE_H);
      g.fillStyle = 'rgba(200,215,230,0.55)';
      g.fillText(fmtTime(t, step < 1 ? (step < 0.1 ? 2 : 1) : 0), x + 4, RULER_H / 2);
    }

    // waveform
    const top = RULER_H, mid = top + WAVE_H / 2, amp = (WAVE_H / 2) * 0.9;
    if (this.peaks) {
      const cols = Math.max(1, Math.round(W));
      const { lo, hi } = this.peaks.columns(t0, t1, cols);
      const playedX = X(this.pos);
      for (let x = 0; x < cols; x++) {
        g.fillStyle = x < playedX ? 'rgba(120,205,215,0.55)' : 'rgba(140,165,195,0.30)';
        const y0 = mid - hi[x] * amp, y1 = mid - lo[x] * amp;
        g.fillRect(x, y0, 1, Math.max(1, y1 - y0));
      }
    }
    g.fillStyle = 'rgba(255,255,255,0.06)';
    g.fillRect(0, mid, W, 1);

    // hit markers (drawn from the bottom of the wave area; height = strength)
    const i0 = bsearch(this.events, t0 - 0.05);
    const visible = bsearch(this.events, t1 + 0.05) - i0;
    const dense = visible > W / 3;
    const lw = span < 5 ? 2.5 : span < 15 ? 2 : 1.25;
    const bottom = top + WAVE_H;
    for (let k = i0; k < this.events.length; k++) {
      const e = this.events[k];
      if (e.t > t1 + 0.05) break;
      const x = X(e.t);
      const h = (0.3 + 0.7 * e.s) * (WAVE_H - 10);
      g.fillStyle = strengthColor(e.s, dense ? 0.45 + 0.35 * e.s : 0.6 + 0.4 * e.s);
      g.fillRect(x - lw / 2, bottom - h, lw, h);
      if (e.s >= 0.8 && !dense) {
        g.beginPath();
        g.arc(x, bottom - h, lw + 1.5, 0, Math.PI * 2);
        g.fill();
      }
    }

    // lanes
    if (this.lanes.length) {
      let y = bottom + 4;
      g.fillStyle = 'rgba(255,255,255,0.08)';
      g.fillRect(0, bottom + 2, W, 1);
      for (const [li, lane] of this.lanes.entries()) {
        g.fillStyle = li % 2 ? 'rgba(255,255,255,0.018)' : 'rgba(255,255,255,0.035)';
        g.fillRect(0, y, W, LANE_H);
        const cy = y + LANE_H / 2;
        if (lane.kind === 'taps') {
          g.fillStyle = lane.live ? 'rgba(255,140,140,0.95)' : 'rgba(190,165,255,0.95)';
          const times = lane.times;
          for (let k = 0; k < times.length; k++) {
            const t = times[k];
            if (t < t0 - 0.1 || t > t1 + 0.1) continue;
            const x = X(t);
            g.beginPath();
            g.moveTo(x, cy - 5); g.lineTo(x + 4, cy); g.lineTo(x, cy + 5); g.lineTo(x - 4, cy);
            g.fill();
          }
        } else {
          const ev = lane.events || [];
          const j0 = bsearch(ev, t0 - 0.05);
          for (let k = j0; k < ev.length && ev[k].t <= t1 + 0.05; k++) {
            const e = ev[k];
            const hh = 6 + 9 * e.s;
            g.fillStyle = strengthColor(e.s, 0.75);
            g.fillRect(X(e.t) - 0.75, cy - hh / 2, 1.5, hh);
          }
        }
        // label pill
        g.font = '600 11px "Segoe UI Variable Text", "Segoe UI", sans-serif';
        const tw = Math.min(LABEL_W - 14, g.measureText(lane.label).width);
        g.fillStyle = 'rgba(8,12,18,0.85)';
        g.beginPath();
        g.roundRect(6, cy - 9, tw + 14, 18, 9);
        g.fill();
        g.fillStyle = lane.kind === 'taps' ? (lane.live ? '#ffb4b4' : '#cdbcff') : 'rgba(220,230,240,0.85)';
        g.fillText(lane.label, 13, cy + 0.5, LABEL_W - 14);
        y += LANE_H;
      }
    }

    // hover line
    if (this.hoverX != null) {
      g.fillStyle = 'rgba(255,255,255,0.18)';
      g.fillRect(Math.round(this.hoverX), RULER_H, 1, H - RULER_H);
    }

    // playhead
    const px = X(this.pos);
    if (px >= -2 && px <= W + 2) {
      g.fillStyle = 'rgba(255,255,255,0.18)';
      g.fillRect(px - 3, 0, 6, H);
      g.fillStyle = '#ffffff';
      g.fillRect(px - 0.75, 0, 1.5, H);
      g.beginPath();
      g.moveTo(px - 6, 0); g.lineTo(px + 6, 0); g.lineTo(px, 8);
      g.closePath();
      g.fill();
    }
  }
}
