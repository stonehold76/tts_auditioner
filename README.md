# TTS Voice Auditioner

**Version 0.9.0**, a release candidate: working and in daily use, on its way to 1.0.

A local, accessible web tool to **browse, hear, shape and export** text-to-speech voices across five
engines, then hand the chosen voice to any other program (a voice assistant, a game bridge, your own
scripts) as a small JSON profile.

Built for low vision: high contrast, follows your light/dark theme, large text, fully keyboard
navigable, and voices are found by typed search rather than long lists.

Everything runs on your own machine. No cloud services, no accounts.

---

## What it does

- **Five engines, about 130 preset voices, plus describe-a-voice:**
  Piper · Kokoro-82M (68 voices, 7 languages) · MeloTTS · XTTS-v2 (58 **built-in speakers only**) ·
  Parler-TTS Mini (**describe a voice in words**).
- **Speed and pitch sliders.** Pitch is formant-preserving (ffmpeg rubberband), so no chipmunk effect.
- **Export and import voice profiles:** save a selection (engine, voice or description, speed, pitch)
  to a portable JSON file, load it back, or hand it to another program.
- **Playback happens in your browser**, so the sound comes out wherever you are.

### No voice cloning, on purpose

XTTS-v2 can clone a voice from a short recording. This tool **does not expose that anywhere**, and
it was never tested. Cloning someone's voice without their consent can't be prevented once the
feature exists, so it's left out. Only XTTS's built-in studio speakers are offered.

---

## Requirements

- Python 3.10 or newer, and **ffmpeg** with the rubberband filter (for pitch).
- Tested on Linux, CPU only. Nothing here needs a GPU, though a GPU makes the heavy engines much faster.
- **You supply the models.** The tool ships no model weights (see [Licensing](#licensing)).

---

## Setup

### 1. Models

Put the models you want under one directory (default `~/models/TTS`), one folder per engine:

```
~/models/TTS/
├── piper/            *.onnx voices (with their .onnx.json files)
├── kokoro/voices/v1_0/*.pt
├── melotts/          checkpoint.pth, config.json
├── parler-tts-mini/  the Parler-TTS Mini v1 model
└── xtts-v2/          the XTTS-v2 model (download it yourself; see Licensing)
```

Engines you don't install are simply skipped.

### 2. Engines

- **Piper:** a virtualenv with `piper-tts` installed (default `~/.local/share/piper-venv`).
- **Kokoro:** a checkout of [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) (default
  `~/Kokoro-FastAPI`). Its virtualenv also runs this app, since it already has FastAPI and uvicorn.
- **MeloTTS, XTTS-v2, Parler:** each runs as a small local service in its own virtualenv under
  `engines/`. Build them with the install scripts:

  ```
  bash engines/install_melotts.sh     # then engines/download_bert.sh for its BERT model
  bash engines/install_xtts.sh
  bash engines/install_parler.sh
  ```

### 3. Configuration

The defaults above can be changed with environment variables:

| Variable | Default | What it points to |
|---|---|---|
| `TTS_AUDITIONER_MODELS` | `~/models/TTS` | the models directory (or pass it as the first argument) |
| `TTS_AUDITIONER_PIPER_PY` | `~/.local/share/piper-venv/bin/python` | Piper's Python |
| `TTS_AUDITIONER_KOKORO_REPO` | `~/Kokoro-FastAPI` | the Kokoro-FastAPI checkout |
| `TTS_AUDITIONER_PROFILES` | `profiles/` next to `app.py` | where voice profiles are saved |
| `TTS_AUDITIONER_PORT` | `7770` | the web page's port |

---

## Running it

```
~/Kokoro-FastAPI/.venv/bin/python app.py
```

Then open **http://127.0.0.1:7770**. Piper works straight away. For the other engines, click the
engine's **"Start … server"** button on the page. They take 30 to 90 seconds to warm up on a CPU.

To start the engine services by hand instead:

| Engine | Port | Command (from this directory) |
|---|---|---|
| Kokoro | 8880 | `cd ~/Kokoro-FastAPI && bash start-cpu.sh` |
| MeloTTS | 7771 | `engines/melotts-venv/bin/python engines/melotts_service.py` |
| XTTS-v2 | 7772 | `engines/xtts-venv/bin/python engines/xtts_service.py` |
| Parler | 7773 | `engines/parler-venv/bin/python engines/parler_service.py` |
| Piper | none | called directly; no service |

Nothing starts by itself after a reboot: start the app, then each engine as you need it.

### How long each engine takes

Measured on a CPU-only machine, per short sentence, after warm-up:

| Engine | Delay | |
|---|---|---|
| Kokoro | about 0.7 s | fast |
| Piper | about 0.9 s | fast, lightweight |
| MeloTTS | about 1 s | fast once warm |
| XTTS-v2 | about 8 s | neural, heavier |
| Parler | about 19 s | describe-a-voice, the slowest |

The first sentence from each engine is slower (model loading and one-time downloads). A GPU cuts the
two heavy engines down dramatically.

---

## Describing a voice for Parler

Parler builds a voice from a description of **vocal qualities**. What it understands: **gender,
pitch, speaking rate, expressiveness** (monotone to animated), **reverberation, and background noise
or audio quality**.

- Include **"very clear audio"** for the cleanest result.
- **Name one of its 34 built-in speakers** to keep the voice consistent between runs, for example:
  *"Jon's voice is monotone yet slightly fast, with a very close recording and almost no background
  noise."* Other speakers include Lea, Gary, Jenna, Mike and Laura.
- **Punctuation shapes the delivery:** commas add small pauses.
- **Accents don't work.** We tried "British" and "New Orleans", and neither had any effect. Regional
  accent isn't something this model was trained to control, so describe tone, pitch, pace,
  expressiveness and audio quality instead.

---

## Voice profiles

Exported profiles are JSON files in `profiles/` (see `profiles/example.json`):

```json
{ "tts_voice_profile": "1", "label": "Example",
  "engine": "piper", "voice": "en_GB-northern_english_male-medium", "description": null,
  "speed": 0.85, "pitch": 1.0, "created": "2026-09-24T00:00:00Z" }
```

Voice-list engines use `voice`; Parler uses `description`. A profile holds everything another program
needs to reproduce the voice: read the JSON and send its fields with your text to the app's
`/api/play` endpoint, which returns WAV audio. To change voices, swap the file; no code changes.

---

## Licensing

There are two separate layers, and they have different licenses:

- **This tool's code** is free software under the AGPL-3.0-or-later (below).
- **Engines and model weights are not included** and keep their own licenses. You install them
  yourself, and you're bound by each one's terms.

| Model | Weights license |
|---|---|
| Kokoro-82M | Apache-2.0 |
| Parler-TTS Mini v1 | Apache-2.0 (code and weights) |
| MeloTTS | MIT |
| Piper | MIT engine; each voice has its own license, depending on its training data |
| **XTTS-v2** | **Coqui Public Model License (CPML), non-commercial** |

**XTTS-v2 is the restricted one.** Download it from its official source and accept the CPML there,
for your own non-commercial use. The XTTS service won't accept the license for you: once you've
read it, set `COQUI_TOS_AGREED=1` in your environment yourself before starting the app (the app's
"Start server" button passes your environment on to the service). This project doesn't distribute it, and "works with XTTS-v2" is a
compatibility statement, not an affiliation with Coqui. Check each model's license at its source
before relying on it; this table is a summary, not legal advice.

---

## Troubleshooting

- **Kokoro, Japanese:** it needs a UniDic dictionary. Don't run `python -m unidic download` (526 MB,
  slow and flaky). Install `unidic-lite` instead, and symlink `unidic/dicdir` to `unidic_lite/dicdir`
  in the Kokoro virtualenv. Mandarin needs nothing extra.
- **MeloTTS:** the PyPI package is broken, so install it from git. torch and torchaudio must be a
  matching CPU pair. If Hugging Face downloads are flaky, the service runs with `HF_HUB_OFFLINE=1`
  once its BERT model is cached.
- **XTTS-v2:** coqui-tts doesn't pull in torch, so install a matching CPU pair yourself. Pin
  `transformers>=4.57,<5.0` (5.x removed a function it uses), and install `coqui-tts[codec]`.
- **No sound?** Playback is in the browser. Check the browser tab isn't muted.

---

## Files

- `app.py`: the web app (page, `/api/play`, `/api/export`, `/api/profiles`, and the engine registry).
- `engines/`: the small engine services and their install scripts. Their virtualenvs are built on
  each machine and never committed.
- `profiles/`: saved voice profiles (only the example is included).

## License

Copyright (C) 2026 Ken (stonehold) and Claudette (Claude Code).

Free software under the **GNU Affero General Public License, version 3 or later** (AGPL-3.0-or-later).
You may use, study, change and share it. If you distribute it, or run a modified version for others
over a network, you must offer them your source code under the same license. See [LICENSE](LICENSE).
