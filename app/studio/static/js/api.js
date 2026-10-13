// Thin client for the Studio server's JSON API.

async function req(method, url, body, headers = {}) {
  const opts = { method, headers: { ...headers } };
  if (body instanceof Blob || body instanceof ArrayBuffer) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.body = JSON.stringify(body);
    opts.headers['Content-Type'] = 'application/json';
  }
  const r = await fetch(url, opts);
  const ct = r.headers.get('Content-Type') || '';
  const data = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || `${r.status} ${r.statusText}`);
  return data;
}

export function shapeQuery(shape) {
  return new URLSearchParams({
    policy: shape.policy,
    spinners: shape.spinners ? '1' : '0',
    min_spacing: shape.min_spacing,
    accent: shape.accent,
    offset: shape.offset,
  }).toString();
}

export const api = {
  health: () => req('GET', '/api/health'),
  runs: () => req('GET', '/api/runs').then((d) => d.runs),
  patchRun: (id, fields) => req('PATCH', `/api/runs/${id}`, fields),
  deleteRun: (id) => req('DELETE', `/api/runs/${id}`),
  events: (id, shape) => req('GET', `/api/runs/${id}/events?${shapeQuery(shape)}`),
  exportRun: (id, body) => req('POST', `/api/runs/${id}/export`, body),
  beatmapUrl: (id, shape) => `/api/runs/${id}/beatmap.json?${shapeQuery(shape)}`,
  reveal: (path) => req('POST', '/api/reveal', { path }),
  audioUrl: (sha, ext) => `/api/audio/${sha}${ext}`,
  taps: (sha) => req('GET', `/api/songs/${sha}/taps`),
  saveTaps: (sha, taps, duration_sec) => req('POST', `/api/songs/${sha}/taps`, { taps, duration_sec }),
  deleteTaps: (sha) => req('DELETE', `/api/songs/${sha}/taps`),
  jobs: () => req('GET', '/api/jobs').then((d) => d.jobs),
  job: (id, since = 0) => req('GET', `/api/jobs/${id}?since=${since}`),
  submit: (body) => req('POST', '/api/jobs', body).then((d) => d.jobs),
  cancelJob: (id) => req('DELETE', `/api/jobs/${id}`),
  clearJobs: () => req('POST', '/api/jobs/clear', {}),
  bye: () => navigator.sendBeacon?.('/api/bye', new Blob(['{}'], { type: 'application/json' })),

  /** Upload with progress. Resolves to {sha256, ext, filename, size, duration_sec, runs}. */
  upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open('POST', '/api/upload');
      x.setRequestHeader('X-Filename', encodeURIComponent(file.name));
      x.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      x.onload = () => {
        let data = {};
        try { data = JSON.parse(x.responseText); } catch { /* ignore */ }
        if (x.status >= 200 && x.status < 300) resolve(data);
        else reject(new Error(data.error || `Upload failed (${x.status})`));
      };
      x.onerror = () => reject(new Error('Upload failed — is the Studio server running?'));
      x.send(file);
    });
  },
};
