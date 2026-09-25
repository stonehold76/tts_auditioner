#!/usr/bin/env python3
"""Tiny MeloTTS synthesis service (stdlib HTTP, no extra deps).

Loads the LOCAL MeloTTS checkpoint once and serves synthesis on :7771.
Run with the melotts venv python:  engines/melotts-venv/bin/python engines/melotts_service.py
"""
import os, json, tempfile
# Use only locally-cached HF models — no network calls at synth time (the HF connection resets
# on this box otherwise hang every synthesis). Everything MeloTTS-English needs is cached.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = os.path.expanduser(os.environ.get("TTS_AUDITIONER_MODELS", "~/models/TTS"))
CKPT = os.path.join(MODELS, "melotts", "checkpoint.pth")
CFG  = os.path.join(MODELS, "melotts", "config.json")
LANG = os.environ.get("MELO_LANG", "EN_NEWEST")
PORT = 7771

print("MeloTTS: loading model…", flush=True)
from melo.api import TTS
model = TTS(language=LANG, device="cpu", config_path=CFG, ckpt_path=CKPT)
spk2id = dict(model.hps.data.spk2id)
print(f"MeloTTS ready on :{PORT}. voices: {list(spk2id)}", flush=True)


class H(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/voices":
            self._send(200, "application/json", json.dumps({"voices": list(spk2id)}).encode())
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
        sid = spk2id.get(speaker, list(spk2id.values())[0])
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            model.tts_to_file(text, sid, wav, speed=speed)
            with open(wav, "rb") as f:
                data = f.read()
            self._send(200, "audio/wav", data)
        except Exception as e:
            self._send(500, "application/json", json.dumps({"error": str(e)[:300]}).encode())
        finally:
            try: os.remove(wav)
            except OSError: pass

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
