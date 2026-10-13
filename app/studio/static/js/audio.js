// Web Audio playback engine. The song and every click run on ONE AudioContext
// clock, so clicks are sample-accurate and stay in sync at any speed. Unlike the
// old baked-mp3 preview, shaping changes apply live while the song plays.

const LOOKAHEAD = 0.2;   // seconds of clicks scheduled ahead of the audio clock
const TICK_MS = 25;

// A worker-driven tick keeps clicks scheduled even when the window is in the
// background (page timers are throttled there; worker timers much less so).
function makeTicker(fn) {
  try {
    const src = `let t=null;onmessage=e=>{clearInterval(t);if(e.data>0)t=setInterval(()=>postMessage(0),e.data)}`;
    const w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
    w.onmessage = fn;
    return { start: () => w.postMessage(TICK_MS), stop: () => w.postMessage(0) };
  } catch {
    let t = null;
    return { start: () => { clearInterval(t); t = setInterval(fn, TICK_MS); }, stop: () => clearInterval(t) };
  }
}

function lowerBound(events, t) {
  let lo = 0, hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (events[mid].t < t) lo = mid + 1; else hi = mid;
  }
  return lo;
}

function buildSounds(ctx) {
  const TAU = Math.PI * 2;
  const sr = ctx.sampleRate;
  let seed = 12345;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 2 - 1;
  const mk = (dur, fn) => {
    const n = Math.ceil(sr * dur);
    const b = ctx.createBuffer(1, n, sr);
    const d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = fn(i / sr);
    for (let i = 0; i < 48 && i < n; i++) d[n - 1 - i] *= i / 48; // soft tail
    return b;
  };
  const kick = (f0, decay, amp) => {
    const f1 = 46, k = 30;
    return (t) => Math.sin(TAU * (f1 * t + ((f0 - f1) * (1 - Math.exp(-k * t))) / k)) * Math.exp(-t * decay) * amp * Math.min(1, t * 1500);
  };
  return {
    // Same tones as the exported click-track mp3 (beatex/clicktrack.py).
    beep: [mk(0.04, (t) => Math.sin(TAU * 1500 * t) * Math.exp(-t * 180) * 0.9),
           mk(0.04, (t) => Math.sin(TAU * 2300 * t) * Math.exp(-t * 180))],
    tick: [mk(0.03, (t) => (rnd() * 0.45 + Math.sin(TAU * 3900 * t) * 0.6) * Math.exp(-t * 360) * 0.9),
           mk(0.035, (t) => (rnd() * 0.5 + Math.sin(TAU * 5200 * t) * 0.7) * Math.exp(-t * 280))],
    wood: [mk(0.09, (t) => (Math.sin(TAU * 880 * t) + 0.4 * Math.sin(TAU * 2390 * t) * Math.exp(-t * 60)) * Math.exp(-t * 75) * 0.7),
           mk(0.09, (t) => (Math.sin(TAU * 1180 * t) + 0.4 * Math.sin(TAU * 3120 * t) * Math.exp(-t * 60)) * Math.exp(-t * 70) * 0.8)],
    kick: [mk(0.18, kick(130, 20, 0.95)), mk(0.2, kick(170, 15, 1.0))],
  };
}

export class AudioEngine extends EventTarget {
  constructor() {
    super();
    this.ctx = null;
    this.buffer = null;
    this.src = null;
    this.playing = false;
    this.rate = 1;
    this.startCtx = 0;       // context time at which startPos is played
    this.startPos = 0;
    this.pausedPos = 0;
    this.events = [];
    this.clicksOn = true;
    this.muteClicks = false; // tap-along mode
    this.sound = 'beep';
    this.musicVol = 0.8;
    this.clickVol = 0.9;
    this.nextIdx = 0;
    this.scheduled = [];
    this._lastVis = null;
    this.ticker = makeTicker(() => this._schedule());
  }

  _ensure() {
    if (this.ctx) return this.ctx;
    const ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'interactive' });
    this.ctx = ctx;
    this.pre = ctx.createGain();
    this.musicGain = ctx.createGain();
    this.clickGain = ctx.createGain();
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.analyser.smoothingTimeConstant = 0.8;
    const limiter = ctx.createDynamicsCompressor();  // only catches song+click peaks
    limiter.threshold.value = -2;
    limiter.knee.value = 2;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.002;
    limiter.release.value = 0.12;
    this.pre.connect(this.musicGain);
    this.pre.connect(this.analyser);
    this.musicGain.connect(limiter);
    this.clickGain.connect(limiter);
    limiter.connect(ctx.destination);
    this.sounds = buildSounds(ctx);
    this._applyVolumes();
    return ctx;
  }

  _emit(type) { this.dispatchEvent(new Event(type)); }

  /** Decode without touching playback (the caller decides whether it's still wanted). */
  decode(arrayBuffer) { return this._ensure().decodeAudioData(arrayBuffer); }

  setBuffer(buffer) {
    this.stop();
    this.buffer = buffer;
    this.pausedPos = 0;
    this._emit('state');
  }

  clear() { this.stop(); this.buffer = null; this.pausedPos = 0; }

  get duration() { return this.buffer ? this.buffer.duration : 0; }

  _posAt(ctxTime) { return this.startPos + (ctxTime - this.startCtx) * this.rate; }

  /** Context time of the sample reaching the speakers at performance time `perfNow`. */
  heardCtxTime(perfNow = performance.now()) {
    const c = this.ctx;
    if (c.getOutputTimestamp) {
      const ts = c.getOutputTimestamp();
      if (ts.contextTime > 0 && ts.performanceTime > 0) {
        const t = ts.contextTime + (perfNow - ts.performanceTime) / 1000;
        if (Math.abs(t - c.currentTime) < 0.5) return t;
      }
    }
    return c.currentTime - (c.outputLatency || c.baseLatency || 0) - (performance.now() - perfNow) / 1000;
  }

  /** Song position you are hearing right now (latency-compensated) — for visuals. */
  position() {
    if (!this.playing || !this.ctx) return this.pausedPos;
    let p = Math.max(0, Math.min(this.duration, this._posAt(this.heardCtxTime())));
    if (this._lastVis != null && p < this._lastVis && this._lastVis - p < 0.05) p = this._lastVis;
    this._lastVis = p;
    return p;
  }

  /** Song position that was audible when a key/pointer event happened. */
  positionAtEvent(timeStamp) {
    if (!this.playing) return this.pausedPos;
    return this._posAt(this.heardCtxTime(timeStamp));
  }

  async play(from) {
    const ctx = this._ensure();
    if (ctx.state !== 'running') await ctx.resume();
    if (!this.buffer) return;
    let pos = from ?? this.pausedPos;
    if (pos >= this.duration - 0.05 || pos < 0) pos = 0;
    this._stopSource();
    const src = ctx.createBufferSource();
    src.buffer = this.buffer;
    src.playbackRate.value = this.rate;
    src.connect(this.pre);
    const when = ctx.currentTime + 0.05;
    src.start(when, pos);
    src.onended = () => {
      if (this.src !== src) return;
      this.src = null;
      this.playing = false;
      this.pausedPos = 0;
      this.ticker.stop();
      this._stopClicks();
      this._emit('ended');
      this._emit('state');
    };
    this.src = src;
    this.startCtx = when;
    this.startPos = pos;
    this.playing = true;
    this._lastVis = null;
    this._resetClicks();
    this.ticker.start();
    this._schedule();
    this._emit('state');
  }

  pause() {
    if (!this.playing) return;
    this.pausedPos = this.position();
    this.stop(true);
  }

  stop(keepPos = false) {
    const wasPlaying = this.playing;
    this.playing = false;
    this._stopSource();
    this._stopClicks();
    this.ticker.stop();
    if (!keepPos) this.pausedPos = 0;
    if (wasPlaying) this._emit('state');
  }

  toggle() { return this.playing ? this.pause() : this.play(); }

  seek(t) {
    t = Math.max(0, Math.min(this.duration || 0, t));
    if (this.playing) this.play(t);
    else { this.pausedPos = t; this._emit('state'); }
  }

  setRate(r) {
    if (r === this.rate) return;
    const pos = this.position();
    this.rate = r;
    if (this.playing) this.play(pos);
  }

  setEvents(events) {
    this.events = events || [];
    if (this.playing) this._resetClicks();
  }

  setClicks(on) { this.clicksOn = on; if (this.playing) this._resetClicks(); }
  setMuteClicks(on) { this.muteClicks = on; if (this.playing) this._resetClicks(); }
  setSound(name) { if (this.sounds?.[name] || !this.ctx) this.sound = name; }

  setVolumes(music, click) {
    this.musicVol = music;
    this.clickVol = click;
    this._applyVolumes();
  }

  _applyVolumes() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.musicGain.gain.setTargetAtTime(this.musicVol, t, 0.015);
    this.clickGain.gain.setTargetAtTime(this.clickVol, t, 0.015);
  }

  /** Audition a click sound (normal then accent). */
  async preview(name = this.sound) {
    const ctx = this._ensure();
    if (ctx.state !== 'running') await ctx.resume();
    const t = ctx.currentTime + 0.03;
    [[0, 0.55], [1, 1]].forEach(([accent, s], i) => this._fire({ s, accent }, t + i * 0.22, name));
  }

  /** Frequency bins (0..255) of the music, for visuals. */
  spectrum(out) {
    if (!this.analyser) return null;
    this.analyser.getByteFrequencyData(out);
    return out;
  }

  // -- internals
  _stopSource() {
    if (this.src) {
      const s = this.src;
      this.src = null;
      try { s.stop(); } catch { /* already stopped */ }
      s.disconnect();
    }
  }

  _stopClicks() {
    for (const s of this.scheduled) { try { s.node.stop(); } catch { /* fine */ } }
    this.scheduled = [];
  }

  _resetClicks() {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    const keep = [];
    for (const s of this.scheduled) {
      if (s.when > now + 0.002) { try { s.node.stop(); } catch { /* fine */ } } else keep.push(s);
    }
    this.scheduled = keep;
    this.nextIdx = lowerBound(this.events, this._posAt(Math.max(now, this.startCtx)));
  }

  _schedule() {
    if (!this.playing || !this.ctx) return;
    const now = this.ctx.currentTime;
    const horizon = now + LOOKAHEAD;
    const audible = this.clicksOn && !this.muteClicks;
    const ev = this.events;
    while (this.nextIdx < ev.length) {
      const e = ev[this.nextIdx];
      const when = this.startCtx + (e.t - this.startPos) / this.rate;
      if (when > horizon) break;
      if (audible && when >= now - 0.008) this._fire(e, Math.max(when, now));
      this.nextIdx++;
    }
    if (this.scheduled.length > 96) this.scheduled = this.scheduled.filter((s) => s.when > now - 0.5);
  }

  _fire(e, when, sound = this.sound) {
    const ctx = this.ctx;
    const accent = e.accent ?? (e.s >= 0.8);
    const node = ctx.createBufferSource();
    node.buffer = this.sounds[sound][accent ? 1 : 0];
    const g = ctx.createGain();
    g.gain.value = 0.45 + 0.55 * Math.min(1, e.s);
    node.connect(g);
    g.connect(this.clickGain);
    node.start(when);
    node.onended = () => { node.disconnect(); g.disconnect(); };
    this.scheduled.push({ node, when });
  }
}
