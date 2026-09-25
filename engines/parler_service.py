#!/usr/bin/env python3
"""Parler-TTS Mini service — describe a voice in words, it conjures one. stdlib HTTP, :7773.

POST /synthesize {description, text} -> WAV. No preset voices; the 'description' string
(e.g. "A warm, unhurried woman with a slight rasp, very clear audio") shapes the voice.
Loads the LOCAL checkpoint. Left ONLINE for first run in case the DAC codec needs fetching.
"""
import os, json, tempfile, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import torch
from parler_tts import ParlerTTSForConditionalGeneration
from transformers import AutoTokenizer

MODEL_DIR = os.path.join(os.path.expanduser(os.environ.get("TTS_AUDITIONER_MODELS", "~/models/TTS")), "parler-tts-mini")
PORT = 7773

print("Parler: loading model…", flush=True)
model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL_DIR)
model.eval()
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
SR = model.config.sampling_rate
print(f"Parler ready on :{PORT}. sampling_rate={SR}", flush=True)


def write_wav(path, wav, sr):
    data = np.asarray(wav, dtype=np.float32)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr)); w.writeframes(pcm)


class H(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, "application/json", b'{"ok":true}')
        elif self.path == "/voices":
            self._send(200, "application/json", b'{"voices":[]}')
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/synthesize":
            self._send(404, "text/plain", b"not found"); return
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or b"{}")
        text = (d.get("text") or "Hello.").strip()
        desc = (d.get("description") or "A clear, neutral voice speaking at a natural pace.").strip()
        fd, wavp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            input_ids = tokenizer(desc, return_tensors="pt").input_ids
            prompt_ids = tokenizer(text, return_tensors="pt").input_ids
            with torch.no_grad():
                audio = model.generate(input_ids=input_ids, prompt_input_ids=prompt_ids)
            arr = audio.cpu().numpy().squeeze()
            write_wav(wavp, arr, SR)
            with open(wavp, "rb") as f:
                data = f.read()
            self._send(200, "audio/wav", data)
        except Exception as e:
            self._send(500, "application/json", json.dumps({"error": str(e)[:400]}).encode())
        finally:
            try: os.remove(wavp)
            except OSError: pass

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
