#!/bin/bash
# Isolated XTTS-v2 (Coqui TTS) install. torch/torchaudio from the CPU index (primary) so they
# come as a matched CPU pair; coqui-tts + the rest from PyPI (extra index). Avoids the ABI trap.
set -e
cd "$(dirname "$0")"
echo ">>> creating xtts venv (py3.11)"
uv venv xtts-venv --python 3.11
VP=xtts-venv/bin/python
echo ">>> installing coqui-tts with CPU torch pair"
uv pip install --python "$VP" \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple \
  coqui-tts
echo ">>> import test (low-level Xtts, no TOS/download path)"
"$VP" -c "from TTS.tts.models.xtts import Xtts; from TTS.tts.configs.xtts_config import XttsConfig; print('xtts import OK')"
echo ">>> XTTS INSTALL COMPLETE"
