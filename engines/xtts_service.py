#!/usr/bin/env python3
"""XTTS-v2 synthesis service — BUILT-IN SPEAKERS ONLY. stdlib HTTP, :7772.

Loads the LOCAL XTTS-v2 checkpoint and exposes ONLY its preset studio speakers.
By deliberate design it does NOT accept reference audio and has NO voice-cloning path —
see the model's license (Coqui Public Model License) and the README's no-cloning stance.
Runs offline (local checkpoint only).
"""
import os, json, tempfile, wave
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# Coqui asks you to accept its model license (CPML, non-commercial). That choice is yours:
# set COQUI_TOS_AGREED=1 yourself, after reading the license, before starting this service.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

MODEL_DIR = os.path.join(os.path.expanduser(os.environ.get("TTS_AUDITIONER_MODELS", "~/models/TTS")), "xtts-v2")
PORT = 7772

print("XTTS: loading model…", flush=True)
config = XttsConfig()
config.load_json(os.path.join(MODEL_DIR, "config.json"))
model = Xtts.init_from_config(config)
model.load_checkpoint(config, checkpoint_dir=MODEL_DIR, use_deepspeed=False, eval=True)
model.cpu()

speakers = sorted(model.speaker_manager.speakers.keys()) if model.speaker_manager else []
print(f"XTTS ready on :{PORT}. built-in speakers: {len(speakers)}", flush=True)


def _latents(name):
    d = model.speaker_manager.speakers[name]
    return d["gpt_cond_latent"], d["speaker_embedding"]

def write_wav(path, wav, sr=24000):
    data = np.asarray(wav, dtype=np.float32)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)


class H(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/voices":
            self._send(200, "application/json", json.dumps({"voices": speakers}).encode())
        elif self.path == "/health":
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/synthesize":
            self._send(404, "text/plain", b"not found"); return
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or b"{}")
        text = (d.get("text") or "Hello.").strip()
        speaker = d.get("speaker")
        try:
            speed = min(2.0, max(0.5, float(d.get("speed", 1.0))))
        except (TypeError, ValueError):
            speed = 1.0
        if not model.speaker_manager or speaker not in model.speaker_manager.speakers:
            self._send(400, "application/json", json.dumps({"error": "unknown built-in speaker"}).encode()); return
        fd, wavp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            gpt, emb = _latents(speaker)
            with torch.no_grad():
                out = model.inference(text, "en", gpt, emb, temperature=0.7,
                                      speed=speed, enable_text_splitting=True)
            write_wav(wavp, out["wav"])
            with open(wavp, "rb") as f:
                data = f.read()
            self._send(200, "audio/wav", data)
        except Exception as e:
            self._send(500, "application/json", json.dumps({"error": str(e)[:300]}).encode())
        finally:
            try: os.remove(wavp)
            except OSError: pass

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
