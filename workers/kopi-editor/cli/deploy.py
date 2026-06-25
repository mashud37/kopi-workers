"""`deploy` — build and deploy the GPU LLM service to Cloud Run.

The primary service is vLLM serving Qwen3-32B-FP8 + the `kopi` LoRA adapter on a
Blackwell GPU (FP8, not AWQ: a bf16-trained LoRA over an AWQ base corrupts tokens). It is **fire-and-retire**: `deploy` stages the adapter and submits the
long image build to Cloud Build asynchronously, then returns — the terminal is free
while the build runs. `deploy-status [--wait]` polls the build; once it succeeds it
runs the short Cloud Run deploy locally and writes BASE_URL + JOB_TOKEN into env.yaml
(the JOB_TOKEN never leaves this machine). Pending-build state lives in .kopi/deploy.json.

The legacy L4 Ollama service (deploy.ps1/.sh, synchronous) is reachable with --ollama.
"""
import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from cli import config, ui

_REPO = "kopi"
_STATE = config.ROOT / ".kopi" / "deploy.json"
# Blackwell vLLM service shape (also written to env.yaml so cost estimation is accurate).
_GPU_TYPE, _CPU, _MEM = "nvidia-rtx-pro-6000", 20, 80
_DEAD = {"FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED", "EXPIRED"}


def run(ollama: bool = False):
    if ollama:
        return _deploy_ollama()
    return _fire_vllm()


# --- primary path: async vLLM build, finish on status -----------------------

def _fire_vllm():
    ui.header("Deploy vLLM LLM service")
    _require_gcloud()
    project = _select_project()
    region, service = config.region(), config.service()
    model = config.model() or "Qwen/Qwen3-32B-FP8"
    image = f"{region}-docker.pkg.dev/{project}/{_REPO}/kopi-editor-vllm:latest"
    token = config.job_token() or secrets.token_hex(24)

    ui.step(f"deploying {model} to {project} ({region}/{service})")
    _stage_adapter()
    _ensure_infra(project, region)

    ui.step("submitting image build to Cloud Build (async — the terminal frees once the upload finishes)")
    build_id = _gcloud_capture(
        "builds", "submit", "--config", "cloudbuild.vllm.yaml",
        "--substitutions", f"_KOPI_MODEL={model},_IMAGE={image}",
        f"--region={region}", f"--project={project}", "--async", "--format=value(id)",
    )
    if not build_id:
        raise SystemExit("could not read the build id — check `gcloud builds list`.")

    _save_state({
        "build_id": build_id, "project": project, "region": region, "service": service,
        "model": model, "image": image, "token": token, "deployed": False,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    ui.ok(f"build {build_id} firing — terminal is free")
    ui.info(f"logs: gcloud builds log {build_id} --region {region} --stream")
    ui.info("finish + deploy when it's done:  python manage.py deploy-status --wait")
    return 0


def status(wait: bool = False):
    ui.header("Deploy status")
    _require_gcloud()
    rec = _load_state()
    if rec.get("deployed"):
        ui.ok(f"already deployed: {rec.get('url')}")
        return 0

    while True:
        st = _gcloud_capture("builds", "describe", rec["build_id"],
                             f"--region={rec['region']}", f"--project={rec['project']}",
                             "--format=value(status)")
        ui.info(f"build {rec['build_id']}: {st or 'UNKNOWN'}")
        if st == "SUCCESS":
            break
        if st in _DEAD:
            raise SystemExit(
                f"build {st} — logs: gcloud builds log {rec['build_id']} --region {rec['region']}")
        if not wait:
            ui.info("still building; re-run `deploy-status --wait` to block, or check back later.")
            return 0
        time.sleep(20)

    return _finish_deploy(rec)


def _finish_deploy(rec):
    ui.step(f"image built — deploying Cloud Run service {rec['service']} (~1-3 min)")
    _gcloud_stream(
        "run", "deploy", rec["service"], f"--image={rec['image']}",
        f"--region={rec['region']}", f"--project={rec['project']}",
        f"--service-account=kopi-runner@{rec['project']}.iam.gserviceaccount.com",
        "--command=./entrypoint_vllm.sh",
        "--gpu=1", f"--gpu-type={_GPU_TYPE}", "--no-gpu-zonal-redundancy", "--no-cpu-throttling",
        f"--cpu={_CPU}", f"--memory={_MEM}Gi", "--max-instances=1", "--min-instances=0",
        "--concurrency=4", "--timeout=900",
        f"--set-env-vars=KOPI_MODEL={rec['model']},JOB_TOKEN={rec['token']}",
        "--allow-unauthenticated",
    )
    url = _gcloud_capture("run", "services", "describe", rec["service"],
                          f"--region={rec['region']}", f"--project={rec['project']}",
                          "--format=value(status.url)")
    if not url:
        raise SystemExit("deploy reported no URL — check `gcloud run services list`.")

    config.set_values({
        "PROJECT": rec["project"], "REGION": rec["region"], "SERVICE": rec["service"],
        "MODEL": rec["model"], "BASE_URL": url, "JOB_TOKEN": rec["token"],
        "GPU_TYPE": _GPU_TYPE, "CPU": _CPU, "MEMORY": _MEM,
    })
    rec.update(deployed=True, url=url)
    _save_state(rec)
    ui.ok(f"deployed: {url}")
    ui.info("edit locally with:  python manage.py edit <file.docx> <words>")
    return 0


# --- build context helpers --------------------------------------------------

def _stage_adapter():
    src = Path(os.environ.get("KOPI_ADAPTER_DIR")
               or config.ROOT.parent / "kopi-learner" / "data" / "adapters" / "sft")
    dst = config.ROOT / "adapter"
    dst.mkdir(exist_ok=True)
    for p in dst.iterdir():
        if p.name == ".gitkeep":
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()

    if not (src / "adapter_config.json").exists():
        ui.warn(f"no adapter at {src} — deploying base-only (no 'kopi' module)")
        return
    for item in src.iterdir():
        if item.name.startswith("checkpoint-"):
            continue
        target = dst / item.name
        shutil.copytree(item, target) if item.is_dir() else shutil.copy2(item, target)
    ui.ok(f"staged adapter from {src} -> adapter/ (served as 'kopi')")

    # The silent base-only trap: an ignore file can strip the adapter from the upload.
    listing = _gcloud_capture("meta", "list-files-for-upload", ".").replace("\\", "/")
    if "adapter/adapter_config.json" not in listing:
        raise SystemExit("adapter staged but excluded from the build upload "
                         "(.gcloudignore/.gitignore) — fix the ignore file before deploying.")


def _ensure_infra(project, region):
    _gcloud_stream("services", "enable", "run.googleapis.com",
                   "artifactregistry.googleapis.com", "cloudbuild.googleapis.com",
                   f"--project={project}")
    _gcloud_stream("artifacts", "repositories", "create", _REPO,
                   "--repository-format=docker", f"--location={region}",
                   f"--project={project}", allow_fail=True)
    _gcloud_stream("iam", "service-accounts", "create", "kopi-runner",
                   "--display-name=kopi-editor LLM service",
                   f"--project={project}", allow_fail=True)


# --- legacy synchronous Ollama path -----------------------------------------

def _deploy_ollama():
    ui.header("Deploy ollama LLM service")
    _require_gcloud()
    project = _select_project()
    ui.ok(f"deploying to project: {project}")
    ui.info("L4 GPU is required; ensure the region has availability and quota.")
    if os.name == "nt":
        script = config.ROOT / "deploy.ps1"
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = config.ROOT / "deploy.sh"
        if not shutil.which("bash"):
            raise SystemExit("bash not found — run `bash deploy.sh` from a shell that has it.")
        cmd = ["bash", str(script)]
    if not script.exists():
        raise SystemExit(f"{script.name} not found.")
    return subprocess.call(cmd, cwd=str(config.ROOT), env=dict(os.environ, PROJECT=project))


# --- shared --------------------------------------------------------------

def _require_gcloud():
    if not shutil.which("gcloud"):
        raise SystemExit("gcloud CLI not found — install it first (run: python manage.py install).")
    if not config.ENV_FILE.exists():
        raise SystemExit("env.yaml missing — run `python manage.py install` first.")


def _select_project():
    # env.yaml is the source of truth; gcloud's active config is only a fallback —
    # the two can diverge (and a stale active config sends the deploy to the wrong project).
    configured = config.project()
    active = _gcloud_capture("config", "get-value", "project")
    default = configured or active
    listing = _gcloud_capture("projects", "list", "--format=value(projectId)")
    projects = [p for p in listing.splitlines() if p.strip()]

    ui.step("Select GCP project")
    if configured:
        ui.info(f"env.yaml project: {configured}")
    if active and active != configured:
        ui.info(f"gcloud active project: {active} (not used unless selected)")
    for i, p in enumerate(projects, 1):
        tag = "  (env.yaml)" if p == configured else ("  (gcloud active)" if p == active else "")
        ui.info(f"{i}) {p}{tag}")

    raw = (ui.ask("Project to deploy to (number or id)", default=default) or "").strip()
    if not raw:
        raise SystemExit("No project selected.")
    if raw.isdigit() and 1 <= int(raw) <= len(projects):
        return projects[int(raw) - 1]
    return raw


def _gcloud_capture(*args):
    exe = shutil.which("gcloud") or "gcloud"
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=600)
        return out.stdout.strip()
    except Exception:
        return ""


def _gcloud_stream(*args, allow_fail=False):
    exe = shutil.which("gcloud") or "gcloud"
    rc = subprocess.call([exe, *args])
    if rc != 0 and not allow_fail:
        raise SystemExit(f"`gcloud {args[0]} {args[1]}` failed (exit {rc}).")
    return rc


def _save_state(rec):
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(rec, indent=2), encoding="utf-8")


def _load_state():
    if not _STATE.exists():
        raise SystemExit("no pending deploy — run `python manage.py deploy` first.")
    return json.loads(_STATE.read_text(encoding="utf-8"))
