"""Waveform player for a single (already click-baked) audio stream + hit markers.

The clicks are baked into the audio server-side (beatex.clicktrack), so playback
is one stream on one clock — there's no separate click scheduler and therefore no
possibility of click/song desync. This component only renders the waveform, the
strength-colored markers, a play/pause button and a volume control.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
}


def _audio_data_uri(audio_bytes: bytes, filename: str) -> str:
    mime = _MIME.get(Path(filename).suffix.lower(), "audio/mpeg")
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def waveform_html(audio_bytes: bytes, filename: str, events, height: int = 180) -> str:
    """audio_bytes: the click-baked preview. events: {"t": sec, "s": strength}."""
    uri = _audio_data_uri(audio_bytes, filename)
    markers = [{"t": round(float(e["t"]), 3), "s": round(float(e["s"]), 3)} for e in events]
    return (
        _TEMPLATE
        .replace("__AUDIO__", uri)
        .replace("__MARKERS__", json.dumps(markers))
        .replace("__H__", str(int(height)))
    )


_TEMPLATE = r"""
<div id="bx" style="font-family:system-ui,Segoe UI,sans-serif;color:#ddd;">
  <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
    <button id="playBtn" style="background:#6cb2eb;border:0;color:#06243b;font-weight:600;
            padding:6px 16px;border-radius:6px;cursor:pointer;">▶ Play</button>
    <label style="font-size:12px;color:#bbb;">🔊 volume
      <input type="range" id="vol" min="0" max="100" value="90" style="vertical-align:middle;width:110px;"></label>
    <span style="font-size:12px;color:#8a9;">clicks are baked in — always in sync</span>
    <span id="timeLbl" style="font-size:12px;color:#9aa;margin-left:auto;">0.00s</span>
  </div>
  <div id="wrap" style="position:relative;">
    <div id="waveform"></div>
    <div id="markers" style="position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;"></div>
  </div>
</div>
<script src="https://unpkg.com/wavesurfer.js@7"></script>
<script>
const AUDIO="__AUDIO__", MARKERS=__MARKERS__, H=__H__;
const ws = WaveSurfer.create({
  container:'#waveform', height:H, waveColor:'#2c4a63', progressColor:'#4d7ea8',
  cursorColor:'#fff', cursorWidth:2, url:AUDIO,
});
const vol=document.getElementById('vol');
let dur=0;
const md=document.getElementById('markers');
function lerpColor(s){ const a=[43,214,198], b=[255,180,84];
  const r=Math.round(a[0]+(b[0]-a[0])*s), g=Math.round(a[1]+(b[1]-a[1])*s), bl=Math.round(a[2]+(b[2]-a[2])*s);
  return `rgb(${r},${g},${bl})`; }
function draw(){
  md.innerHTML=''; if(!dur) return;
  for(const m of MARKERS){
    const el=document.createElement('div');
    el.style.position='absolute'; el.style.left=(m.t/dur*100)+'%'; el.style.bottom='0';
    el.style.width=(1+m.s)+'px'; el.style.height=(25+m.s*75)+'%';
    el.style.background=lerpColor(m.s); el.style.opacity=(0.45+m.s*0.5).toFixed(2);
    md.appendChild(el);
  }
}
ws.on('decode', d=>{ dur=d; draw(); });
ws.on('ready', ()=>{ dur=ws.getDuration(); draw(); ws.setVolume(vol.value/100); });
window.addEventListener('resize', draw);
vol.oninput=()=>ws.setVolume(vol.value/100);

const playBtn=document.getElementById('playBtn');
playBtn.onclick=()=>ws.playPause();
ws.on('play', ()=>{ playBtn.textContent='⏸ Pause'; });
ws.on('pause', ()=>{ playBtn.textContent='▶ Play'; });
ws.on('finish', ()=>{ playBtn.textContent='▶ Play'; });
ws.on('timeupdate', t=>{ document.getElementById('timeLbl').textContent=t.toFixed(2)+'s'; });
</script>
"""
