FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless curl ca-certificates wget zstd xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama via the official installer, but PINNED to a stable version.
# The latest builds ship brand-new CUDA kernels (PDL / fused Gated Delta Net)
# that Cloud Run's L4 GPU driver can't load ("device kernel image is invalid").
# CUDA is backward- but not forward-compatible, so a pinned older Ollama runs
# fine on the host driver. Bump only after confirming GPU compat on Cloud Run.
ARG OLLAMA_VERSION=0.5.13
RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=${OLLAMA_VERSION} sh \
    && ollama --version

# Bake the model into the image FIRST (the big, slow layer) so later changes to
# dependencies or app code don't re-pull it on a rebuild. A failed pull now fails
# the build (no `|| true` masking a broken Ollama).
# Override at build time: docker build --build-arg KOPI_MODEL=gemma3:4b .
ARG KOPI_MODEL=qwen2.5:7b
ENV KOPI_MODEL=${KOPI_MODEL}
RUN ollama serve & sleep 8 && ollama pull ${KOPI_MODEL} && (pkill -f "ollama serve" || true)

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
RUN python -c "import language_tool_python; language_tool_python.LanguageTool('en-GB')" || true

COPY kopi/ ./kopi/
COPY cloud/serve.py entrypoint_serve.sh ./
RUN chmod +x entrypoint_serve.sh

COPY data/ ./data/

# The warm GPU service (Ollama + Flask) is the only deployment target.
ENTRYPOINT ["./entrypoint_serve.sh"]
