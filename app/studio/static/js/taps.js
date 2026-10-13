// Tap-along scoring: how well does a run's hit list match the beats you tapped?
//
// Your taps carry a personal, roughly constant timing bias (motor + device
// latency), so we first estimate that bias as the median offset to the nearest
// hit, then match taps to hits one-to-one inside a tight window around it.

const SEARCH = 0.15;   // seconds: max distance when estimating your bias
const WINDOW = 0.06;   // seconds: match tolerance after removing the bias

function nearestDiffs(taps, hits) {
  const out = [];
  let j = 0;
  for (const t of taps) {
    while (j + 1 < hits.length && hits[j + 1] <= t) j++;
    let best = null;
    for (const k of [j, j + 1]) {
      if (k >= 0 && k < hits.length) {
        const d = t - hits[k];
        if (Math.abs(d) <= SEARCH && (best === null || Math.abs(d) < Math.abs(best))) best = d;
      }
    }
    if (best !== null) out.push(best);
  }
  return out;
}

function median(xs) {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** taps, hits: sorted seconds. Returns null if there is too little to score. */
export function scoreTake(taps, hits) {
  if (!taps || taps.length < 4) return null;
  const lo = taps[0] - 0.75, hi = taps[taps.length - 1] + 0.75;
  const span = hits.filter((t) => t >= lo && t <= hi);
  const bias = median(nearestDiffs(taps, span));

  let i = 0, j = 0, matched = 0;
  const offs = [];
  while (i < taps.length && j < span.length) {
    const d = taps[i] - bias - span[j];
    if (Math.abs(d) <= WINDOW) { matched++; offs.push(d); i++; j++; }
    else if (d < 0) i++;
    else j++;
  }
  const precision = span.length ? matched / span.length : 0;  // map hits you also felt
  const recall = matched / taps.length;                      // your beats the map has
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
  const jitter = offs.length ? Math.sqrt(offs.reduce((a, d) => a + d * d, 0) / offs.length) : 0;
  return {
    matched, nTaps: taps.length, nHits: span.length,
    precision, recall, f1,
    biasMs: bias * 1000, jitterMs: jitter * 1000,
    from: lo, to: hi,
  };
}

/** A short, actionable reading of a score. */
export function readScore(sc) {
  if (!sc) return '';
  const ratio = sc.nHits / Math.max(1, sc.nTaps);
  if (sc.precision < sc.recall - 0.15 || ratio > 1.6) {
    return `This map has <b>${ratio.toFixed(1)}×</b> as many hits as you tapped. Try a lower difficulty, or raise <b>Minimum spacing</b>.`;
  }
  if (sc.recall < sc.precision - 0.15 || ratio < 0.7) {
    return 'The map skips beats you feel. Try a <b>higher difficulty</b>.';
  }
  if (sc.f1 >= 0.75) return 'Close match. This run follows what you feel.';
  return 'Partial match. Compare the other runs, or tap another take.';
}
