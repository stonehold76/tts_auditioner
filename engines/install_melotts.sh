#!/bin/bash
# Isolated MeloTTS install: its own venv and CPU torch, so it can't disturb any other engine.
# MeloTTS comes from its GitHub repo because the PyPI sdist is broken. --torch-backend cpu makes
# uv fetch the CPU builds of torch/torchaudio instead of the multi-GB CUDA ones from PyPI.
# MeloTTS's librosa 0.9 still imports pkg_resources, which setuptools 81 dropped, so hold it below.
# Safe to re-run: the venv is kept and uv only fetches what's missing.
set -e
cd "$(dirname "$0")"
echo ">>> creating melotts venv (py3.11)"
uv venv melotts-venv --python 3.11 --allow-existing
VP=melotts-venv/bin/python
echo ">>> installing MeloTTS (from git) with CPU torch"
uv pip install --python "$VP" --torch-backend cpu "melotts @ git+https://github.com/myshell-ai/MeloTTS.git" "setuptools<81"
echo ">>> Japanese dictionary: point unidic at the bundled unidic-lite (skips a ~500 MB download)"
# MeloTTS imports its Japanese text module even for English, and MeCab fails without a dictionary.
SP=$("$VP" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
[ -e "$SP/unidic/dicdir" ] || ln -s ../unidic_lite/dicdir "$SP/unidic/dicdir"
echo ">>> nltk data for English G2P (g2p_en)"
"$VP" - <<'PY' || true
import nltk
for pkg in ["averaged_perceptron_tagger","averaged_perceptron_tagger_eng","cmudict"]:
    try: nltk.download(pkg)
    except Exception as e: print("nltk", pkg, "skip:", e)
PY
echo ">>> import test"
"$VP" -c "from melo.api import TTS; print('melo import OK')"
echo ">>> BERT model for English (retries on flaky connections)"
bash download_bert.sh
echo ">>> MELOTTS INSTALL COMPLETE"
