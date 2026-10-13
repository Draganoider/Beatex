// Small DOM/format helpers, the icon set, toasts and modals.

const P = {
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>',
  play: '<path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5Z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6" y="4" width="4.2" height="16" rx="1.2" fill="currentColor" stroke="none"/><rect x="13.8" y="4" width="4.2" height="16" rx="1.2" fill="currentColor" stroke="none"/>',
  skipBack: '<path d="M19 20 9 12l10-8v16Z"/><path d="M5 19V5"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.25 4.1 1 5.85L12 16.9l-5.25 2.75 1-5.85L3.5 9.7l5.9-.9L12 3.5Z"/>',
  starFill: '<path d="m12 3.5 2.6 5.3 5.9.9-4.25 4.1 1 5.85L12 16.9l-5.25 2.75 1-5.85L3.5 9.7l5.9-.9L12 3.5Z" fill="currentColor"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  sparkles: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z"/><path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8L19 15Z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 10.5V4a1.5 1.5 0 0 1 3 0v6.5M14 10.5V5.5a1.5 1.5 0 0 1 3 0V14"/><path d="M17 9.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-1.2a6 6 0 0 1-4.6-2.2L4 15.6a1.6 1.6 0 0 1 2.4-2.1L8 15"/>',
  zoomIn: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
  zoomOut: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>',
  crosshair: '<circle cx="12" cy="12" r="8"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
  metronome: '<path d="M9 3h6l4 18H5L9 3Z"/><path d="m12 15 5-8"/><path d="M7.5 15h9"/>',
  braces: '<path d="M8 4H7a2 2 0 0 0-2 2v4l-2 2 2 2v4a2 2 0 0 0 2 2h1M16 4h1a2 2 0 0 1 2 2v4l2 2-2 2v4a2 2 0 0 1-2 2h-1"/>',
  music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
  folder: '<path d="M3.5 7.5A2 2 0 0 1 5.5 5.5h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-10Z"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  alert: '<path d="M12 4 2.8 19.5h18.4L12 4Z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.5 8.5h.01M15.5 8.5h.01M12 12h.01M8.5 15.5h.01M15.5 15.5h.01"/>',
  log: '<path d="M5 4h14v16H5z"/><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  wand: '<path d="m4 20 11-11M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2ZM19 11l.6 1.4L21 13l-1.4.6L19 15l-.6-1.4L17 13l1.4-.6L19 11Z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.8-3.5L4 9M4 4v5h5M4 13a8 8 0 0 0 14.8 3.5L20 15m0 5v-5h-5"/>',
};

export function icon(name, cls = '') {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ''}</svg>`;
}

/** Replace every [data-icon] placeholder under root with its svg. */
export function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((el) => {
    if (el.dataset.iconDone) return;
    el.insertAdjacentHTML('afterbegin', icon(el.dataset.icon));
    el.dataset.iconDone = '1';
  });
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function fmtTime(sec, decimals = 1) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  const ss = decimals ? s.toFixed(decimals).padStart(decimals + 3, '0') : String(Math.floor(s)).padStart(2, '0');
  return `${m}:${ss}`;
}

export function fmtDuration(sec) {
  if (!isFinite(sec) || sec <= 0) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function fmtAgo(ts) {
  const d = Date.now() / 1000 - ts;
  if (d < 60) return 'just now';
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  if (d < 86400 * 30) return `${Math.floor(d / 86400)}d ago`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1 << 20) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1 << 20)).toFixed(1)} MB`;
}

/** "Artist - Title.mp3" -> {artist, title}. */
export function splitTitle(filename) {
  let base = String(filename || 'Untitled').replace(/\.[a-z0-9]{2,5}$/i, '').replace(/_/g, ' ').trim();
  const m = base.match(/^(.{1,60}?)\s+[-–—]\s+(.+)$/);
  if (m) return { artist: m[1].trim(), title: m[2].trim() };
  return { artist: '', title: base };
}

/** Deterministic gradient "cover" for a song from its sha256. */
export function artStyle(sha) {
  const h1 = parseInt((sha || '0').slice(0, 4), 16) % 360;
  const h2 = (h1 + 40 + (parseInt((sha || '0').slice(4, 6), 16) % 80)) % 360;
  return `background: radial-gradient(120% 120% at 0% 0%, hsl(${h1} 75% 52%), transparent 60%), linear-gradient(135deg, hsl(${h1} 70% 34%), hsl(${h2} 75% 42%));`;
}

/** Strength 0..1 -> teal..amber. */
export function strengthColor(s, alpha = 1) {
  const a = [43, 214, 198], b = [255, 180, 84];
  const k = Math.max(0, Math.min(1, (s - 0.35) / 0.6));
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * k));
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export function setRangeFill(input) {
  const min = +input.min || 0, max = +input.max || 100;
  const p = ((+input.value - min) / (max - min)) * 100;
  input.style.setProperty('--p', `${p}%`);
  if ('center' in input.dataset) {  // fill outward from the middle (e.g. a ± offset)
    input.style.setProperty('--a', `${Math.min(50, p)}%`);
    input.style.setProperty('--b', `${Math.max(50, p)}%`);
  }
}

// ------------------------------------------------------------------ toasts
export function toast(title, msg = '', { kind = 'info', action = null, timeout = 4200 } = {}) {
  const root = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  const ic = kind === 'err' ? 'alert' : kind === 'ok' ? 'check' : 'info';
  el.innerHTML = `<span class="ti">${icon(ic)}</span><div class="tm"><b>${esc(title)}</b>${msg ? `<span>${esc(msg)}</span>` : ''}</div>`;
  if (action) {
    const b = document.createElement('button');
    b.className = 'btn btn-sm';
    b.textContent = action.label;
    b.onclick = () => { action.run(); close(); };
    el.appendChild(b);
  }
  root.appendChild(el);
  let timer = timeout ? setTimeout(close, timeout) : null;
  el.addEventListener('mouseenter', () => clearTimeout(timer));
  el.addEventListener('mouseleave', () => { if (timeout) timer = setTimeout(close, 2000); });
  function close() {
    el.classList.add('out');
    setTimeout(() => el.remove(), 260);
  }
  return close;
}

// ------------------------------------------------------------------ modals
let modalStack = [];

export function openModal(html, { size = '', onClose = null, art = false } = {}) {
  const root = $('#modalRoot');
  const back = document.createElement('div');
  back.className = 'modal-backdrop';
  back.innerHTML = `<div class="modal ${size}" role="dialog" aria-modal="true">${html}</div>`;
  const modal = back.firstElementChild;
  if (art) modal.querySelector('.modal-head')?.classList.add('hero-head');
  const head = modal.querySelector('.modal-head');
  if (head) head.insertAdjacentHTML('beforeend', `<button class="icon-btn modal-close" aria-label="Close">${icon('x')}</button>`);
  root.appendChild(back);
  hydrateIcons(back);
  const api = {
    el: modal,
    close() {
      back.remove();
      modalStack = modalStack.filter((m) => m !== api);
      onClose?.();
    },
  };
  back.addEventListener('mousedown', (e) => { if (e.target === back) api.close(); });
  modal.querySelector('.modal-close')?.addEventListener('click', () => api.close());
  modalStack.push(api);
  setTimeout(() => modal.querySelector('[autofocus]')?.focus(), 30);
  return api;
}

export function topModal() { return modalStack[modalStack.length - 1] || null; }

export function confirmDialog(title, message, { ok = 'Delete', danger = true } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal(`
      <div class="modal-head"><h2>${esc(title)}</h2></div>
      <div class="modal-body"><p style="margin:0;color:var(--text-2)">${esc(message)}</p></div>
      <div class="modal-foot"><span class="grow"></span>
        <button class="btn" data-a="no">Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-a="yes" autofocus>${esc(ok)}</button>
      </div>`, { size: 'sm', onClose: () => { if (!done) resolve(false); } });
    m.el.querySelector('[data-a=no]').onclick = () => m.close();
    m.el.querySelector('[data-a=yes]').onclick = () => { done = true; resolve(true); m.close(); };
  });
}
