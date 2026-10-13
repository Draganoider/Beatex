// Beatex Studio — app state and wiring.

import { api } from './api.js';
import { AudioEngine } from './audio.js';
import { GameView } from './game.js';
import { readScore, scoreTake } from './taps.js';
import { Peaks, Timeline } from './timeline.js';
import {
  $, $$, artStyle, confirmDialog, debounce, esc, fmtAgo, fmtBytes, fmtDuration, fmtTime,
  hydrateIcons, icon, openModal, setRangeFill, splitTitle, toast, topModal,
} from './ui.js';

// ------------------------------------------------------------------ prefs
const PREFS_KEY = 'beatex.studio.v1';
const DEFAULT_SHAPE = { policy: 'head_tail', spinners: false, min_spacing: 0, accent: 0.3, offset: 0 };
const DEFAULT_PREFS = {
  shape: DEFAULT_SHAPE, sound: 'beep', musicVol: 0.8, clickVol: 0.9, clicks: true, compare: true,
  follow: true, rate: 1, mp3ClicksOnly: false, lastRun: null, genRatio: 0.9, expanded: [],
  newDiff: 4, newYear: 2021,
};

function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    return { ...DEFAULT_PREFS, ...p, shape: { ...DEFAULT_SHAPE, ...(p.shape || {}) } };
  } catch {
    return { ...DEFAULT_PREFS, shape: { ...DEFAULT_SHAPE } };
  }
}
const prefs = loadPrefs();
const savePrefs = debounce(() => {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* private mode etc. */ }
}, 250);

// ------------------------------------------------------------------ state
const S = {
  view: 'welcome',
  health: null,
  runs: [],
  jobs: [],
  seenJobs: new Map(),
  autoOpen: new Set(),
  run: null,
  info: null,
  events: [],
  allEvents: {},       // run_id -> shaped events, for every run of the current song
  audioSha: null,
  takes: [],
  take: null,          // latest take's tap times
  scores: {},          // run_id -> tap score
  recording: null,
  expanded: new Set(prefs.expanded),
  search: '',
  shapeTok: 0,
  newModal: null,
  jobTimer: null,
};

const engine = new AudioEngine();
engine.musicVol = prefs.musicVol;
engine.clickVol = prefs.clickVol;
engine.sound = prefs.sound;
engine.clicksOn = prefs.clicks;
engine.rate = prefs.rate;

const timeline = new Timeline({
  overview: $('#overview'),
  detail: $('#detail'),
  wrap: $('#detailWrap'),
  tooltip: $('#tlTooltip'),
  onSeek: (t) => engine.seek(t),
  onFollowChange: (on) => { prefs.follow = on; savePrefs(); syncToggles(); },
  onLaneClick: (id) => openRun(id),
});
timeline.follow = prefs.follow;
const game = new GameView($('#game'));
window.beatex = { S, prefs, engine, timeline, game };  // console debugging handle

// ------------------------------------------------------------------ helpers
const byDiff = (a, b) => a.difficulty - b.difficulty || a.year - b.year || a.created_ts - b.created_ts;
const runById = (id) => S.runs.find((r) => r.run_id === id);
const runsOfSong = (sha) => S.runs.filter((r) => r.audio_sha256 === sha).sort(byDiff);
const shortGpu = (g) => g.replace(/^NVIDIA\s+(GeForce\s+)?/i, '');
const isAudio = (f) => /\.(mp3|wav|ogg|m4a|flac)$/i.test(f.name);

function runName(r) {
  const twins = S.runs.filter((x) => x.audio_sha256 === r.audio_sha256 && x.difficulty === r.difficulty && x.year === r.year);
  return `d${r.difficulty} · ${r.year}` + (twins.length > 1 ? ` · seed ${r.seed ?? '–'}` : '');
}

function songs() {
  const map = new Map();
  for (const r of S.runs) {
    let s = map.get(r.audio_sha256);
    if (!s) {
      s = { sha: r.audio_sha256, ext: r.audio_ext, filename: r.audio_filename, duration: r.duration_sec, runs: [], latest: 0 };
      map.set(r.audio_sha256, s);
    }
    s.runs.push(r);
    s.latest = Math.max(s.latest, r.created_ts);
  }
  for (const s of map.values()) s.runs.sort(byDiff);
  return [...map.values()].sort((a, b) => b.latest - a.latest);
}

function bestRun() {
  let best = null;
  for (const [id, sc] of Object.entries(S.scores)) if (sc && (!best || sc.f1 > best.sc.f1)) best = { id, sc };
  return best;
}

function setSeg(sel, v) { $$(`${sel} button`).forEach((b) => b.classList.toggle('on', b.dataset.v === String(v))); }
function onSeg(sel, fn) {
  $(sel).addEventListener('click', (e) => { const b = e.target.closest('button[data-v]'); if (b) fn(b.dataset.v); });
}

// ------------------------------------------------------------------ health
async function refreshHealth() {
  try { S.health = await api.health(); } catch { S.health = null; }
  renderHealth();
  renderSetupCard();
}

function renderHealth() {
  const pill = $('#healthPill'), h = S.health;
  const running = S.jobs.find((j) => j.status === 'running');
  pill.classList.remove('ok', 'warn', 'busy');
  let label;
  if (!h) { pill.classList.add('warn'); label = 'Studio server offline'; }
  else if (running) { pill.classList.add('busy'); label = `Generating · ${Math.round(running.progress * 100)}%`; }
  else if (!h.ready) { pill.classList.add('warn'); label = 'Setup needed'; }
  else { pill.classList.add('ok'); label = h.gpu ? `Model ready · ${shortGpu(h.gpu)}` : 'Model ready'; }
  pill.querySelector('.label').textContent = label;
}

function renderSetupCard() {
  const el = $('#setupCard'), h = S.health;
  if (!h || h.ready) { el.hidden = true; return; }
  const missing = [];
  if (!h.model.repo_ok) missing.push('the Mapperatorinator model repo');
  if (!h.model.python_ok) missing.push('its Python 3.10 environment');
  if (!h.ffmpeg || !h.ffprobe) missing.push('ffmpeg');
  el.hidden = false;
  el.innerHTML = `<h3>${icon('alert')}Finish setup to generate new beatmaps</h3>
    <p>Missing: ${esc(missing.join(', '))}. You can still open, shape and export existing runs.</p>
    <button class="btn btn-sm" data-act="setup">See setup steps</button>`;
}

function openSetupModal() {
  const h = S.health || { model: {} };
  const m = h.model || {};
  const rows = [
    [m.repo_ok, 'Mapperatorinator model repo', m.repo_dir || 'external/Mapperatorinator',
      'git clone --recurse-submodules https://github.com/OliBomby/Mapperatorinator.git external/Mapperatorinator'],
    [m.python_ok, 'Model Python 3.10 environment', m.python || '',
      'uv venv external/Mapperatorinator/.venv --python 3.10\nuv pip install --python external/Mapperatorinator/.venv torch torchaudio --index-url https://download.pytorch.org/whl/cu130\nuv pip install --python external/Mapperatorinator/.venv -r setup/mapperatorinator-requirements-win.txt'],
    [m.weights_cached ? true : 'warn', 'Model weights (Mapperatorinator V32)',
      m.weights_cached ? 'Cached in your Hugging Face cache' : 'Downloaded automatically from Hugging Face on the first generation'],
    [h.ffmpeg && h.ffprobe, 'ffmpeg and ffprobe on PATH', h.ffmpeg && h.ffprobe ? 'Found' : 'Needed to read audio', 'winget install Gyan.FFmpeg'],
    [h.gpu ? true : 'warn', 'NVIDIA GPU', h.gpu || 'Not detected. Generation falls back to the CPU and is much slower.'],
    [h.clicktrack ? true : 'warn', 'Click-track mp3 export', h.clicktrack ? 'numpy + pydub available' : 'Optional',
      h.clicktrack ? '' : 'uv pip install --python .venv -e ".[app]"'],
  ];
  const html = rows.map(([ok, title, detail, cmd]) => {
    const cls = ok === true ? 'ok' : ok === 'warn' ? 'warn' : 'bad';
    const ic = ok === true ? 'check' : ok === 'warn' ? 'info' : 'x';
    return `<div class="check ${cls}"><span class="ci">${icon(ic)}</span><div><b>${esc(title)}</b><small>${esc(detail || '')}</small>${cmd && ok !== true ? `<pre>${esc(cmd)}</pre>` : ''}</div></div>`;
  }).join('');
  const md = openModal(`
    <div class="modal-head"><h2>Environment</h2><p>${h.ready ? 'Everything needed to generate beatmaps is in place.' : 'A few pieces are missing before Beatex can generate. Run these from the Beatex folder.'}</p></div>
    <div class="modal-body"><div class="checks">${html}</div></div>
    <div class="modal-foot"><span class="grow">Beatex ${esc(h.version || '')} · data in ${esc(h.data_dir || 'data/')}</span>
      <button class="btn" data-a="recheck">${icon('refresh')}Re-check</button></div>`, { size: 'lg' });
  md.el.querySelector('[data-a=recheck]').onclick = async () => { md.close(); await refreshHealth(); openSetupModal(); };
}

// ------------------------------------------------------------------ library
async function refreshRuns() {
  try { S.runs = await api.runs(); } catch (e) { toast('Could not load runs', e.message, { kind: 'err' }); }
  if (S.run) S.run = runById(S.run.run_id) || S.run;
  renderLibrary();
  renderRecent();
  if (S.run && S.view === 'wb') { renderHeader(); renderRunSwitch(); }
}

function renderLibrary() {
  const lib = $('#library');
  const q = S.search.trim().toLowerCase();
  const list = songs().filter((s) => !q || s.filename.toLowerCase().includes(q));
  if (!S.runs.length) {
    lib.innerHTML = `<div class="lib-empty">No beatmaps yet.<br>Create one with <b>New beatmap</b>.</div>`;
    return;
  }
  if (!list.length) {
    lib.innerHTML = `<div class="lib-empty">No songs match “${esc(S.search)}”.</div>`;
    return;
  }
  lib.innerHTML = list.map((s) => {
    const { artist, title } = splitTitle(s.filename);
    const open = S.expanded.has(s.sha) || !!q;
    const cur = S.run?.audio_sha256 === s.sha;
    const sub = [artist, `${s.runs.length} run${s.runs.length > 1 ? 's' : ''}`, fmtDuration(s.duration)].filter(Boolean).join(' · ');
    return `<div class="song ${open ? 'open' : ''} ${cur ? 'current' : ''}">
      <button class="song-row" data-act="toggle" data-sha="${s.sha}" title="${esc(s.filename)}">
        <span class="art" style="${artStyle(s.sha)}"></span>
        <span class="song-meta"><div class="song-name">${esc(title)}</div><div class="song-sub">${esc(sub)}</div></span>
        <span class="song-chev">${icon('chevron')}</span>
      </button>
      <div class="song-runs">
        ${s.runs.map((r) => `<button class="run-row ${S.run?.run_id === r.run_id ? 'active' : ''}" data-act="open" data-id="${r.run_id}" title="${esc(r.note || '')}">
          <span class="d">d${r.difficulty}</span><span>${r.year}</span>
          ${r.starred ? `<span class="star">${icon('starFill')}</span>` : ''}
          <span class="when">${fmtAgo(r.created_ts)}</span></button>`).join('')}
        <button class="song-new" data-act="new-for" data-sha="${s.sha}">${icon('plus')}New run</button>
      </div></div>`;
  }).join('');
}

function renderRecent() {
  const runs = [...S.runs].sort((a, b) => b.created_ts - a.created_ts).slice(0, 8);
  $('#recentWrap').hidden = !runs.length;
  $('#recentGrid').innerHTML = runs.map((r) => {
    const { title } = splitTitle(r.audio_filename);
    return `<button class="recent-card" data-id="${r.run_id}">
      <span class="art" style="${artStyle(r.audio_sha256)}"></span>
      <div><div class="t">${esc(title)}</div><div class="s">d${r.difficulty} · ${r.year} · ${fmtAgo(r.created_ts)}</div></div>
    </button>`;
  }).join('');
}

// ------------------------------------------------------------------ views
function showWelcome() {
  if (S.recording) stopTapping(false);
  engine.pause();
  S.view = 'welcome';
  $('#main').classList.remove('wb-mode');
  $('#welcome').hidden = false;
  $('#workbench').hidden = true;
  renderRecent();
  renderSetupCard();
}

function showWorkbench() {
  if (S.view === 'wb') return;
  S.view = 'wb';
  $('#main').classList.add('wb-mode');
  $('#welcome').hidden = true;
  $('#workbench').hidden = false;
  requestAnimationFrame(() => { timeline.resize(); game.resize(); });
}

function closeNav() { $('#app').classList.remove('nav-open'); }

// ------------------------------------------------------------------ open a run
async function openRun(id) {
  const r = runById(id);
  if (!r) return;
  if (S.recording) await stopTapping(false);
  S.run = r;
  prefs.lastRun = id;
  S.expanded.add(r.audio_sha256);
  prefs.expanded = [...S.expanded];
  savePrefs();
  showWorkbench();
  closeNav();
  renderHeader();
  renderLibrary();
  renderRunSwitch();
  renderDetails();
  if (S.audioSha !== r.audio_sha256) {
    S.allEvents = {};
    S.events = [];
    S.takes = [];
    S.take = null;
    S.scores = {};
    engine.setEvents([]);
    timeline.setEvents([]);
    game.setEvents([]);
    renderTapScore();
    loadAudio(r);
    loadTaps(r.audio_sha256);
  }
  await reshape();
}

function showLoading(text, spinner = true) {
  $('#tlLoading').hidden = false;
  $('#tlLoading .spinner').style.display = spinner ? '' : 'none';
  $('#tlLoadingText').textContent = text;
}

async function loadAudio(r) {
  const sha = r.audio_sha256;
  S.audioSha = sha;
  engine.clear();
  timeline.setAudio(null, r.duration_sec);
  $('#timeDur').textContent = fmtTime(r.duration_sec, 0);
  if (!r.audio_available) {
    showLoading('The audio for this run is no longer cached', false);
    return;
  }
  showLoading('Loading audio…');
  try {
    const resp = await fetch(api.audioUrl(sha, r.audio_ext));
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const ab = await resp.arrayBuffer();
    if (S.audioSha !== sha) return;
    showLoading('Decoding audio…');
    const buf = await engine.decode(ab);
    if (S.audioSha !== sha) return;
    engine.setBuffer(buf);
    engine.setEvents(S.events);
    timeline.setAudio(new Peaks(buf), buf.duration);
    timeline.setEvents(S.events);
    $('#timeDur').textContent = fmtTime(buf.duration, 0);
    $('#tlLoading').hidden = true;
    renderStats();
  } catch (e) {
    if (S.audioSha === sha) showLoading(`Could not decode this audio (${e.message})`, false);
  }
}

async function reshape() {
  if (!S.run) return;
  const tok = ++S.shapeTok, run = S.run;
  const ids = runsOfSong(run.audio_sha256).map((r) => r.run_id);
  if (!ids.includes(run.run_id)) ids.push(run.run_id);
  const res = await Promise.all(ids.map((id) => api.events(id, prefs.shape).catch(() => null)));
  if (tok !== S.shapeTok) return;
  S.allEvents = {};
  ids.forEach((id, i) => { if (res[i]) S.allEvents[id] = res[i].events; });
  const cur = res[ids.indexOf(run.run_id)];
  if (!cur) { toast('Could not shape this run', 'Its .osu file may be missing.', { kind: 'err' }); return; }
  S.info = cur;
  S.events = cur.events;
  engine.setEvents(S.events);
  timeline.setEvents(S.events);
  game.setEvents(S.events);
  computeScores();
  updateLanes();
  renderStats();
  renderBreakdown();
  renderRunSwitch();
  renderTapScore();
}
const reshapeSoon = debounce(reshape, 60);

function updateLanes() {
  const lanes = [];
  if (S.recording) lanes.push({ id: 'rec', kind: 'taps', label: 'Recording', times: S.recording.taps, live: true });
  else if (S.take) lanes.push({ id: 'taps', kind: 'taps', label: 'Your taps', times: S.take });
  if (prefs.compare && S.run) {
    for (const r of runsOfSong(S.run.audio_sha256)) {
      if (r.run_id === S.run.run_id || !S.allEvents[r.run_id]) continue;
      lanes.push({ id: r.run_id, kind: 'run', label: runName(r), events: S.allEvents[r.run_id] });
      if (lanes.length >= 7) break;
    }
  }
  timeline.setLanes(lanes);
}

// ------------------------------------------------------------------ workbench rendering
function renderHeader() {
  const r = S.run;
  if (!r) return;
  const { artist, title } = splitTitle(r.audio_filename);
  const art = $('#songArt');
  art.className = 'song-art art';
  art.setAttribute('style', artStyle(r.audio_sha256));
  $('#songArtist').textContent = artist || 'Beatmap';
  $('#songTitle').textContent = title;
  $('#songTitle').title = r.audio_filename;
  const chips = [
    [`difficulty ${r.difficulty}`, 'accent'],
    [`${r.year} style`, ''],
    [`seed ${r.seed ?? 'random'}`, ''],
  ];
  if (r.cfg_scale) chips.push([`cfg ${r.cfg_scale}`, '']);
  if (r.super_timing) chips.push(['super timing', 'warm']);
  if (r.batch_label) chips.push([`batch ${r.batch_label}`, '']);
  $('#runChips').innerHTML = chips.map(([t, c]) => `<span class="chip ${c}">${esc(t)}</span>`).join('');
  const star = $('#starBtn');
  star.innerHTML = icon(r.starred ? 'starFill' : 'star');
  star.classList.toggle('on', !!r.starred);
  star.title = r.starred ? 'Unstar this run (S)' : 'Star this run (S)';
}

function renderRunSwitch() {
  if (!S.run) return;
  const runs = runsOfSong(S.run.audio_sha256);
  const best = bestRun();
  $('#runSwitch').innerHTML = runs.map((r) => {
    const lvl = Math.max(1, Math.min(5, Math.ceil(r.difficulty / 1.6)));
    const n = S.allEvents[r.run_id]?.length ?? r.n_objects;
    const sc = S.scores[r.run_id];
    const on = r.run_id === S.run.run_id;
    return `<button class="run-pill ${on ? 'on' : ''}" data-id="${r.run_id}" role="tab" aria-selected="${on}" title="${esc(runName(r))} · ${n} hits${r.note ? ' · ' + esc(r.note) : ''}">
      <span class="lvl">${[6, 8, 10, 12, 14].map((h, i) => `<i class="${i < lvl ? 'f' : ''}" style="height:${h}px"></i>`).join('')}</span>
      <span>${esc(runName(r))}</span><span class="n">${n}</span>
      ${sc ? `<span class="f1 ${best?.id === r.run_id ? 'best' : ''}" title="Tap match">${Math.round(sc.f1 * 100)}%</span>` : ''}
      ${r.starred ? icon('starFill') : ''}
    </button>`;
  }).join('') + `<button class="run-pill add" data-act="new" title="Generate another run of this song">${icon('plus')}<span>New run</span></button>`;
}

function peakDensity(ev, win = 4) {
  let best = 0;
  for (let i = 0, j = 0; j < ev.length; j++) {
    while (ev[j].t - ev[i].t > win) i++;
    best = Math.max(best, j - i + 1);
  }
  return best / win;
}

function renderStats() {
  if (!S.run) return;
  const ev = S.events, n = ev.length;
  const dur = engine.duration || S.run.duration_sec || 1;
  const accents = ev.filter((e) => e.s >= 0.8).length;
  const sc = S.scores[S.run.run_id];
  const tiles = [
    ['Hits', n.toLocaleString(), `${S.run.n_objects.toLocaleString()} model objects`],
    ['Density', `${(n / dur).toFixed(2)}<small>/s</small>`, `peak ${peakDensity(ev).toFixed(1)}/s`],
    ['Tempo', `${Math.round(S.info?.bpm || S.run.bpm)}<small>BPM</small>`, `${S.info?.meter || S.run.meter} · model estimate`],
    ['Accents', accents.toLocaleString(), `${Math.round((accents / Math.max(1, n)) * 100)}% of hits`],
    sc ? ['Tap match', `${Math.round(sc.f1 * 100)}<small>%</small>`, 'vs your latest take', 'hl']
       : ['Length', fmtTime(dur, 0), `${Math.round(dur)} seconds`],
  ];
  const el = $('#stats');
  el.classList.toggle('has-taps', !!sc);
  el.innerHTML = tiles.map(([k, v, d, cls]) => `<div class="stat ${cls || ''}"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${esc(d)}</div></div>`).join('');
}

const SRC = {
  circle: ['Circles', '#2bd6c6'],
  slider_head: ['Slider heads', '#7fd3b0'],
  slider_tail: ['Slider tails', '#9b7bff'],
  hold_head: ['Hold heads', '#7fd3b0'],
  hold_tail: ['Hold tails', '#9b7bff'],
  spinner_start: ['Spinner starts', '#ffb454'],
  spinner_end: ['Spinner ends', '#ff8a5b'],
};

function renderBreakdown() {
  const counts = {};
  for (const e of S.events) counts[e.src] = (counts[e.src] || 0) + 1;
  const total = S.events.length || 1;
  const keys = Object.keys(SRC).filter((k) => counts[k]);
  $('#breakdown').innerHTML = `
    <div class="bd-bar">${keys.map((k) => `<i style="width:${(counts[k] / total) * 100}%;background:${SRC[k][1]}"></i>`).join('')}</div>
    <div class="bd-legend">${keys.map((k) => `<span><i style="background:${SRC[k][1]}"></i>${SRC[k][0]} <b>${counts[k]}</b></span>`).join('')}</div>`;
}

function renderDetails() {
  const r = S.run;
  if (!r) return;
  const rows = [
    ['Created', r.created_at],
    ['Difficulty', r.difficulty],
    ['Style year', r.year],
    ['Seed', r.seed ?? 'random'],
    ['CFG scale', r.cfg_scale ?? '1 (off)'],
    ['Super timing', r.super_timing ? 'on' : 'off'],
    ['Model objects', r.n_objects.toLocaleString()],
    ['Tempo', `${r.bpm} BPM · ${r.meter}`],
    ['Song length', fmtTime(r.duration_sec, 0)],
  ];
  if (r.batch_label) rows.push(['Batch', r.batch_label]);
  rows.push(['Run ID', r.run_id]);
  $('#runDetails').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd title="${esc(v)}">${esc(v)}</dd>`).join('');
  $('#runNote').value = r.note || '';
}

// ------------------------------------------------------------------ taps
async function loadTaps(sha) {
  let data;
  try { data = await api.taps(sha); } catch { data = { takes: [] }; }
  if (S.audioSha !== sha) return;
  S.takes = data.takes || [];
  S.take = S.takes.length ? S.takes[S.takes.length - 1].taps : null;
  computeScores();
  updateLanes();
  renderTapScore();
  renderStats();
  renderRunSwitch();
}

function computeScores() {
  S.scores = {};
  if (!S.take) return;
  for (const [id, ev] of Object.entries(S.allEvents)) S.scores[id] = scoreTake(S.take, ev.map((e) => e.t));
}

function renderTapScore() {
  const el = $('#tapScore');
  $('#tapClear').hidden = !S.takes.length;
  const sc = S.run && S.scores[S.run.run_id];
  if (!S.take || !sc) {
    el.innerHTML = `<div class="ts-empty"><p>Tap along on every beat you feel. Beatex then scores <b>every run</b> of this song against your taps, so you can see which one matches your feel.</p>
      <button class="btn btn-sm" data-act="tap">${icon('hand')}Start tapping</button></div>`;
    return;
  }
  const C = 2 * Math.PI * 30;
  const best = bestRun();
  const bias = Math.round(sc.biasMs);
  const bestRunMeta = best && best.id !== S.run.run_id ? runById(best.id) : null;
  el.innerHTML = `
    <div class="ts-main">
      <div class="ring"><svg viewBox="0 0 74 74" aria-hidden="true"><defs><linearGradient id="ringGrad" x1="0" x2="1"><stop offset="0" stop-color="#2bd6c6"/><stop offset="1" stop-color="#ffb454"/></linearGradient></defs>
        <circle cx="37" cy="37" r="30" stroke="rgba(255,255,255,.08)" stroke-width="7" fill="none"/>
        <circle cx="37" cy="37" r="30" stroke="url(#ringGrad)" stroke-width="7" fill="none" stroke-linecap="round" stroke-dasharray="${(C * sc.f1).toFixed(1)} ${C.toFixed(1)}"/></svg>
        <div class="rv">${Math.round(sc.f1 * 100)}%</div></div>
      <div class="ts-lines">
        <div class="ts-line"><span>Map hits you tapped</span><b>${Math.round(sc.precision * 100)}%</b></div>
        <div class="ts-line"><span>Your taps the map has</span><b>${Math.round(sc.recall * 100)}%</b></div>
        <div class="ts-line"><span>Your timing vs map</span><b>${bias > 0 ? '+' : ''}${bias} ms</b></div>
      </div>
    </div>
    <div class="ts-tip">${readScore(sc)}
      ${bestRunMeta ? `<br><b>${esc(runName(bestRunMeta))}</b> matches best (${Math.round(best.sc.f1 * 100)}%). <button class="link-btn" data-act="best" data-id="${best.id}">Switch to it</button>` : ''}
      ${Math.abs(bias) >= 15 ? `<br>You tap ${Math.abs(bias)} ms ${bias > 0 ? 'after' : 'before'} the hits. <button class="link-btn" data-act="offset" data-v="${bias}">Shift map ${bias > 0 ? '+' : ''}${bias} ms</button>` : ''}
    </div>
    <div class="ts-foot"><span>${S.takes.length} take${S.takes.length > 1 ? 's' : ''} · ${S.take.length} taps · ${esc(S.takes[S.takes.length - 1].created_at)}</span>
      <button class="link-btn" data-act="tap">${icon('refresh')}Retake</button></div>`;
}

function startTapping() {
  if (!S.run) return;
  if (!engine.buffer) { toast('Audio is still loading', 'Try again in a moment.', { kind: 'err' }); return; }
  if (S.recording) return;
  S.recording = { taps: [] };
  engine.setMuteClicks(true);
  $('#tapBanner').hidden = false;
  $('#tapBtn').classList.add('rec');
  $('#gameWrap').classList.add('taptarget');
  $('#tapCount').textContent = '0 taps';
  game.setTaps(S.recording.taps, true);
  updateLanes();
  const from = engine.position() > engine.duration - 5 ? 0 : engine.position();
  engine.play(from);
}

function recordTap(ev) {
  if (!S.recording || !engine.playing) return;
  S.recording.taps.push(engine.positionAtEvent(ev.timeStamp));
  const n = S.recording.taps.length;
  $('#tapCount').textContent = `${n} tap${n === 1 ? '' : 's'}`;
  timeline.dirty = true;
  game.dirty = true;
}

async function stopTapping(save) {
  const rec = S.recording;
  if (!rec) return;
  S.recording = null;
  engine.setMuteClicks(false);
  engine.pause();
  $('#tapBanner').hidden = true;
  $('#tapBtn').classList.remove('rec');
  $('#gameWrap').classList.remove('taptarget');
  game.setTaps([], false);
  const taps = rec.taps.slice().sort((a, b) => a - b);
  if (save && taps.length < 4) {
    toast('Not enough taps', 'Tap at least 4 beats to score a take.', { kind: 'err' });
  } else if (save) {
    try {
      const take = await api.saveTaps(S.run.audio_sha256, taps, engine.duration);
      S.takes.push(take);
      S.take = take.taps;
      computeScores();
      renderTapScore();
      renderRunSwitch();
      renderStats();
      const best = bestRun();
      const bestMeta = best && runById(best.id);
      toast('Take scored', bestMeta ? `${runName(bestMeta)} matches your feel best (${Math.round(best.sc.f1 * 100)}%).` : `${taps.length} taps saved.`, { kind: 'ok', timeout: 7000 });
    } catch (e) {
      toast('Could not save taps', e.message, { kind: 'err' });
    }
  }
  updateLanes();
}

// ------------------------------------------------------------------ jobs
async function pollJobs() {
  clearTimeout(S.jobTimer);
  try {
    const jobs = await api.jobs();
    if (!S.health) refreshHealth();
    handleTransitions(jobs);
    S.jobs = jobs;
    renderJobs();
    renderHealth();
  } catch {
    if (S.health) { S.health = null; renderHealth(); }
  }
  const active = S.jobs.some((j) => j.status === 'queued' || j.status === 'running');
  S.jobTimer = setTimeout(pollJobs, active ? 1000 : 4000);
}

function handleTransitions(jobs) {
  const finished = [];
  for (const j of jobs) {
    const prev = S.seenJobs.get(j.id);
    if (prev !== undefined && prev !== j.status) {
      if (j.status === 'done') finished.push(j);
      if (j.status === 'failed') {
        toast('Generation failed', j.error || 'See the log for details.', {
          kind: 'err', timeout: 10000, action: { label: 'Log', run: () => openLogModal(j.id) },
        });
      }
    }
    S.seenJobs.set(j.id, j.status);
  }
  if (finished.length) onJobsFinished(finished);
}

async function onJobsFinished(list) {
  await refreshRuns();
  let reshaped = false;
  for (const j of list) {
    const r = runById(j.run_id);
    if (r && j.started_ts && j.finished_ts && r.duration_sec > 20) {  // learn this GPU's speed
      const ratio = Math.max(0.2, (j.finished_ts - j.started_ts - GEN_OVERHEAD) / r.duration_sec);
      prefs.genRatio = prefs.genRatio * 0.5 + ratio * 0.5;
      savePrefs();
    }
    const title = splitTitle(j.filename).title;
    const wantsOpen = S.autoOpen.has(j.id) && !engine.playing && !S.recording && j.run_id;
    S.autoOpen.delete(j.id);
    if (wantsOpen) {
      await openRun(j.run_id);
      reshaped = true;
      toast('Beatmap ready', `${title} · d${j.difficulty} · ${j.year}`, { kind: 'ok' });
    } else {
      toast('Beatmap ready', `${title} · d${j.difficulty} · ${j.year}`, {
        kind: 'ok', timeout: 9000, action: j.run_id ? { label: 'Open', run: () => openRun(j.run_id) } : null,
      });
    }
  }
  if (!reshaped && S.run && list.some((j) => j.sha256 === S.run.audio_sha256)) reshape();
}

function phaseText(j) {
  if (/timing/i.test(j.phase)) return 'Finding the timing';
  if (/map/i.test(j.phase)) return 'Placing the hits';
  return j.phase || 'Starting';
}

function renderJobs() {
  $('#jobsPanel').hidden = !S.jobs.length;
  if (!S.jobs.length) return;
  const now = Date.now() / 1000;
  const rank = { running: 0, queued: 1 };
  const jobs = [...S.jobs].sort((a, b) => (rank[a.status] ?? 2) - (rank[b.status] ?? 2)
    || (a.status === 'queued' ? a.created_ts - b.created_ts : b.created_ts - a.created_ts));
  let qpos = 0;
  $('#jobsList').innerHTML = jobs.map((j) => {
    const title = splitTitle(j.filename).title;
    const pct = Math.round(j.progress * 100);
    const label = `d${j.difficulty} · ${j.year}`;
    let badge, left, right, actions;
    if (j.status === 'running') {
      const el = now - (j.started_ts || now);
      const eta = j.progress > 0.06 ? (el * (1 - j.progress)) / j.progress : null;
      badge = `${pct}%`;
      left = `${label} · ${phaseText(j)}`;
      right = fmtDuration(el) + (eta ? ` · ~${fmtDuration(eta)} left` : '');
      actions = `<button class="link-btn" data-act="log" data-id="${j.id}">${icon('log')}Log</button><button class="link-btn" data-act="cancel" data-id="${j.id}">${icon('x')}Cancel</button>`;
    } else if (j.status === 'queued') {
      qpos += 1;
      badge = 'Queued';
      left = label;
      right = `#${qpos} in line`;
      actions = `<button class="link-btn" data-act="cancel" data-id="${j.id}">${icon('x')}Remove</button>`;
    } else if (j.status === 'done') {
      badge = 'Done';
      left = `${label} · took ${fmtDuration((j.finished_ts || now) - (j.started_ts || now))}`;
      right = fmtAgo(j.finished_ts || now);
      actions = j.run_id ? `<button class="link-btn" data-act="open" data-id="${j.run_id}">${icon('open')}Open</button>` : '';
    } else {
      badge = j.status === 'failed' ? 'Failed' : 'Cancelled';
      left = j.status === 'failed' ? (j.error || label) : label;
      right = fmtAgo(j.finished_ts || now);
      actions = `<button class="link-btn" data-act="log" data-id="${j.id}">${icon('log')}Log</button>`;
    }
    return `<div class="job ${j.status}">
      <div class="job-top"><span class="job-name" title="${esc(j.filename)}">${esc(title)}</span><span class="job-badge ${j.status}">${badge}</span></div>
      <div class="job-sub"><span title="${esc(left)}">${esc(left)}</span><span>${esc(right)}</span></div>
      ${j.status === 'running' || j.status === 'queued' ? `<div class="bar"><i style="width:${Math.max(2, pct)}%"></i></div>` : ''}
      ${actions ? `<div class="job-actions">${actions}</div>` : ''}
    </div>`;
  }).join('');
}

function openLogModal(id) {
  let timer = null;
  const m = openModal(`
    <div class="modal-head"><h2>Model log</h2><p id="logSub">&nbsp;</p></div>
    <div class="modal-body"><pre class="log-view" id="logView">Loading…</pre></div>
    <div class="modal-foot"><span class="grow"></span><button class="btn" data-a="close">Close</button></div>`,
  { size: 'lg', onClose: () => clearInterval(timer) });
  const pre = m.el.querySelector('#logView');
  const load = async () => {
    try {
      const j = await api.job(id, 0);
      const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
      pre.textContent = (j.log || []).slice(-800).join('\n') || '(no output yet)';
      if (atBottom) pre.scrollTop = pre.scrollHeight;
      m.el.querySelector('#logSub').textContent = `${j.filename} · d${j.difficulty} · ${j.year} · ${j.status}`;
      if (!['queued', 'running'].includes(j.status)) clearInterval(timer);
    } catch (e) {
      pre.textContent = `Could not load the log: ${e.message}`;
      clearInterval(timer);
    }
  };
  load();
  timer = setInterval(load, 1000);
  m.el.querySelector('[data-a=close]').onclick = () => m.close();
}

// ------------------------------------------------------------------ new beatmap
const DIFFS = [2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7];
const GEN_OVERHEAD = 20;  // seconds per run to start the model process and load weights

function diffDesc(d) {
  if (d <= 2) return 'Sparse: only the strongest beats';
  if (d <= 3) return 'Light: the main beats and key accents';
  if (d <= 4.5) return 'Balanced: the rhythm plus vocal and melody hits';
  if (d <= 6) return 'Dense: most notes and fills';
  return 'Very dense: streams and fast subdivisions';
}

function openNewModal({ file = null, sha = null } = {}) {
  if (S.newModal) { if (file) S.newModal.setFile(file); return; }
  const st = {
    song: null, uploading: false, progress: 0, uploadName: '',
    diff: prefs.newDiff, year: prefs.newYear, batch: false, batchDiffs: new Set([3, 4, 5]),
    cfg: 1, seed: '', superTiming: false,
  };
  const lib = songs();
  const m = openModal(`
    <div class="modal-head"><h2>New beatmap</h2><p>Pick a song and how busy the map should be. The model runs once on your GPU; shaping afterwards is instant.</p></div>
    <div class="modal-body">
      <div class="dropzone" id="nmDrop" tabindex="0" role="button" aria-label="Choose an audio file"></div>
      ${lib.length ? `<div class="or-pick"><span>or reuse</span><select id="nmPick"><option value="">a song from your library…</option>
        ${lib.map((s) => `<option value="${s.sha}">${esc(splitTitle(s.filename).title)} (${s.runs.length} run${s.runs.length > 1 ? 's' : ''})</option>`).join('')}</select></div>` : ''}
      <div class="form-grid">
        <div class="field row full"><label for="nmBatch">Sweep several difficulties</label><label class="switch"><input type="checkbox" id="nmBatch"><span></span></label></div>
        <div class="field full" id="nmSingle">
          <div class="field-top"><label for="nmDiff">Difficulty</label><output id="nmDiffOut"></output></div>
          <input type="range" id="nmDiff" min="1" max="8" step="0.5">
          <div class="diff-desc" id="nmDiffDesc"></div>
        </div>
        <div class="field full" id="nmBatchBox" hidden>
          <label>Difficulties to generate</label>
          <div class="chipset" id="nmChips">${DIFFS.map((d) => `<button type="button" data-d="${d}">${d}</button>`).join('')}</div>
          <div class="field-help">One run per difficulty, queued back to back. Flip between them while the song plays.</div>
        </div>
        <div class="field full">
          <div class="field-top"><label for="nmYear">Style year</label><output id="nmYearOut"></output></div>
          <input type="range" id="nmYear" min="2007" max="2024" step="1">
          <div class="field-help">Imitates the mapping style of maps from that year.</div>
        </div>
        <details class="adv"><summary>${icon('chevron')}Advanced</summary>
          <div class="form-grid">
            <div class="field"><div class="field-top"><label for="nmCfg">CFG scale</label><output id="nmCfgOut"></output></div>
              <input type="range" id="nmCfg" min="1" max="5" step="0.5">
              <div class="field-help">How hard to follow the style settings. 1 = off.</div></div>
            <div class="field"><label for="nmSeed">Seed</label>
              <div class="inline-input"><input type="number" id="nmSeed" placeholder="random" min="0" max="999999"><button type="button" class="icon-btn" id="nmDice" title="Random seed" aria-label="Random seed">${icon('dice')}</button></div>
              <div class="field-help">Same seed and settings give the same map.</div></div>
            <div class="field row full"><div><label for="nmST" style="margin:0">Super timing</label><div class="field-help">Much slower; more accurate on songs with tempo changes.</div></div>
              <label class="switch"><input type="checkbox" id="nmST"><span></span></label></div>
          </div>
        </details>
      </div>
    </div>
    <div class="modal-foot"><span class="grow" id="nmEta"></span><button class="btn" data-a="cancel">Cancel</button><button class="btn btn-primary" id="nmGo">${icon('sparkles')}Generate</button></div>`,
  { art: true, onClose: () => { S.newModal = null; } });

  const q = (s) => m.el.querySelector(s);
  const drop = q('#nmDrop');

  function renderDrop() {
    if (st.uploading) {
      drop.className = 'dropzone';
      drop.innerHTML = `<span class="dz-ico"><span class="spinner"></span></span><div class="dz-text"><b>Uploading ${esc(st.uploadName)}</b><small>${Math.round(st.progress * 100)}%</small></div>`;
    } else if (st.song) {
      const { artist, title } = splitTitle(st.song.filename);
      const bits = [artist, fmtTime(st.song.duration_sec || 0, 0), st.song.size ? fmtBytes(st.song.size) : '',
        st.song.runs ? `${st.song.runs} existing run${st.song.runs > 1 ? 's' : ''}` : 'new song'].filter(Boolean);
      drop.className = 'dropzone has';
      drop.innerHTML = `<span class="art" style="${artStyle(st.song.sha256)}"></span><div class="dz-text"><b>${esc(title)}</b><small>${esc(bits.join(' · '))}</small></div><span class="link-btn">Change</span>`;
    } else {
      drop.className = 'dropzone';
      drop.innerHTML = `<span class="dz-ico">${icon('upload')}</span><div class="dz-text"><b>Drop an audio file here, or click to browse</b><small>mp3 · wav · ogg · m4a · flac</small></div>`;
    }
    renderFoot();
  }

  function estimate() {
    const dur = st.song?.duration_sec || 180;
    let s = dur * prefs.genRatio + GEN_OVERHEAD;
    if (st.cfg > 1) s *= 1.8;
    if (st.superTiming) s *= 3;
    return s;
  }

  function renderFoot() {
    const n = st.batch ? st.batchDiffs.size : 1;
    const go = q('#nmGo');
    const ready = S.health?.ready;
    go.disabled = !st.song || st.uploading || !n || !ready;
    go.innerHTML = `${icon('sparkles')}${n > 1 ? `Generate ${n} runs` : 'Generate'}`;
    const queued = S.jobs.filter((j) => j.status === 'queued' || j.status === 'running').length;
    let eta = '';
    if (!ready) eta = 'Finish the environment setup first (see the status pill).';
    else if (st.song) eta = `About ${fmtDuration(estimate() * n)} on your GPU${queued ? `, after ${queued} queued` : ''}`;
    q('#nmEta').textContent = eta;
  }

  function syncFields() {
    q('#nmDiff').value = st.diff;
    q('#nmDiffOut').textContent = st.diff.toFixed(1);
    q('#nmDiffDesc').textContent = diffDesc(st.diff);
    q('#nmYear').value = st.year;
    q('#nmYearOut').textContent = st.year;
    q('#nmCfg').value = st.cfg;
    q('#nmCfgOut').textContent = st.cfg === 1 ? 'off' : st.cfg.toFixed(1);
    q('#nmSingle').hidden = st.batch;
    q('#nmBatchBox').hidden = !st.batch;
    q('#nmBatch').checked = st.batch;
    $$('#nmChips button', m.el).forEach((b) => b.classList.toggle('on', st.batchDiffs.has(+b.dataset.d)));
    $$('input[type=range]', m.el).forEach(setRangeFill);
    renderFoot();
  }

  function useLibrarySong(shaVal) {
    const s = songs().find((x) => x.sha === shaVal);
    if (!s) return;
    st.song = { sha256: s.sha, ext: s.ext, filename: s.filename, duration_sec: s.duration, runs: s.runs.length };
    renderDrop();
  }

  async function setFile(f) {
    if (!isAudio(f)) { toast('Not an audio file', 'Use mp3, wav, ogg, m4a or flac.', { kind: 'err' }); return; }
    st.uploading = true;
    st.progress = 0;
    st.uploadName = f.name;
    renderDrop();
    try {
      st.song = await api.upload(f, (p) => { st.progress = p; renderDrop(); });
      const pick = q('#nmPick');
      if (pick) pick.value = '';
    } catch (e) {
      toast('Upload failed', e.message, { kind: 'err' });
    } finally {
      st.uploading = false;
      renderDrop();
    }
  }

  drop.addEventListener('click', () => { if (!st.uploading) $('#fileInput').click(); });
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drop.click(); } });
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  q('#nmPick')?.addEventListener('change', (e) => e.target.value && useLibrarySong(e.target.value));
  q('#nmDiff').addEventListener('input', (e) => { st.diff = +e.target.value; syncFields(); });
  q('#nmYear').addEventListener('input', (e) => { st.year = +e.target.value; syncFields(); });
  q('#nmCfg').addEventListener('input', (e) => { st.cfg = +e.target.value; syncFields(); });
  q('#nmBatch').addEventListener('change', (e) => { st.batch = e.target.checked; syncFields(); });
  q('#nmChips').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-d]');
    if (!b) return;
    const d = +b.dataset.d;
    if (st.batchDiffs.has(d)) st.batchDiffs.delete(d); else st.batchDiffs.add(d);
    syncFields();
  });
  q('#nmSeed').addEventListener('input', (e) => { st.seed = e.target.value; });
  q('#nmDice').addEventListener('click', () => { st.seed = String(Math.floor(Math.random() * 999999)); q('#nmSeed').value = st.seed; });
  q('#nmST').addEventListener('change', (e) => { st.superTiming = e.target.checked; renderFoot(); });
  q('[data-a=cancel]').addEventListener('click', () => m.close());
  q('#nmGo').addEventListener('click', async () => {
    if (!st.song) return;
    const diffs = st.batch ? [...st.batchDiffs].sort((a, b) => a - b) : [st.diff];
    const go = q('#nmGo');
    go.disabled = true;
    try {
      const jobs = await api.submit({
        sha256: st.song.sha256, ext: st.song.ext, filename: st.song.filename,
        combos: diffs.map((d) => [d, st.year]), cfg_scale: st.cfg,
        seed: st.seed === '' ? null : +st.seed, super_timing: st.superTiming,
      });
      jobs.forEach((j) => S.seenJobs.set(j.id, j.status));
      if (S.view !== 'wb' || !S.run || S.run.audio_sha256 === st.song.sha256) S.autoOpen.add(jobs[0].id);
      prefs.newDiff = st.diff;
      prefs.newYear = st.year;
      savePrefs();
      const est = fmtDuration(estimate() * jobs.length);
      m.close();
      const bg = S.health?.app_mode ? ' You can close Beatex; it finishes in the background.' : '';
      toast(jobs.length > 1 ? `Queued ${jobs.length} runs` : 'Generating', `${splitTitle(st.song.filename).title} · about ${est}. Progress is in the sidebar.${bg}`, { kind: 'ok', timeout: 7000 });
      pollJobs();
    } catch (e) {
      toast('Could not start generation', e.message, { kind: 'err' });
      go.disabled = false;
    }
  });

  S.newModal = { setFile, close: () => m.close() };
  if (sha) { useLibrarySong(sha); const pick = q('#nmPick'); if (pick) pick.value = sha; }
  renderDrop();
  syncFields();
  if (file) setFile(file);
}

// ------------------------------------------------------------------ export
async function doExport(kind, btn) {
  if (!S.run) return;
  if (kind === 'mp3' && S.health && !S.health.clicktrack) {
    toast('mp3 export unavailable', 'Install numpy and pydub (the [app] extras).', { kind: 'err' });
    return;
  }
  const small = btn.querySelector('small');
  const old = small.textContent;
  btn.disabled = true;
  small.textContent = kind === 'mp3' ? 'Rendering the mix…' : 'Saving…';
  try {
    const res = await api.exportRun(S.run.run_id, {
      kind, ...prefs.shape, mode: prefs.mp3ClicksOnly ? 'clicks' : 'song',
      song_gain: prefs.musicVol, click_gain: prefs.clickVol,
    });
    const el = $('#exportLast');
    el.hidden = false;
    el.innerHTML = `<b>Saved</b> ${esc(res.name)}<div style="margin-top:6px"><button class="link-btn" data-act="reveal" data-path="${esc(res.path)}">${icon('folder')}Show in folder</button></div>`;
    toast('Exported', res.name, { kind: 'ok' });
  } catch (e) {
    toast('Export failed', e.message, { kind: 'err' });
  } finally {
    btn.disabled = false;
    small.textContent = old;
  }
}

async function copyJson() {
  if (!S.run) return;
  try {
    const text = await fetch(api.beatmapUrl(S.run.run_id, prefs.shape)).then((r) => r.text());
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toast('Copied beatmap-v1 JSON', `${S.events.length} events with the current shaping.`, { kind: 'ok' });
  } catch (e) {
    toast('Copy failed', e.message, { kind: 'err' });
  }
}

// ------------------------------------------------------------------ run actions
function replaceRun(meta) {
  S.runs = S.runs.map((r) => (r.run_id === meta.run_id ? meta : r));
  if (S.run?.run_id === meta.run_id) S.run = meta;
}

async function toggleStar() {
  if (!S.run) return;
  try {
    replaceRun(await api.patchRun(S.run.run_id, { starred: !S.run.starred }));
    renderHeader();
    renderLibrary();
    renderRunSwitch();
  } catch (e) { toast('Could not update run', e.message, { kind: 'err' }); }
}

const saveNote = debounce(async (id, note) => {
  try { replaceRun(await api.patchRun(id, { note })); renderLibrary(); } catch (e) { toast('Could not save note', e.message, { kind: 'err' }); }
}, 600);

async function deleteRun() {
  const r = S.run;
  if (!r) return;
  const ok = await confirmDialog('Delete this run?',
    `${runName(r)} of “${splitTitle(r.audio_filename).title}” will be removed from your library. The song stays cached for its other runs.`);
  if (!ok) return;
  try {
    await api.deleteRun(r.run_id);
  } catch (e) { toast('Delete failed', e.message, { kind: 'err' }); return; }
  const siblings = runsOfSong(r.audio_sha256).filter((x) => x.run_id !== r.run_id);
  await refreshRuns();
  toast('Run deleted', '', { kind: 'ok' });
  if (siblings.length) {
    openRun(siblings[0].run_id);
  } else {
    S.run = null;
    S.audioSha = null;
    engine.clear();
    prefs.lastRun = null;
    savePrefs();
    showWelcome();
    renderLibrary();
  }
}

function stepRun(dir) {
  if (!S.run) return;
  const runs = runsOfSong(S.run.audio_sha256);
  const i = runs.findIndex((r) => r.run_id === S.run.run_id);
  const next = runs[i + dir];
  if (next) openRun(next.run_id);
}

// ------------------------------------------------------------------ controls
function syncShapeUI() {
  const sh = prefs.shape;
  setSeg('#policySeg', sh.policy);
  $('#spinners').checked = sh.spinners;
  $('#minSpacing').value = sh.min_spacing;
  $('#minSpacingOut').textContent = sh.min_spacing ? `${sh.min_spacing} ms` : 'off';
  $('#accent').value = sh.accent;
  $('#accentOut').textContent = `+${(+sh.accent).toFixed(2)}`;
  $('#offset').value = sh.offset;
  $('#offsetOut').textContent = `${sh.offset > 0 ? '+' : ''}${sh.offset} ms`;
  ['#minSpacing', '#accent', '#offset'].forEach((s) => setRangeFill($(s)));
}

function shapeChanged() {
  savePrefs();
  syncShapeUI();
  reshapeSoon();
}

function syncListenUI() {
  setSeg('#soundSeg', prefs.sound);
  $('#musicVol').value = prefs.musicVol;
  $('#musicVolOut').textContent = `${Math.round(prefs.musicVol * 100)}%`;
  $('#clickVol').value = prefs.clickVol;
  $('#clickVolOut').textContent = `${Math.round(prefs.clickVol * 100)}%`;
  setRangeFill($('#musicVol'));
  setRangeFill($('#clickVol'));
  $('#mp3ClicksOnly').checked = prefs.mp3ClicksOnly;
}

function syncToggles() {
  $('#followBtn').classList.toggle('on', timeline.follow);
  $('#compareBtn').classList.toggle('on', prefs.compare);
  $('#clicksBtn').classList.toggle('on', prefs.clicks);
  setSeg('#rateSeg', prefs.rate);
}

const toggleFollow = () => { timeline.setFollow(!timeline.follow); prefs.follow = timeline.follow; savePrefs(); syncToggles(); };
const toggleCompare = () => { prefs.compare = !prefs.compare; savePrefs(); syncToggles(); updateLanes(); };
const toggleClicks = () => { prefs.clicks = !prefs.clicks; engine.setClicks(prefs.clicks); savePrefs(); syncToggles(); };

function bindControls() {
  // top bar + navigation
  $('#navToggle').onclick = () => $('#app').classList.toggle('nav-open');
  $('#scrim').onclick = closeNav;
  $('#brand').onclick = (e) => { e.preventDefault(); showWelcome(); };
  $('#healthPill').onclick = openSetupModal;
  $('#helpBtn').onclick = openHelp;
  $('#newBtn').onclick = () => openNewModal();
  $('#heroNew').onclick = () => openNewModal();
  $('#setupCard').addEventListener('click', (e) => { if (e.target.closest('[data-act=setup]')) openSetupModal(); });
  $('#search').addEventListener('input', (e) => { S.search = e.target.value; renderLibrary(); });
  $('#library').addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'toggle') {
      const sha = b.dataset.sha;
      if (S.expanded.has(sha)) S.expanded.delete(sha); else S.expanded.add(sha);
      prefs.expanded = [...S.expanded];
      savePrefs();
      renderLibrary();
    } else if (b.dataset.act === 'open') {
      openRun(b.dataset.id);
    } else if (b.dataset.act === 'new-for') {
      openNewModal({ sha: b.dataset.sha });
    }
  });
  $('#recentGrid').addEventListener('click', (e) => { const b = e.target.closest('[data-id]'); if (b) openRun(b.dataset.id); });
  $('#jobsList').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const { act, id } = b.dataset;
    if (act === 'cancel') { await api.cancelJob(id).catch(() => {}); pollJobs(); }
    else if (act === 'log') openLogModal(id);
    else if (act === 'open') openRun(id);
  });
  $('#clearJobs').onclick = async () => { await api.clearJobs().catch(() => {}); pollJobs(); };

  // workbench header
  $('#starBtn').onclick = toggleStar;
  $('#moreRunsBtn').onclick = () => openNewModal({ sha: S.run?.audio_sha256 });
  $('#deleteRunBtn').onclick = deleteRun;
  $('#runSwitch').addEventListener('click', (e) => {
    const b = e.target.closest('.run-pill');
    if (!b) return;
    if (b.dataset.act === 'new') openNewModal({ sha: S.run?.audio_sha256 });
    else if (b.dataset.id !== S.run?.run_id) openRun(b.dataset.id);
  });

  // timeline + transport
  $('#zoomIn').onclick = () => timeline.zoom(1 / 1.5);
  $('#zoomOut').onclick = () => timeline.zoom(1.5);
  $('#followBtn').onclick = toggleFollow;
  $('#compareBtn').onclick = toggleCompare;
  $('#clicksBtn').onclick = toggleClicks;
  $('#tapBtn').onclick = () => (S.recording ? stopTapping(true) : startTapping());
  $('#tapStop').onclick = () => stopTapping(true);
  $('#tapCancel').onclick = () => stopTapping(false);
  $('#playBtn').onclick = () => engine.toggle();
  $('#toStart').onclick = () => engine.seek(0);
  onSeg('#rateSeg', (v) => { prefs.rate = +v; engine.setRate(+v); savePrefs(); syncToggles(); });
  $('#game').addEventListener('pointerdown', (e) => { if (S.recording) { e.preventDefault(); recordTap(e); } });

  // shape
  onSeg('#policySeg', (v) => { prefs.shape.policy = v; shapeChanged(); });
  $('#spinners').onchange = (e) => { prefs.shape.spinners = e.target.checked; shapeChanged(); };
  $('#minSpacing').oninput = (e) => { prefs.shape.min_spacing = +e.target.value; shapeChanged(); };
  $('#accent').oninput = (e) => { prefs.shape.accent = +e.target.value; shapeChanged(); };
  $('#offset').oninput = (e) => { prefs.shape.offset = +e.target.value; shapeChanged(); };
  $$('[data-nudge]').forEach((b) => {
    b.onclick = () => {
      prefs.shape.offset = Math.max(-150, Math.min(150, prefs.shape.offset + +b.dataset.nudge));
      shapeChanged();
    };
  });
  $('#shapeReset').onclick = () => { prefs.shape = { ...DEFAULT_SHAPE }; shapeChanged(); };

  // listen
  onSeg('#soundSeg', (v) => { prefs.sound = v; engine.setSound(v); engine.preview(v); savePrefs(); syncListenUI(); });
  $('#musicVol').oninput = (e) => { prefs.musicVol = +e.target.value; engine.setVolumes(prefs.musicVol, prefs.clickVol); savePrefs(); syncListenUI(); };
  $('#clickVol').oninput = (e) => { prefs.clickVol = +e.target.value; engine.setVolumes(prefs.musicVol, prefs.clickVol); savePrefs(); syncListenUI(); };

  // tap score
  $('#tapCard').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'tap') startTapping();
    else if (b.dataset.act === 'best') openRun(b.dataset.id);
    else if (b.dataset.act === 'offset') {
      prefs.shape.offset = Math.max(-150, Math.min(150, prefs.shape.offset + Math.round(+b.dataset.v)));
      shapeChanged();
      toast('Timing offset updated', `Now ${prefs.shape.offset > 0 ? '+' : ''}${prefs.shape.offset} ms.`, { kind: 'ok' });
    }
  });
  $('#tapClear').onclick = async () => {
    if (!S.run) return;
    const ok = await confirmDialog('Clear all takes?', 'Your tap-along takes for this song will be deleted.', { ok: 'Clear takes' });
    if (!ok) return;
    await api.deleteTaps(S.run.audio_sha256).catch(() => {});
    S.takes = [];
    S.take = null;
    S.scores = {};
    updateLanes();
    renderTapScore();
    renderStats();
    renderRunSwitch();
  };

  // export
  $('#expJson').onclick = (e) => doExport('json', e.currentTarget);
  $('#expMp3').onclick = (e) => doExport('mp3', e.currentTarget);
  $('#mp3ClicksOnly').onchange = (e) => { prefs.mp3ClicksOnly = e.target.checked; savePrefs(); };
  $('#copyJson').onclick = copyJson;
  $('#openExports').onclick = () => api.reveal(S.health?.exports_dir).catch((err) => toast('Could not open folder', err.message, { kind: 'err' }));
  $('#exportLast').addEventListener('click', (e) => {
    const b = e.target.closest('[data-act=reveal]');
    if (b) api.reveal(b.dataset.path).catch((err) => toast('Could not open folder', err.message, { kind: 'err' }));
  });

  // notes
  $('#runNote').addEventListener('input', (e) => {
    if (!S.run) return;
    S.run.note = e.target.value;
    saveNote(S.run.run_id, e.target.value);
  });

  // file input (shared by the new-beatmap modal)
  $('#fileInput').addEventListener('change', (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (!f) return;
    if (S.newModal) S.newModal.setFile(f); else openNewModal({ file: f });
  });

  // mouse clicks shouldn't leave buttons focused (Space would re-trigger them)
  document.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b && e.detail > 0) b.blur();
  });

  engine.addEventListener('state', () => {
    const b = $('#playBtn');
    b.innerHTML = icon(engine.playing ? 'pause' : 'play');
    b.setAttribute('aria-label', engine.playing ? 'Pause' : 'Play');
    timeline.dirty = true;
    game.dirty = true;
  });
  engine.addEventListener('ended', () => { if (S.recording) stopTapping(true); });
}

// ------------------------------------------------------------------ drag & drop
function bindDnD() {
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  const overlay = $('#dropOverlay');
  window.addEventListener('dragenter', (e) => { if (!hasFiles(e)) return; e.preventDefault(); depth++; if (!S.newModal) overlay.classList.add('show'); });
  window.addEventListener('dragover', (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener('dragleave', (e) => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) overlay.classList.remove('show'); });
  window.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    overlay.classList.remove('show');
    const f = [...e.dataTransfer.files].find(isAudio);
    if (!f) { toast('Not an audio file', 'Use mp3, wav, ogg, m4a or flac.', { kind: 'err' }); return; }
    openNewModal({ file: f });
  });
}

// ------------------------------------------------------------------ keyboard
function openHelp() {
  const rows = [
    ['Play / pause', ['Space']], ['Seek 2 s / 10 s', ['←', '→', 'Shift']], ['Back to start', ['Home']],
    ['Zoom in / out', ['+', '−']], ['Follow playhead', ['F']], ['Clicks on / off', ['M']],
    ['Compare lanes', ['C']], ['Previous / next run', ['[', ']']], ['Star run', ['S']],
    ['Tap along', ['T']], ['Tap a beat (while tapping)', ['D', 'F', 'J', 'K']], ['Stop and score', ['Enter']],
    ['New beatmap', ['N']], ['Cancel / close', ['Esc']],
  ];
  const m = openModal(`
    <div class="modal-head"><h2>Keyboard shortcuts</h2></div>
    <div class="modal-body"><div class="shortcuts">${rows.map(([k, keys]) => `<div class="sc"><span>${k}</span><span>${keys.map((x) => `<kbd>${x}</kbd>`).join('')}</span></div>`).join('')}</div></div>
    <div class="modal-foot"><span class="grow">Drop an audio file anywhere to start a new beatmap.</span><button class="btn" data-a="ok">Got it</button></div>`);
  m.el.querySelector('[data-a=ok]').onclick = () => m.close();
}

function bindKeys() {
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    const textual = (t.tagName === 'INPUT' && !['range', 'checkbox'].includes(t.type)) || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT';
    if (e.key === 'Escape') {
      const m = topModal();
      if (m) { m.close(); return; }
      if (S.recording) { stopTapping(false); return; }
      closeNav();
      return;
    }
    if (textual || topModal() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (t.type === 'range' && /^(Arrow|Home|End|Page)/.test(e.key)) return;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (S.recording) {
      if ('dfjk'.includes(k) && k.length === 1) { e.preventDefault(); if (!e.repeat) recordTap(e); return; }
      if (k === 'Enter') { e.preventDefault(); stopTapping(true); return; }
    }
    if (k === 'n') { openNewModal({ sha: S.view === 'wb' ? S.run?.audio_sha256 : null }); return; }
    if (k === '?') { openHelp(); return; }
    if (S.view !== 'wb') return;
    switch (k) {
      case ' ': e.preventDefault(); engine.toggle(); break;
      case 'ArrowLeft': e.preventDefault(); engine.seek(engine.position() - (e.shiftKey ? 10 : 2)); break;
      case 'ArrowRight': e.preventDefault(); engine.seek(engine.position() + (e.shiftKey ? 10 : 2)); break;
      case 'Home': e.preventDefault(); engine.seek(0); break;
      case '+': case '=': timeline.zoom(1 / 1.5); break;
      case '-': case '_': timeline.zoom(1.5); break;
      case 'f': toggleFollow(); break;
      case 'm': toggleClicks(); break;
      case 'c': toggleCompare(); break;
      case 't': if (S.recording) stopTapping(true); else startTapping(); break;
      case 's': toggleStar(); break;
      case '[': stepRun(-1); break;
      case ']': stepRun(1); break;
      default: break;
    }
  });
}

// ------------------------------------------------------------------ frame loop
let lastTimeText = '';
function frame() {
  if (S.view === 'wb') {
    const pos = engine.position();
    const playing = engine.playing;
    timeline.setPosition(pos, playing);
    timeline.render();
    game.frame(pos, playing, (arr) => engine.spectrum(arr));
    const txt = fmtTime(pos, 1);
    if (txt !== lastTimeText) { $('#timeNow').textContent = txt; lastTimeText = txt; }
  }
  requestAnimationFrame(frame);
}

// ------------------------------------------------------------------ boot
async function init() {
  hydrateIcons();
  bindControls();
  bindDnD();
  bindKeys();
  syncShapeUI();
  syncListenUI();
  syncToggles();

  const ro = new ResizeObserver(() => { timeline.resize(); game.resize(); });
  ro.observe($('#detailWrap'));
  ro.observe($('.overview-wrap'));
  ro.observe($('#gameWrap'));

  window.addEventListener('pagehide', () => api.bye());

  await Promise.all([refreshHealth(), refreshRuns()]);
  pollJobs();
  if (prefs.lastRun && runById(prefs.lastRun)) openRun(prefs.lastRun);
  else showWelcome();
  requestAnimationFrame(frame);
}

init();
