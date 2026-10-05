#!/bin/bash
set -e

ollama serve &

# Warm the model in the BACKGROUND once Ollama is up. The web server must bind
# $PORT immediately so the container passes Cloud Run's startup check — blocking
# here on the GPU model load (or on Ollama readiness) is what fails the deploy.
(
    until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do sleep 1; done
    ollama run "${KOPI_MODEL}" "ok" >/dev/null 2>&1 || true
) &

exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 0 serve:app
