#!/bin/bash
# deploy.sh — build + deploy the kopi-editor GPU LLM service to Cloud Run (POSIX).
# POSIX mirror of deploy.ps1 (the Windows default) — keep the two in sync.
# Usage: PROJECT=my-project bash deploy.sh   (or run `python manage.py deploy`)
set -e

# Default to env.yaml's PROJECT (the source of truth), not gcloud's active config.
PROJECT="${PROJECT:-$(python -c "import yaml,pathlib; p=pathlib.Path('env.yaml'); d=(yaml.safe_load(p.read_text()) if p.exists() else {}) or {}; print(d.get('PROJECT') or '')" 2>/dev/null || true)}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$PROJECT" ]; then echo "No GCP project set (export PROJECT=...)."; exit 1; fi
if [ ! -f env.yaml ]; then echo "env.yaml missing - run: python manage.py install"; exit 1; fi

REGION="${KOPI_REGION:-europe-west1}"
SERVICE="${KOPI_SERVICE:-kopi-editor}"
MODEL="${KOPI_MODEL:-qwen2.5:7b}"
REPO="kopi"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/kopi-editor:latest"
SA="kopi-runner@$PROJECT.iam.gserviceaccount.com"

TOKEN="$(python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('env.yaml').read_text()) or {}; print(d.get('JOB_TOKEN') or '')")"
if [ -z "$TOKEN" ]; then TOKEN="$(python -c 'import secrets; print(secrets.token_hex(24))')"; fi

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project="$PROJECT"
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" --project="$PROJECT" || true
gcloud iam service-accounts create "kopi-runner" --display-name="kopi-editor LLM service" --project="$PROJECT" || true

gcloud builds submit --config cloudbuild.yaml --substitutions "_KOPI_MODEL=$MODEL,_IMAGE=$IMAGE" --project="$PROJECT"

gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" --project="$PROJECT" \
  --service-account="$SA" --command="./entrypoint_serve.sh" \
  --gpu=1 --gpu-type=nvidia-l4 --no-gpu-zonal-redundancy --no-cpu-throttling \
  --cpu=4 --memory=16Gi --max-instances=1 --min-instances=0 --concurrency=4 --timeout=900 \
  --set-env-vars="KOPI_MODEL=$MODEL,OLLAMA_NUM_PARALLEL=4,JOB_TOKEN=$TOKEN" \
  --allow-unauthenticated

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format='value(status.url)')"
python -c "import yaml,sys,pathlib;p=pathlib.Path('env.yaml');d=yaml.safe_load(p.read_text()) or {};d.update({'PROJECT':sys.argv[1],'REGION':sys.argv[2],'SERVICE':sys.argv[3],'MODEL':sys.argv[4],'BASE_URL':sys.argv[5],'JOB_TOKEN':sys.argv[6]});p.write_text(yaml.safe_dump(d,sort_keys=False));print('BASE_URL written: '+sys.argv[5])" "$PROJECT" "$REGION" "$SERVICE" "$MODEL" "$URL" "$TOKEN"

echo ""
echo "Deployed. Edit locally with:  python manage.py edit <file.docx> <words>"
