# deploy.ps1 — build + deploy the kopi-editor GPU LLM service to Cloud Run (Windows).
# Usage: set $env:PROJECT (or run `python manage.py deploy`, which prompts), then: .\deploy.ps1
#
# Native PowerShell mirror of deploy.sh — keep the two in sync. Builds the image
# (model baked in via cloudbuild.yaml), deploys a warm L4-GPU service, then writes
# BASE_URL + JOB_TOKEN back into env.yaml.

$ErrorActionPreference = "Continue"

$PROJECT = $env:PROJECT
if (-not $PROJECT) {
  $current = (gcloud config get-value project 2>$null)
  $PROJECT = Read-Host "GCP project to deploy to [$current]"
  if (-not $PROJECT) { $PROJECT = $current }
}
if (-not $PROJECT) { Write-Error "No GCP project set."; exit 1 }
if (-not (Test-Path env.yaml)) { Write-Error "env.yaml missing - run: python manage.py install"; exit 1 }

$REGION  = if ($env:KOPI_REGION)  { $env:KOPI_REGION }  else { "europe-west1" }
$SERVICE = if ($env:KOPI_SERVICE) { $env:KOPI_SERVICE } else { "kopi-editor" }
$MODEL   = if ($env:KOPI_MODEL)   { $env:KOPI_MODEL }   else { "qwen2.5:7b" }
$REPO    = "kopi"
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/$REPO/kopi-editor:latest"
$SA      = "kopi-runner@$PROJECT.iam.gserviceaccount.com"

# Reuse an existing JOB_TOKEN from env.yaml, else generate one.
$TOKEN = (python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('env.yaml').read_text()) or {}; print(d.get('JOB_TOKEN') or '')").Trim()
if (-not $TOKEN) { $TOKEN = (python -c "import secrets; print(secrets.token_hex(24))").Trim() }

# --- enable APIs ---
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project=$PROJECT

# --- Artifact Registry repo (ignored if it already exists) ---
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION --project=$PROJECT

# --- service account (ignored if it already exists) ---
gcloud iam service-accounts create "kopi-runner" --display-name="kopi-editor LLM service" --project=$PROJECT

# --- build image (model baked in; large build, 15-25 min) ---
gcloud builds submit --config cloudbuild.yaml --substitutions "_KOPI_MODEL=$MODEL,_IMAGE=$IMAGE" --project=$PROJECT
if ($LASTEXITCODE -ne 0) { Write-Error "Image build failed."; exit 1 }

# --- deploy warm GPU service (scales to zero between sessions) ---
gcloud run deploy $SERVICE --image=$IMAGE --region=$REGION --project=$PROJECT `
  --service-account=$SA --command="./entrypoint_serve.sh" `
  --gpu=1 --gpu-type=nvidia-l4 --no-gpu-zonal-redundancy --no-cpu-throttling `
  --cpu=4 --memory=16Gi --max-instances=1 --min-instances=0 --concurrency=4 --timeout=900 `
  --set-env-vars="KOPI_MODEL=$MODEL,OLLAMA_NUM_PARALLEL=4,JOB_TOKEN=$TOKEN" `
  --allow-unauthenticated
if ($LASTEXITCODE -ne 0) { Write-Error "Deploy failed (check L4 GPU availability/quota in $REGION)."; exit 1 }

# --- write BASE_URL + JOB_TOKEN + targets back into env.yaml ---
$URL = (gcloud run services describe $SERVICE --region=$REGION --project=$PROJECT --format="value(status.url)")
python -c "import yaml,sys,pathlib;p=pathlib.Path('env.yaml');d=yaml.safe_load(p.read_text()) or {};d.update({'PROJECT':sys.argv[1],'REGION':sys.argv[2],'SERVICE':sys.argv[3],'MODEL':sys.argv[4],'BASE_URL':sys.argv[5],'JOB_TOKEN':sys.argv[6]});p.write_text(yaml.safe_dump(d,sort_keys=False));print('BASE_URL written: '+sys.argv[5])" $PROJECT $REGION $SERVICE $MODEL $URL $TOKEN

Write-Host ""
Write-Host "Deployed. Edit locally with:  python manage.py edit <file.docx> <words>"
