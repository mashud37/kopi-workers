#!/bin/bash
# deploy_vllm.sh — build + deploy the PARALLEL vLLM/qwen3 service on the Blackwell GPU.
# Separate service (kopi-editor-vllm) in europe-west4 (the L4 Ollama service in
# europe-west1 is untouched). Blackwell runs driver 580/CUDA 13, so vLLM-latest works.
# Writes URL + token to env.vllm.yaml. Usage: PROJECT=my-project bash deploy_vllm.sh
set -e

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$PROJECT" ]; then echo "No GCP project set (export PROJECT=...)."; exit 1; fi

# Blackwell (nvidia-rtx-pro-6000) is NOT in europe-west1; nearest is europe-west4.
REGION="${KOPI_VLLM_REGION:-europe-west4}"
SERVICE="${KOPI_VLLM_SERVICE:-kopi-editor-vllm}"
MODEL="${KOPI_MODEL:-Qwen/Qwen3-32B-AWQ}"
REPO="kopi"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/kopi-editor-vllm:latest"
SA="kopi-runner@$PROJECT.iam.gserviceaccount.com"

TOKEN="$(python -c "import yaml,pathlib; p=pathlib.Path('env.vllm.yaml'); d=(yaml.safe_load(p.read_text()) if p.exists() else {}) or {}; print(d.get('JOB_TOKEN') or '')" 2>/dev/null || true)"
if [ -z "$TOKEN" ]; then TOKEN="$(python -c 'import secrets; print(secrets.token_hex(24))')"; fi

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project="$PROJECT"
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" --project="$PROJECT" || true
gcloud iam service-accounts create "kopi-runner" --display-name="kopi-editor LLM service" --project="$PROJECT" || true

gcloud builds submit --config cloudbuild.vllm.yaml --substitutions "_KOPI_MODEL=$MODEL,_IMAGE=$IMAGE" --region="$REGION" --project="$PROJECT"

# Blackwell requires a minimum of 20 CPU and 80 GiB memory.
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" --project="$PROJECT" \
  --service-account="$SA" --command="./entrypoint_vllm.sh" \
  --gpu=1 --gpu-type=nvidia-rtx-pro-6000 --no-gpu-zonal-redundancy --no-cpu-throttling \
  --cpu=20 --memory=80Gi --max-instances=1 --min-instances=0 --concurrency=4 --timeout=900 \
  --set-env-vars="KOPI_MODEL=$MODEL,JOB_TOKEN=$TOKEN" \
  --allow-unauthenticated

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format='value(status.url)')"
python -c "import yaml,sys,pathlib;p=pathlib.Path('env.vllm.yaml');d=(yaml.safe_load(p.read_text()) if p.exists() else {}) or {};d.update({'PROJECT':sys.argv[1],'REGION':sys.argv[2],'SERVICE':sys.argv[3],'MODEL':sys.argv[4],'BASE_URL':sys.argv[5],'JOB_TOKEN':sys.argv[6],'GPU_TYPE':'nvidia-rtx-pro-6000','CPU':20,'MEMORY':80});p.write_text(yaml.safe_dump(d,sort_keys=False));print('vLLM BASE_URL: '+sys.argv[5])" "$PROJECT" "$REGION" "$SERVICE" "$MODEL" "$URL" "$TOKEN"

echo ""
echo "A/B test (Ollama prod untouched):"
echo "  KOPI_BASE_URL=$URL KOPI_JOB_TOKEN=$TOKEN python manage.py edit \"chapter 1.docx\""
