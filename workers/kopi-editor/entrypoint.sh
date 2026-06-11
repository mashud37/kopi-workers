#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &

# Wait until the server accepts requests
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
    sleep 1
done

exec python run.py "$@"
