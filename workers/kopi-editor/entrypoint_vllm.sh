#!/bin/bash
set -e

# Start the vLLM OpenAI server on 8001 in the background; it loads the baked model
# (~1-3 min for a 14B AWQ on an L4). Conservative L4 sizing: short paragraphs need
# little context, so cap it to keep KV cache well within 24 GB.
# Quantization is auto-detected from the model config (AWQ), so we don't force a
# kernel. Short paragraphs need little context; cap it to keep KV cache modest.
#
# A baked QLoRA adapter (/adapter, present only when one was staged at build time)
# is served as the named module `kopi` alongside the base, so one server answers
# both the prompt-only base and the tune — the A/B the editor compares before
# switching its default. --max-lora-rank must be >= the adapter's r (16). When no
# adapter is baked the flags are omitted and the service is base-only as before.
LORA_FLAGS=()
if [ -f /adapter/adapter_config.json ]; then
  echo "serving LoRA adapter 'kopi' from /adapter" >&2
  LORA_FLAGS=(--enable-lora --max-lora-rank 16 --lora-modules kopi=/adapter)
  export KOPI_LORA=kopi
fi

vllm serve "${KOPI_MODEL}" \
  --host 127.0.0.1 --port 8001 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.90 \
  "${LORA_FLAGS[@]}" &

# Bind $PORT immediately with the proxy so Cloud Run's startup probe passes while
# vLLM loads (the proxy returns 503 on /tighten until vLLM /health is ready).
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 0 serve_vllm:app
