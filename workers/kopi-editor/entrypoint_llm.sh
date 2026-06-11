#!/bin/bash
set -e

ollama serve &

until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
    sleep 1
done

exec python cloud_llm.py "$@"
