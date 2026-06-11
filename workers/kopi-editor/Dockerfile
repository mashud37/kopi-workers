FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless curl ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Ollama binary (no systemd needed — we start it in the entrypoint)
RUN curl -L "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64" \
    -o /usr/local/bin/ollama && chmod +x /usr/local/bin/ollama

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
RUN python -c "import language_tool_python; language_tool_python.LanguageTool('en-GB')" || true

COPY kopi/ ./kopi/
COPY run.py cloud/cloud_llm.py entrypoint.sh entrypoint_llm.sh ./
RUN chmod +x entrypoint.sh entrypoint_llm.sh

COPY data/ ./data/

# Bake the model into the image so Cloud Run jobs don't pull on every cold start.
# Override at build time: docker build --build-arg KOPI_MODEL=qwen2.5:7b .
ARG KOPI_MODEL=qwen2.5:3b
ENV KOPI_MODEL=${KOPI_MODEL}
RUN ollama serve & sleep 10 && ollama pull ${KOPI_MODEL} && pkill -f "ollama serve" || true

ENTRYPOINT ["./entrypoint.sh"]
