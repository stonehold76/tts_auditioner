#!/bin/bash
# Isolated XTTS-v2 (Coqui TTS) install. coqui-tts lists torch under its [cpu] extra, and torchaudio
# needs torchcodec ([codec]) to load audio. --torch-backend cpu makes uv fetch the matched CPU builds
# of all three; without it the extra index route pulls the multi-GB CUDA torch from PyPI.
# transformers 5 removed helpers coqui-tts 0.27 still imports, so hold it to 4.x.
set -e
cd "$(dirname "$0")"
echo ">>> creating xtts venv (py3.11)"
uv venv xtts-venv --python 3.11 --allow-existing
VP=xtts-venv/bin/python
echo ">>> installing coqui-tts with CPU torch pair"
uv pip install --python "$VP" --torch-backend cpu "coqui-tts[cpu,codec]" "transformers<5"
echo ">>> import test (low-level Xtts, no TOS/download path)"
"$VP" -c "from TTS.tts.models.xtts import Xtts; from TTS.tts.configs.xtts_config import XttsConfig; print('xtts import OK')"
echo ">>> XTTS INSTALL COMPLETE"
