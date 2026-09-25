#!/usr/bin/env python3
"""TTS Voice Auditioner — point it at a models/TTS directory, browse and hear the voices.

Built for low vision: high-contrast dark UI, large text, keyboard-navigable, voices found by
typed search. Playback is in the BROWSER (endpoint returns WAV bytes) so it comes out where the
user is, not the server's audio session.

Engines that need a running backend (Kokoro, MeloTTS, …) are handled via a small SERVERS registry:
each can be checked for health and started on demand from the UI.

Run:  Kokoro-venv-python app.py  [TTS_DIR]   → http://127.0.0.1:7770
"""
import os, sys, glob, json, re, time, tempfile, threading, subprocess, urllib.request
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

APP_DIR = os.path.dirname(os.path.abspath(__file__))
env = lambda name, default: os.path.expanduser(os.environ.get(name, default))

# Where things live. Defaults suit a typical install; override any of them with the environment
# variable shown (or pass the models directory as the first argument).
TTS_DIR = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else env("TTS_AUDITIONER_MODELS", "~/models/TTS")
PIPER_PY = env("TTS_AUDITIONER_PIPER_PY", "~/.local/share/piper-venv/bin/python")
KOKORO_REPO = env("TTS_AUDITIONER_KOKORO_REPO", "~/Kokoro-FastAPI")
ENGINES_DIR = os.path.join(APP_DIR, "engines")
MELO_PY = os.path.join(ENGINES_DIR, "melotts-venv/bin/python")
MELO_SERVICE = os.path.join(ENGINES_DIR, "melotts_service.py")
XTTS_PY = os.path.join(ENGINES_DIR, "xtts-venv/bin/python")
XTTS_SERVICE = os.path.join(ENGINES_DIR, "xtts_service.py")
PARLER_PY = os.path.join(ENGINES_DIR, "parler-venv/bin/python")
PARLER_SERVICE = os.path.join(ENGINES_DIR, "parler_service.py")
PORT = int(os.environ.get("TTS_AUDITIONER_PORT", "7770"))
PROFILES_DIR = env("TTS_AUDITIONER_PROFILES", os.path.join(APP_DIR, "profiles"))
os.makedirs(PROFILES_DIR, exist_ok=True)

app = FastAPI()
_play_lock = threading.Lock()

# Non-English Kokoro voices are named by language prefix (j=Japanese, z=Mandarin, e=Spanish,
# f=French, h=Hindi, i=Italian, p=Portuguese). English text won't demo them, so audition each
# with a short native sample. (a/b = English → use the user's own text.)
KOKORO_SAMPLES = {
    "j": "こんにちは。今日はいい天気ですね。",
    "z": "你好，今天天气很好。",
    "e": "Hola, ¿cómo estás hoy?",
    "f": "Bonjour, comment allez-vous aujourd'hui ?",
    "h": "नमस्ते, आप कैसे हैं?",
    "i": "Ciao, come stai oggi?",
    "p": "Olá, como você está hoje?",
}

# Engines that run as a backend service: how to health-check and how to launch on demand.
SERVERS = {
    "kokoro": {
        "url": "http://localhost:8880", "health": "/v1/audio/voices",
        "cmd": ["bash", "start-cpu.sh"], "cwd": KOKORO_REPO,
        "log": "/tmp/claude-1000/kokoro-audition.log",
    },
    "melotts": {
        "url": "http://localhost:7771", "health": "/health",
        "cmd": [MELO_PY, MELO_SERVICE], "cwd": ENGINES_DIR,
        "log": "/tmp/claude-1000/melotts-service.log",
    },
    "xtts": {
        "url": "http://localhost:7772", "health": "/health",
        "cmd": [XTTS_PY, XTTS_SERVICE], "cwd": ENGINES_DIR,
        "log": "/tmp/claude-1000/xtts-service.log",
    },
    "parler": {
        "url": "http://localhost:7773", "health": "/health",
        "cmd": [PARLER_PY, PARLER_SERVICE], "cwd": ENGINES_DIR,
        "log": "/tmp/claude-1000/parler-service.log",
    },
}


def server_up(key):
    s = SERVERS[key]
    try:
        urllib.request.urlopen(s["url"] + s["health"], timeout=3)
        return True
    except Exception:
        return False


def start_server(key):
    s = SERVERS[key]
    if server_up(key):
        return {"ok": True, "msg": "already running"}
    try:
        logf = open(s["log"], "ab")
        subprocess.Popen(s["cmd"], cwd=s["cwd"], stdout=logf, stderr=logf, start_new_session=True)
        return {"ok": True, "msg": "starting"}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:300]}


# ---------- voice discovery ----------
def piper_voices():
    """One entry per voice. Multi-speaker models (vctk, arctic, aru, ...) expand to one entry per
    speaker as "model#speaker", so each speaker can be auditioned and exported on its own."""
    out = []
    for p in sorted(glob.glob(os.path.join(TTS_DIR, "piper", "*.onnx"))):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            with open(p + ".json") as f:
                speakers = json.load(f).get("speaker_id_map") or {}
        except (OSError, ValueError):
            speakers = {}
        if len(speakers) > 1:
            out += [f"{name}#{spk}" for spk in sorted(speakers, key=lambda k: speakers[k])]
        else:
            out.append(name)
    return out

def kokoro_voices():
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(TTS_DIR, "kokoro", "voices", "v1_0", "*.pt")))

def melotts_voices():
    if server_up("melotts"):
        try:
            with urllib.request.urlopen(SERVERS["melotts"]["url"] + "/voices", timeout=3) as r:
                return json.load(r).get("voices", [])
        except Exception:
            pass
    # weights present but service down: name what the checkpoint carries
    return ["EN-Newest"] if present("melotts") else []

def xtts_voices():
    if server_up("xtts"):
        try:
            with urllib.request.urlopen(SERVERS["xtts"]["url"] + "/voices", timeout=3) as r:
                return json.load(r).get("voices", [])
        except Exception:
            pass
    return []  # built-in speakers only load once the service is up

def present(sub):
    p = os.path.join(TTS_DIR, sub)
    return os.path.isdir(p) and any(os.scandir(p))


def state():
    ku, mu = server_up("kokoro"), server_up("melotts")
    engines = [
        {"key": "piper", "name": "Piper", "voices": piper_voices(), "playable": True, "note": "", "start": None},
        {"key": "kokoro", "name": "Kokoro-82M", "voices": kokoro_voices(), "playable": ku,
         "note": "" if ku else "server offline — start it to hear these 68 voices",
         "start": None if ku else "kokoro"},
    ]
    if present("melotts"):
        engines.append({"key": "melotts", "name": "MeloTTS", "voices": melotts_voices(), "playable": mu,
                        "note": "" if mu else "server offline — start it to hear this voice",
                        "start": None if mu else "melotts"})
    if present("xtts-v2_DO-NOT-PUBLISH"):
        xu = server_up("xtts")
        engines.append({"key": "xtts", "name": "XTTS-v2 (speakers-only)", "voices": xtts_voices(), "playable": xu,
                        "note": "" if xu else "server offline — start it to load the built-in speakers (XTTS is slow on CPU)",
                        "start": None if xu else "xtts"})
    if present("parler-tts-mini"):
        pu = server_up("parler")
        engines.append({"key": "parler", "name": "Parler-TTS Mini", "voices": [], "playable": pu,
                        "kind": "describe",
                        "note": "" if pu else "server offline — start it, then describe a voice (slow on CPU)",
                        "start": None if pu else "parler"})
    return {"tts_dir": TTS_DIR, "engines": engines}


# ---------- synthesis ----------
def synth_piper(voice, text, wav, speed=1.0):
    name, _, spk = voice.partition("#")
    model = os.path.join(TTS_DIR, "piper", name + ".onnx")
    length_scale = round(1.0 / speed, 3) if speed else 1.0  # piper: higher length-scale = slower
    extra = []
    if spk:
        with open(model + ".json") as f:
            extra = ["--speaker", str(json.load(f)["speaker_id_map"][spk])]
    p = subprocess.run([PIPER_PY, "-m", "piper", "-m", model, "--length-scale", str(length_scale), *extra, "-f", wav],
                       input=text.encode(), capture_output=True, timeout=120)
    if p.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError((p.stderr.decode() or "piper failed")[:300])

def _post_wav(url, payload, wav):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        ct = r.headers.get("Content-Type", "")
        data = r.read()
    if "audio" not in ct:
        raise RuntimeError((json.loads(data).get("error") if data else "no audio") or "synthesis failed")
    with open(wav, "wb") as f:
        f.write(data)

def synth_kokoro(voice, text, wav, speed=1.0):
    _post_wav(SERVERS["kokoro"]["url"] + "/v1/audio/speech",
              {"model": "kokoro", "voice": voice, "input": text, "response_format": "wav", "speed": speed}, wav)

def synth_melotts(voice, text, wav, speed=1.0):
    _post_wav(SERVERS["melotts"]["url"] + "/synthesize", {"speaker": voice, "text": text, "speed": speed}, wav)

def synth_xtts(voice, text, wav, speed=1.0):
    _post_wav(SERVERS["xtts"]["url"] + "/synthesize", {"speaker": voice, "text": text, "speed": speed}, wav)

def synth_parler(description, text, wav):
    _post_wav(SERVERS["parler"]["url"] + "/synthesize", {"description": description, "text": text}, wav)

def apply_pitch(src_wav, pitch):
    """Formant-preserving pitch shift via ffmpeg rubberband. Universal post-process for any engine.
    Returns a new wav path, or the original if pitch≈1.0 or the shift fails."""
    if abs(pitch - 1.0) < 1e-3:
        return src_wav
    out = tempfile.mktemp(suffix=".wav", dir="/tmp/claude-1000")
    p = subprocess.run(["ffmpeg", "-y", "-i", src_wav, "-af",
                        f"rubberband=pitch={pitch:.3f}:formant=preserved",
                        "-c:a", "pcm_s16le", out],
                       capture_output=True, timeout=120)
    if p.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        try: os.remove(out)
        except OSError: pass
        return src_wav
    return out


@app.get("/api/state")
def api_state():
    return JSONResponse(state())

@app.get("/api/server/status/{key}")
def api_server_status(key: str):
    return {"up": server_up(key)} if key in SERVERS else JSONResponse({"up": False}, status_code=404)

@app.post("/api/server/start/{key}")
def api_server_start(key: str):
    if key not in SERVERS:
        return JSONResponse({"ok": False, "msg": "unknown server"}, status_code=404)
    return start_server(key)

@app.post("/api/play")
async def api_play(request: Request):
    """Synthesize and return WAV bytes so the BROWSER plays it (in the user's session)."""
    d = await request.json()
    engine, voice, text = d.get("engine"), d.get("voice"), (d.get("text") or "").strip()
    try:
        speed = min(1.5, max(0.5, float(d.get("speed", 1.0))))
    except (TypeError, ValueError):
        speed = 1.0
    try:
        pitch = min(1.5, max(0.5, float(d.get("pitch", 1.0))))
    except (TypeError, ValueError):
        pitch = 1.0
    if not text:
        text = "Hello. This is a sample of my voice."
    if engine == "kokoro" and voice and voice[0] in KOKORO_SAMPLES:
        text = KOKORO_SAMPLES[voice[0]]  # non-English voice → native sample
    synths = {"piper": synth_piper, "kokoro": synth_kokoro, "melotts": synth_melotts, "xtts": synth_xtts}
    if engine not in synths and engine != "parler":
        return JSONResponse({"ok": False, "msg": f"{engine} is not playable yet"}, status_code=400)
    if not _play_lock.acquire(blocking=False):
        return JSONResponse({"ok": False, "msg": "still synthesizing the last one — try again"}, status_code=429)
    wav = tempfile.mktemp(suffix=".wav", dir="/tmp/claude-1000")
    shifted = None
    try:
        if engine == "parler":
            synth_parler(d.get("description") or "A clear, neutral voice speaking at a natural pace.", text, wav)
        else:
            synths[engine](voice, text, wav, speed)
        final = apply_pitch(wav, pitch)
        shifted = final if final != wav else None
        with open(final, "rb") as f:
            data = f.read()
        return Response(content=data, media_type="audio/wav")
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)[:300]}, status_code=500)
    finally:
        for pth in (wav, shifted):
            if pth:
                try: os.remove(pth)
                except OSError: pass
        _play_lock.release()


@app.post("/api/export")
async def api_export(request: Request):
    """Save the current voice selection (engine + voice/description + speed + pitch) as a portable
    JSON profile that any interface can import to reproduce the voice."""
    d = await request.json()
    engine = d.get("engine")
    if not engine:
        return JSONResponse({"ok": False, "msg": "nothing selected yet — play a voice first"}, status_code=400)
    voice = d.get("voice")
    description = d.get("description")
    try: speed = round(float(d.get("speed", 1.0)), 3)
    except (TypeError, ValueError): speed = 1.0
    try: pitch = round(float(d.get("pitch", 1.0)), 3)
    except (TypeError, ValueError): pitch = 1.0
    label = (d.get("label") or voice or "described-voice").strip()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-").lower() or "voice"
    profile = {
        "tts_voice_profile": "1", "label": label, "engine": engine,
        "voice": voice, "description": description, "speed": speed, "pitch": pitch,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = os.path.join(PROFILES_DIR, slug + ".json")
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)
    return {"ok": True, "path": path, "filename": slug + ".json"}


@app.get("/api/profiles")
def api_profiles():
    out = []
    for fn in sorted(os.listdir(PROFILES_DIR)):
        if fn.endswith(".json"):
            try:
                p = json.load(open(os.path.join(PROFILES_DIR, fn)))
                p["filename"] = fn
                out.append(p)
            except Exception:
                pass
    return {"profiles": out}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TTS Voice Auditioner</title>
<style>
  :root{
    color-scheme: light dark;   /* follow the system/browser theme */
    --bg:#ffffff; --fg:#141414; --muted:#555555; --panel:#f2f2f2;
    --line:#c8c8c8; --accent:#8a6d00; --accent2:#065f7a;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --bg:#0a0a0a; --fg:#f4f4f4; --muted:#c2c2c2; --panel:#181818;
      --line:#3a3a3a; --accent:#ffd400; --accent2:#66d9ff;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
    font-family:system-ui,"DejaVu Sans",Arial,sans-serif;font-size:20px;line-height:1.6;
    padding:24px;max-width:1100px;margin:0 auto}
  h1{font-size:34px;margin:0 0 4px}
  .dir{color:var(--muted);font-size:16px;word-break:break-all;margin-bottom:20px}
  label{display:block;font-size:18px;color:var(--muted);margin:14px 0 6px}
  input[type=text],textarea{width:100%;font-size:22px;padding:14px;background:var(--panel);
    color:var(--fg);border:2px solid var(--line);border-radius:8px}
  input[type=range]{width:100%;height:38px;accent-color:var(--accent);cursor:pointer}
  select{font-size:20px;padding:10px;background:var(--panel);color:var(--fg);
    border:2px solid var(--line);border-radius:8px;max-width:100%}
  #selpanel{margin:18px 0;padding:16px;border:2px solid var(--line);border-radius:10px;background:var(--panel)}
  #cursel{font-size:22px;margin:6px 0 12px}
  hr{border:none;border-top:2px solid var(--line);margin:16px 0}
  .rangeends{display:flex;justify-content:space-between;color:var(--muted);
    font-size:15px;margin:2px 2px 4px}
  input:focus,textarea:focus,button:focus{outline:4px solid var(--accent);outline-offset:2px}
  #status{position:sticky;top:0;background:var(--bg);padding:16px 4px;font-size:22px;
    border-bottom:2px solid var(--line);margin-bottom:16px;z-index:5}
  .section{margin:26px 0}
  .section h2{font-size:26px;border-bottom:2px solid var(--line);padding-bottom:6px}
  .count{color:var(--muted);font-size:18px;font-weight:normal}
  .note{color:var(--accent);font-size:18px;margin:6px 0}
  .voices{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}
  button.voice{font-size:20px;padding:14px 18px;background:var(--panel);color:var(--fg);
    border:2px solid var(--line);border-radius:8px;cursor:pointer;text-align:left}
  button.voice:hover{border-color:var(--accent2)}
  button.voice[hidden]{display:none}
  button.kbtn{font-size:20px;padding:12px 18px;background:#243b12;color:#eaffea;
    border:2px solid #4a7d24;border-radius:8px;cursor:pointer;margin-top:10px}
  .notplayable{opacity:.75;font-style:italic;color:var(--muted)}
  .hint{color:var(--muted);font-size:16px;margin-top:6px}
</style></head><body>
<h1>TTS Voice Auditioner</h1>
<div class="dir" id="dir"></div>
<div id="status">Loading…</div>

<label for="sample">Sample sentence (spoken when you pick a voice)</label>
<textarea id="sample" rows="2">Hello. This is a sample of my voice, so you can hear how I sound.</textarea>
<div class="hint">Non-English voices (Japanese, Mandarin, Spanish, French…) ignore this box and speak a built-in sample in their own language.</div>

<label for="speed">Speed — <span id="speedval">1.00×</span> &nbsp;(drag left for a slower, calmer cadence)</label>
<input type="range" id="speed" min="0.5" max="1.5" step="0.05" value="1.0">
<div class="rangeends"><span>← 0.5× slower</span><span>normal 1.0×</span><span>1.5× faster →</span></div>

<label for="pitch">Pitch — <span id="pitchval">1.00×</span> &nbsp;(formant-preserving — natural, no chipmunk)</label>
<input type="range" id="pitch" min="0.5" max="1.5" step="0.05" value="1.0">
<div class="rangeends"><span>← 0.5× lower</span><span>normal 1.0×</span><span>1.5× higher →</span></div>

<div id="selpanel">
  <div style="font-size:18px;color:var(--muted)">Your selection</div>
  <div id="cursel">— click a voice below to select it —</div>
  <input type="text" id="explabel" placeholder="name this voice (optional)" style="margin-bottom:10px">
  <button id="exportbtn" class="kbtn">⭳ Export selection to a profile file</button>
  <div id="exportmsg" class="hint"></div>
  <hr>
  <label for="profsel">Import a saved profile (loads its speed/pitch and plays it)</label>
  <select id="profsel"><option value="">(loading…)</option></select>
  <button id="loadbtn" class="kbtn">⭱ Load &amp; play</button>
</div>

<label for="filter">Filter voices — type to narrow the list</label>
<input type="text" id="filter" placeholder="e.g. alba, bf_, british…" autocomplete="off">
<div class="hint">Tab to a voice and press Enter to hear it. Only one plays at a time.</div>

<div id="engines"></div>

<script>
const $ = s => document.querySelector(s);
function setStatus(t){ $("#status").textContent = t; }

let audioEl = null;
let currentSel = null;
async function play(engine, voice, extra){
  const label = voice || (extra && extra.description ? "described voice" : engine);
  currentSel = {engine, voice: voice || null, description: (extra && extra.description) || null};
  const cs = document.getElementById("cursel");
  if(cs) cs.textContent = "Selected: " + engine + " / " + label +
    (currentSel.description ? '  — "' + currentSel.description.slice(0,70) + '"' : "");
  setStatus("… synthesizing — " + engine + " / " + label + " (some engines are slow on CPU)");
  try{
    if(audioEl){ audioEl.pause(); audioEl = null; }
    const body = Object.assign({engine, voice, text:$("#sample").value, speed:parseFloat($("#speed").value), pitch:pitchVal()}, extra||{});
    const r = await fetch("/api/play",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)});
    const ct = r.headers.get("content-type") || "";
    if(!r.ok || !ct.includes("audio")){
      let msg = "error " + r.status; try{ msg = (await r.json()).msg; }catch(_){}
      setStatus("✕ " + msg); return;
    }
    const blob = await r.blob();
    audioEl = new Audio(URL.createObjectURL(blob));
    audioEl.onended = ()=> setStatus("✓ done — " + engine + " / " + label);
    audioEl.onerror = ()=> setStatus("✕ browser could not play the audio");
    setStatus("▶ PLAYING — " + engine + " / " + label);
    await audioEl.play();
  }catch(e){ setStatus("✕ error: " + e); }
}

async function startServer(key, name){
  setStatus("… starting " + name + " server (CPU). First start can take 30–90s to warm up.");
  await fetch("/api/server/start/" + key, {method:"POST"});
  const poll = setInterval(async ()=>{
    const d = await (await fetch("/api/server/status/" + key)).json();
    if(d.up){ clearInterval(poll); setStatus("✓ " + name + " server up — reloading voices."); load(); }
  }, 4000);
}

function render(st){
  $("#dir").textContent = "Pointed at: " + st.tts_dir;
  const box = $("#engines"); box.innerHTML = "";
  for(const e of st.engines){
    const sec = document.createElement("div"); sec.className = "section";
    const h = document.createElement("h2");
    h.innerHTML = e.name + ' <span class="count">' +
      (e.voices.length ? e.voices.length + (e.voices.length===1?" voice":" voices") : "") + '</span>';
    sec.appendChild(h);
    if(e.note){ const n=document.createElement("div"); n.className="note"; n.textContent="⚠ "+e.note; sec.appendChild(n); }
    if(e.start){
      const b=document.createElement("button"); b.className="kbtn";
      b.textContent="▶ Start " + e.name + " server";
      b.onclick=()=>startServer(e.start, e.name); sec.appendChild(b);
    }
    if(e.kind === "describe" && e.playable){
      const lbl=document.createElement("label"); lbl.setAttribute("for","desc-"+e.key);
      lbl.textContent='Describe the voice — e.g. "a warm, unhurried woman with a slight rasp, very clear audio"';
      const ta=document.createElement("textarea"); ta.id="desc-"+e.key; ta.rows=2;
      ta.value="A warm, clear female voice speaking at a natural, calm pace, with very clear audio.";
      const b=document.createElement("button"); b.className="kbtn";
      b.textContent="▶ Speak in this described voice";
      b.onclick=()=>play(e.key, null, {description: document.getElementById("desc-"+e.key).value});
      sec.appendChild(lbl); sec.appendChild(ta); sec.appendChild(b);
    }else if(e.playable && e.voices.length){
      const vs=document.createElement("div"); vs.className="voices";
      for(const v of e.voices){
        const b=document.createElement("button"); b.className="voice"; b.textContent="▶ "+v;
        b.dataset.name=v.toLowerCase(); b.onclick=()=>play(e.key, v);
        vs.appendChild(b);
      }
      sec.appendChild(vs);
    }else if(!e.playable && !e.start && e.voices.length===0){
      const n=document.createElement("div"); n.className="notplayable"; n.textContent="(not playable yet)";
      sec.appendChild(n);
    }
    box.appendChild(sec);
  }
  applyFilter();
}

function applyFilter(){
  const q = $("#filter").value.trim().toLowerCase();
  document.querySelectorAll("button.voice").forEach(b=>{
    b.hidden = q && !b.dataset.name.includes(q);
  });
}
$("#filter").addEventListener("input", applyFilter);
$("#speed").addEventListener("input", ()=>{ $("#speedval").textContent = parseFloat($("#speed").value).toFixed(2)+"×"; });
$("#pitch").addEventListener("input", ()=>{ $("#pitchval").textContent = parseFloat($("#pitch").value).toFixed(2)+"×"; });

function pitchVal(){ const p=document.getElementById("pitch"); return p?parseFloat(p.value):1.0; }

async function exportSel(){
  if(!currentSel){ $("#exportmsg").textContent="✕ play a voice below first to select it."; return; }
  const body = Object.assign({}, currentSel,
    {speed:parseFloat($("#speed").value), pitch:pitchVal(), label:$("#explabel").value});
  try{
    const d = await (await fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)})).json();
    $("#exportmsg").textContent = d.ok ? ("✓ saved to  " + d.path) : ("✕ " + d.msg);
    if(d.ok) loadProfiles();
  }catch(e){ $("#exportmsg").textContent = "✕ " + e; }
}

async function loadProfiles(){
  try{
    const d = await (await fetch("/api/profiles")).json();
    window._profiles = d.profiles || [];
    const sel = $("#profsel"); sel.innerHTML = "";
    if(!window._profiles.length){
      const o=document.createElement("option"); o.value=""; o.textContent="(no saved profiles yet)"; sel.appendChild(o); return;
    }
    window._profiles.forEach((p,i)=>{ const o=document.createElement("option"); o.value=i;
      o.textContent = p.label + "  —  " + p.engine + (p.voice ? ("/"+p.voice) : "") + "  @ " + p.speed + "×";
      sel.appendChild(o); });
  }catch(e){}
}

function loadSel(){
  const i = $("#profsel").value; if(i==="") return;
  const p = window._profiles[parseInt(i)];
  $("#speed").value = p.speed; $("#speedval").textContent = parseFloat(p.speed).toFixed(2)+"×";
  const pit=document.getElementById("pitch");
  if(pit && p.pitch!=null){ pit.value=p.pitch; const pv=document.getElementById("pitchval"); if(pv) pv.textContent=parseFloat(p.pitch).toFixed(2)+"×"; }
  play(p.engine, p.voice, p.description ? {description:p.description} : null);
}

$("#exportbtn").addEventListener("click", exportSel);
$("#loadbtn").addEventListener("click", loadSel);

async function load(){
  setStatus("Loading voices…");
  const st = await (await fetch("/api/state")).json();
  render(st);
  loadProfiles();
  const total = st.engines.reduce((a,e)=>a+(e.playable?e.voices.length:0),0);
  setStatus("Ready — " + total + " voices playable right now. Pick one to hear it.");
}
load();
</script>
</body></html>"""

if __name__ == "__main__":
    import uvicorn
    print(f"TTS Auditioner on http://127.0.0.1:{PORT}  (TTS dir: {TTS_DIR})")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
