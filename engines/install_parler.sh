#!/bin/bash
# Isolated Parler-TTS install. torch/torchaudio CPU pair first, then parler-tts from git.
set -e
cd "$(dirname "$0")"
echo ">>> creating parler venv (py3.11)"
uv venv parler-venv --python 3.11
VP=parler-venv/bin/python
echo ">>> torch+torchaudio matched CPU pair"
uv pip install --python "$VP" --index-url https://download.pytorch.org/whl/cpu torch torchaudio
echo ">>> parler-tts (git) + sentencepiece"
uv pip install --python "$VP" "git+https://github.com/huggingface/parler-tts.git" sentencepiece
echo ">>> import test"
"$VP" -c "from parler_tts import ParlerTTSForConditionalGeneration; from transformers import AutoTokenizer; print('parler import OK')"
echo ">>> PARLER INSTALL COMPLETE"
