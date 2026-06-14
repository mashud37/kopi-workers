# deploy_vllm.ps1 — build + deploy the PARALLEL vLLM/qwen3 service on the Blackwell GPU (Windows).
# Separate service (kopi-editor-vllm) in europe-west4; the L4 Ollama service in europe-west1 is
# untouched. Blackwell runs driver 580/CUDA 13, so vLLM-latest works. Writes URL + token to env.vllm.yaml.

$ErrorActionPreference = "Continue"

$PROJECT = $env:PROJECT
if (-not $PROJECT) {
  $current = (gcloud config get-value project 2>$null)
  $PROJECT = Read-Host "GCP project to deploy to [$current]"
  if (-not $PROJECT) { $PROJECT = $current }
}
if (-not $PROJECT) { Write-Error "No GCP project set."; exit 1 }

# Blackwell (nvidia-rtx-pro-6000) is NOT in europe-west1; nearest is europe-west4.
$REGION  = if ($env:KOPI_VLLM_REGION)   { $env:KOPI_VLLM_REGION }   else { "europe-west4" }
$SERVICE = if ($env:KOPI_VLLM_SERVICE)  { $env:KOPI_VLLM_SERVICE }  else { "kopi-editor-vllm" }
$MODEL   = if ($env:KOPI_MODEL)         { $env:KOPI_MODEL }         else { "Qwen/Qwen3-32B-AWQ" }
$REPO    = "kopi"
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/$REPO/kopi-editor-vllm:latest"
$SA      = "kopi-runner@$PROJECT.iam.gserviceaccount.com"

$TOKEN = (python -c "import yaml,pathlib; p=pathlib.Path('env.vllm.yaml'); d=(yaml.safe_load(p.read_text()) if p.exists() else {}) or {}; print(d.get('JOB_TOKEN') or '')").Trim()
if (-not $TOKEN) { $TOKEN = (python -c "import secrets; print(secrets.token_hex(24))").Trim() }

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project=$PROJECT
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION --project=$PROJECT
gcloud iam service-accounts create "kopi-runner" --display-name="kopi-editor LLM service" --project=$PROJECT

gcloud builds submit --config cloudbuild.vllm.yaml --substitutions "_KOPI_MODEL=$MODEL,_IMAGE=$IMAGE" --region=$REGION --project=$PROJECT
if ($LASTEXITCODE -ne 0) { Write-Error "Image build failed."; exit 1 }

# Blackwell requires a minimum of 20 CPU and 80 GiB memory.
gcloud run deploy $SERVICE --image=$IMAGE --region=$REGION --project=$PROJECT `
  --service-account=$SA --command="./entrypoint_vllm.sh" `
  --gpu=1 --gpu-type=nvidia-rtx-pro-6000 --no-gpu-zonal-redundancy --no-cpu-throttling `
  --cpu=20 --memory=80Gi --max-instances=1 --min-instances=0 --concurrency=4 --timeout=900 `
  --set-env-vars="KOPI_MODEL=$MODEL,JOB_TOKEN=$TOKEN" `
  --allow-unauthenticated
if ($LASTEXITCODE -ne 0) { Write-Error "Deploy failed (check RTX PRO 6000 availability/quota in $REGION)."; exit 1 }

$URL = (gcloud run services describe $SERVICE --region=$REGION --project=$PROJECT --format="value(status.url)")
python -c "import yaml,sys,pathlib;p=pathlib.Path('env.vllm.yaml');d=(yaml.safe_load(p.read_text()) if p.exists() else {}) or {};d.update({'PROJECT':sys.argv[1],'REGION':sys.argv[2],'SERVICE':sys.argv[3],'MODEL':sys.argv[4],'BASE_URL':sys.argv[5],'JOB_TOKEN':sys.argv[6],'GPU_TYPE':'nvidia-rtx-pro-6000','CPU':20,'MEMORY':80});p.write_text(yaml.safe_dump(d,sort_keys=False));print('vLLM BASE_URL: '+sys.argv[5])" $PROJECT $REGION $SERVICE $MODEL $URL $TOKEN

Write-Host ""
Write-Host "A/B test (Ollama prod untouched):"
Write-Host "  `$env:KOPI_BASE_URL='$URL'; `$env:KOPI_JOB_TOKEN='$TOKEN'; python manage.py edit `"chapter 1.docx`""
