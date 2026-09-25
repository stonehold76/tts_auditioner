#!/bin/bash
# Fully cache bert-base-uncased (MeloTTS English) despite flaky HF connection resets.
cd "$(dirname "$0")"
VP=melotts-venv/bin/python
for i in $(seq 1 12); do
  echo ">>> attempt $i"
  "$VP" - <<'PY'
import sys
from huggingface_hub import snapshot_download
try:
    p = snapshot_download(
        "bert-base-uncased",
        allow_patterns=["config.json","tokenizer_config.json","tokenizer.json","vocab.txt","*.safetensors"],
        max_workers=2,
    )
    print(">>> BERT DOWNLOAD COMPLETE", p)
    sys.exit(0)
except Exception as e:
    print("attempt failed:", str(e)[:200]); sys.exit(1)
PY
  [ $? -eq 0 ] && exit 0
  echo "…retrying after reset"; sleep 4
done
echo ">>> BERT DOWNLOAD GAVE UP"
