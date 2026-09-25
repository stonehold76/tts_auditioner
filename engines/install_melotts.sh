#!/bin/bash
# Isolated MeloTTS install — own venv, CPU torch, so it can't disturb the Kokoro venv.
set -e
cd "$(dirname "$0")"
echo ">>> creating melotts venv (py3.11)"
uv venv melotts-venv --python 3.11
VP=melotts-venv/bin/python
echo ">>> installing CPU torch first (avoid the multi-GB CUDA build)"
uv pip install --python "$VP" torch --index-url https://download.pytorch.org/whl/cpu
echo ">>> installing melotts"
uv pip install --python "$VP" melotts
echo ">>> nltk data for English G2P (g2p_en)"
"$VP" - <<'PY' || true
import nltk
for pkg in ["averaged_perceptron_tagger","averaged_perceptron_tagger_eng","cmudict"]:
    try: nltk.download(pkg)
    except Exception as e: print("nltk", pkg, "skip:", e)
PY
echo ">>> import test"
"$VP" -c "from melo.api import TTS; print('melo import OK')"
echo ">>> MELOTTS INSTALL COMPLETE"
