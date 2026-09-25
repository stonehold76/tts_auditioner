#!/bin/bash
# MeloTTS install v2 — from the GitHub repo (PyPI sdist is broken). Into the existing venv.
set -e
cd "$(dirname "$0")"
VP=melotts-venv/bin/python
echo ">>> numpy first (torch needs it)"
uv pip install --python "$VP" numpy
echo ">>> MeloTTS from git"
uv pip install --python "$VP" "git+https://github.com/myshell-ai/MeloTTS.git"
echo ">>> nltk english G2P data"
"$VP" - <<'PY' || true
import nltk
for pkg in ["averaged_perceptron_tagger","averaged_perceptron_tagger_eng","cmudict"]:
    try: nltk.download(pkg)
    except Exception as e: print("nltk", pkg, "skip:", e)
PY
echo ">>> import test"
"$VP" -c "from melo.api import TTS; print('melo import OK')"
echo ">>> MELOTTS INSTALL COMPLETE"
