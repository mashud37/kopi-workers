"""`deploy` — build and deploy the GPU LLM service to Cloud Run.

Prompts for the GCP project (never silently uses the active gcloud config), then
runs the platform deploy script: deploy.ps1 on Windows (default), deploy.sh
elsewhere. Both build the image, deploy a warm L4-GPU service, and write BASE_URL
+ JOB_TOKEN back into env.yaml.
"""
import os
import shutil
import subprocess

from cli import config, ui


def run():
    ui.header("Deploy GPU LLM service")
    if not shutil.which("gcloud"):
        raise SystemExit("gcloud CLI not found — install it first (run: python manage.py install).")
    if not config.ENV_FILE.exists():
        raise SystemExit("env.yaml missing — run `python manage.py install` first.")

    project = _select_project()
    ui.ok(f"deploying to project: {project}  (region {config.region()})")
    ui.info("L4 GPU is required; ensure the region has GPU availability and nvidia_l4 quota.")

    cmd = _deploy_command()
    # Pass the CONFIGURED model/region/service through to the deploy script — it
    # reads these from the environment (KOPI_MODEL defaults to qwen2.5:7b), so
    # without this the build would ignore env.yaml and always bake the default.
    env = dict(
        os.environ,
        PROJECT=project,
        KOPI_MODEL=config.model() or "qwen2.5:7b",
        KOPI_REGION=config.region(),
        KOPI_SERVICE=config.service(),
    )
    ui.info(f"Running {'deploy.ps1' if os.name == 'nt' else 'deploy.sh'} "
            f"(builds the image with {config.model()}, deploys the service, writes BASE_URL/JOB_TOKEN).")
    return subprocess.call(cmd, cwd=str(config.ROOT), env=env)


def _select_project():
    current = _gcloud("config", "get-value", "project")
    listing = _gcloud("projects", "list", "--format=value(projectId)")
    projects = [p for p in listing.splitlines() if p.strip()]

    ui.step("Select GCP project")
    if current:
        ui.info(f"active gcloud project: {current}")
    for i, p in enumerate(projects, 1):
        ui.info(f"{i}) {p}{'  (active)' if p == current else ''}")

    raw = (ui.ask("Project to deploy to (number or id)", default=current) or "").strip()
    if not raw:
        raise SystemExit("No project selected.")
    if raw.isdigit() and 1 <= int(raw) <= len(projects):
        return projects[int(raw) - 1]
    return raw


def _gcloud(*args):
    exe = shutil.which("gcloud") or "gcloud"
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:
        return ""


def _deploy_command():
    if os.name == "nt":
        script = config.ROOT / "deploy.ps1"
        if not script.exists():
            raise SystemExit("deploy.ps1 not found.")
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    script = config.ROOT / "deploy.sh"
    if not script.exists():
        raise SystemExit("deploy.sh not found.")
    if not shutil.which("bash"):
        raise SystemExit("bash not found — run `bash deploy.sh` from a shell that has it.")
    return ["bash", str(script)]
