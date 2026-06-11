#!/usr/bin/env python3
"""Interactive setup script for kopi-editor Google Cloud infrastructure.

Usage:
    python cloud/setup_cloud.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_CONFIG_PATH = Path.home() / ".config" / "kopi-editor" / "cloud.json"


def _load_existing_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(cfg: dict, project: str) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "bucket":   cfg["bucket"],
        "region":   cfg["region"],
        "job":      cfg["job_name"],
        "project":  project,
        "repo":     cfg["repo"],
        "sa_name":  cfg["sa_name"],
        "model_id": cfg["model"]["id"],
    }
    _CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _ok(f"Config saved: {_CONFIG_PATH}")


_MODELS = [
    {"key": "1", "name": "Lightweight", "id": "gemma3:4b",     "cpu": "2", "mem": "4Gi",  "cost": "< $0.03 / chapter"},
    {"key": "2", "name": "Standard",    "id": "mistral-small", "cpu": "4", "mem": "16Gi", "cost": "< $0.05 / chapter"},
    {"key": "3", "name": "High-tier",   "id": "qwen3.5:27b",   "cpu": "4", "mem": "16Gi", "cost": "< $0.08 / chapter"},
]


# ── Terminal helpers ───────────────────────────────────────────────────────────

def _header(text):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def _step(n, total, label):
    print(f"\n[{n}/{total}] {label}")
    print("-" * 50)


def _ok(msg):
    print(f"  OK   {msg}")


def _info(msg):
    print(f"       {msg}")


def _ask(prompt, default=None):
    display = f"  {prompt} [{default}]: " if default else f"  {prompt}: "
    try:
        val = input(display).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default


def _ask_choice(prompt, choices, default=None):
    while True:
        val = _ask(prompt, default)
        if val in choices:
            return val
        print(f"       Please enter one of: {', '.join(choices)}")


def _confirm(prompt, default_yes=True):
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        val = input(f"  {prompt} {suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val.startswith("y") if val else default_yes


def _abort(msg):
    print(f"\n  ERROR: {msg}")
    sys.exit(1)


# ── Subprocess helpers ─────────────────────────────────────────────────────────

def _resolve(cmd):
    """Resolve the executable, finding .cmd/.bat wrappers on Windows."""
    exe = shutil.which(cmd[0])
    return [exe] + list(cmd[1:]) if exe else list(cmd)


def _run(cmd, *, check=True, show=True):
    """Run command, stream output to terminal. Raises on failure if check=True."""
    cmd = _resolve(cmd)
    if show:
        print(f"       $ {' '.join(str(c) for c in cmd)}")
    try:
        subprocess.run(cmd, check=check, text=True)
    except subprocess.CalledProcessError as e:
        _abort(f"Command failed (exit {e.returncode}): {' '.join(str(c) for c in cmd)}")
    except FileNotFoundError:
        _abort(f"Command not found: {cmd[0]}")


def _capture(cmd):
    """Run command, return (returncode, stdout)."""
    cmd = _resolve(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def _exists_gcloud(cmd):
    """Return True if a gcloud describe/list command exits 0."""
    rc, _ = _capture(cmd)
    return rc == 0


_COMMON_REGIONS = [
    "europe-west1", "europe-west4", "europe-west2",
    "us-central1", "us-east1", "us-west1",
    "asia-northeast1", "asia-southeast1",
]


def _auto_discover(project: str, job_name: str = "kopi-editor-llm") -> dict:
    """Scan gcloud for an existing Cloud Run job and extract config defaults."""
    discovered = {}
    _info("No local config found — scanning gcloud for existing setup...")

    job_json = ""
    for region in _COMMON_REGIONS:
        rc, out = _capture([
            "gcloud", "run", "jobs", "describe", job_name,
            "--region", region, "--format=json",
        ])
        if rc != 0 or not out:
            continue

        job_json = out

        m_image = re.search(r'"image":\s*"([^"]*docker\.pkg\.dev[^"]*)"', out)
        if m_image:
            image = m_image.group(1)
            m_parse = re.match(r"[a-z0-9-]+-docker\.pkg\.dev/[^/]+/([^/]+)/", image)
            if m_parse:
                discovered["region"] = region
                discovered["repo"]   = m_parse.group(1)
                discovered["job"]    = job_name

        m_sa = re.search(r'"serviceAccountName":\s*"([^"]+@[^"]+)"', out)
        if m_sa:
            discovered["sa_name"] = m_sa.group(1).split("@")[0]

        _ok(f"Found job '{job_name}' in {region}")
        break

    if not discovered:
        return discovered

    # Extract KOPI_BUCKET / KOPI_MODEL from job env vars (set by current setup_cloud.py).
    # Use object-level matching so field order inside the JSON object doesn't matter.
    for env_obj in re.findall(r'\{[^{}]*(?:KOPI_BUCKET|KOPI_MODEL)[^{}]*\}', job_json):
        m_name = re.search(r'"name":\s*"([^"]+)"', env_obj)
        m_val  = re.search(r'"value":\s*"([^"]+)"', env_obj)
        if not (m_name and m_val):
            continue
        if m_name.group(1) == "KOPI_BUCKET":
            discovered["bucket"]   = m_val.group(1)
            _ok(f"Found bucket from job config: {m_val.group(1)}")
        elif m_name.group(1) == "KOPI_MODEL":
            discovered["model_id"] = m_val.group(1)

    if not discovered.get("bucket"):
        # Bucket not in job env vars — list project buckets (project-scoped, no cross-project noise)
        for list_cmd in (
            ["gcloud", "storage", "buckets", "list", "--project", project, "--uri"],
            ["gsutil", "ls", "-p", project],
        ):
            rc2, blist = _capture(list_cmd)
            if rc2 != 0 or not blist:
                continue
            names = [
                line.strip().removeprefix("gs://").rstrip("/")
                for line in blist.splitlines()
                if line.strip().startswith("gs://")
            ]
            if len(names) == 1:
                discovered["bucket"] = names[0]
                _ok(f"Found bucket: {names[0]}")
                break
            elif len(names) > 1:
                kopi = [n for n in names if "kopi" in n.lower()]
                if len(kopi) == 1:
                    discovered["bucket"] = kopi[0]
                    _ok(f"Found bucket: {kopi[0]}")
                    break
            # Multiple buckets and none kopi-named — try next command before giving up

    return discovered


# ── Setup steps ───────────────────────────────────────────────────────────────

def check_gcloud():
    _step(1, 9, "Check gcloud CLI")
    rc, out = _capture(["gcloud", "version"])
    if rc != 0:
        _abort(
            "gcloud CLI not found.\n"
            "  Install from: https://cloud.google.com/sdk/docs/install"
        )
    first = out.splitlines()[0] if out else "gcloud"
    _ok(first)


def authenticate():
    _step(2, 9, "Authentication")
    rc, account = _capture(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
    if rc == 0 and account:
        _ok(f"Logged in as: {account}")
        if not _confirm("Use this account?"):
            _run(["gcloud", "auth", "login"])
    else:
        _info("No active account found.")
        _run(["gcloud", "auth", "login"])

    # Application Default Credentials are separate from gcloud CLI auth.
    # The Python google-cloud-storage SDK needs these to upload/download from GCS.
    rc_adc, _ = _capture(["gcloud", "auth", "application-default", "print-access-token"])
    if rc_adc != 0:
        _info("Application Default Credentials not set up.")
        _info("These are required by the Python SDK (separate from gcloud CLI auth).")
        _run(["gcloud", "auth", "application-default", "login"])


def select_project():
    _step(3, 9, "Google Cloud project")
    rc, current = _capture(["gcloud", "config", "get-value", "project"])
    default = current if rc == 0 and current else None
    if default:
        _info(f"Current project: {default}")
    project = _ask("Project ID", default)
    if not project:
        _abort("A project ID is required.")
    _run(["gcloud", "config", "set", "project", project], show=False)
    _ok(f"Project: {project}")
    return project


def gather_config(project):
    _step(4, 9, "Configuration")
    existing = _load_existing_config()

    if existing:
        defaults = existing
        source = "local config"
    else:
        defaults = _auto_discover(project)
        source = "gcloud" if defaults else "defaults"

    # Apply hard defaults for anything not discovered
    defaults.setdefault("region",   "europe-west1")
    defaults.setdefault("repo",     "kopi")
    defaults.setdefault("job",      "kopi-editor-llm")
    defaults.setdefault("sa_name",  "kopi-runner")

    current_model_key = next(
        (m["key"] for m in _MODELS if m["id"] == defaults.get("model_id")), "2"
    )
    current_model = next(m for m in _MODELS if m["key"] == current_model_key)

    # Show everything discovered at once
    print()
    if source == "local config":
        _info("Existing local configuration detected:")
    elif source == "gcloud":
        _info("Configuration detected from gcloud:")
    else:
        _info("No existing setup found — using defaults:")
    print()
    print(f"    Project   : {project}")
    print(f"    Region    : {defaults['region']}")
    print(f"    Bucket    : {('gs://' + defaults['bucket']) if defaults.get('bucket') else '[not found — you will be asked]'}")
    print(f"    AR repo   : {defaults['region']}-docker.pkg.dev/{project}/{defaults['repo']}")
    print(f"    Job       : {defaults['job']}")
    print(f"    SA        : {defaults['sa_name']}@{project}.iam.gserviceaccount.com")
    print(f"    Model     : {current_model['id']}  ({current_model['cpu']} CPU, {current_model['mem']})")
    print()

    # Ask only for the bucket if it wasn't auto-detected
    if defaults.get("bucket"):
        bucket = defaults["bucket"]
    else:
        bucket = _ask("GCS bucket name (globally unique)")
        if not bucket:
            _abort("A bucket name is required.")
        defaults["bucket"] = bucket

    # Single confirm — or drop into full edit mode
    if not _confirm("Use these settings?"):
        print()
        _info("Edit settings (press Enter to keep the shown value):")
        print()
        defaults["region"]  = _ask("Region",                             defaults["region"])
        defaults["bucket"]  = _ask("GCS bucket name",                   defaults["bucket"])
        if not defaults["bucket"]:
            _abort("A bucket name is required.")
        defaults["repo"]    = _ask("Artifact Registry repository name", defaults["repo"])
        defaults["job"]     = _ask("Cloud Run job name",                defaults["job"])
        defaults["sa_name"] = _ask("Service account name",              defaults["sa_name"])
        print()
        print("  Model to bake into the container image:")
        for m in _MODELS:
            print(f"    [{m['key']}] {m['name']:<12}  {m['id']:<18}  cloud: {m['cost']}")
        model_key = _ask_choice(
            f"  Model [1/2/3]", ["1", "2", "3"], default=current_model_key
        )
        current_model = next(m for m in _MODELS if m["key"] == model_key)

    region   = defaults["region"]
    bucket   = defaults["bucket"]
    repo     = defaults["repo"]
    job_name = defaults["job"]
    sa_name  = defaults["sa_name"]
    model    = current_model
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"
    image    = f"{region}-docker.pkg.dev/{project}/{repo}/kopi-editor"

    print()
    print("  Confirm")
    print(f"    Project   : {project}")
    print(f"    Region    : {region}")
    print(f"    Bucket    : gs://{bucket}")
    print(f"    AR repo   : {region}-docker.pkg.dev/{project}/{repo}")
    print(f"    Job       : {job_name}")
    print(f"    SA        : {sa_email}")
    print(f"    Model     : {model['id']}  ({model['cpu']} CPU, {model['mem']})")
    print()
    if not _confirm("Proceed?"):
        print("  Aborted.")
        sys.exit(0)

    return {
        "region":   region,
        "bucket":   bucket,
        "repo":     repo,
        "job_name": job_name,
        "sa_name":  sa_name,
        "sa_email": sa_email,
        "model":    model,
        "image":    image,
    }


def enable_apis():
    _step(5, 9, "Enable required APIs")
    apis = [
        "run.googleapis.com",
        "cloudbuild.googleapis.com",
        "storage.googleapis.com",
        "artifactregistry.googleapis.com",
    ]
    _info(f"APIs: {', '.join(apis)}")
    _run(["gcloud", "services", "enable"] + apis)


def create_infrastructure(cfg, project):
    _step(6, 9, "Artifact Registry repository + GCS bucket")

    region, bucket, repo = cfg["region"], cfg["bucket"], cfg["repo"]

    if _exists_gcloud(["gcloud", "artifacts", "repositories", "describe", repo,
                       "--location", region, "--format=value(name)"]):
        _ok(f"AR repo '{repo}' already exists — skipping.")
    else:
        _run([
            "gcloud", "artifacts", "repositories", "create", repo,
            "--repository-format", "docker",
            "--location", region,
        ])

    # Try gsutil first; fall back to gcloud storage (newer SDK)
    rc, _ = _capture(["gsutil", "ls", "-b", f"gs://{bucket}"])
    if rc == 0:
        _ok(f"Bucket gs://{bucket} already exists — skipping.")
    else:
        rc2, _ = _capture(["gsutil", "mb", "-l", region, f"gs://{bucket}"])
        if rc2 != 0:
            # gsutil mb returns non-zero for other errors too; try gcloud storage
            _run(["gcloud", "storage", "buckets", "create", f"gs://{bucket}",
                  "--location", region])


def build_image(cfg):
    _step(7, 9, f"Build and push Docker image  ({cfg['model']['id']})")

    dockerfile = Path(__file__).parent / "Dockerfile"
    if not dockerfile.exists():
        _abort(f"Dockerfile not found at {dockerfile}")

    _info(f"Image : {cfg['image']}")

    if _exists_gcloud([
        "gcloud", "artifacts", "docker", "images", "describe",
        f"{cfg['image']}:latest",
    ]):
        _ok("Image already exists in Artifact Registry — skipping build.")
        _info("To force a rebuild (e.g. to change model), run:")
        _info(f"  gcloud builds submit --config cloudbuild.yaml "
              f"--substitutions _KOPI_MODEL={cfg['model']['id']},_IMAGE={cfg['image']}")
        return

    _info("This may take 10-25 minutes.")
    print()

    config = Path(__file__).parent / "cloudbuild.yaml"
    if not config.exists():
        _abort(f"cloudbuild.yaml not found at {config}")

    _run([
        "gcloud", "builds", "submit",
        "--config", str(config),
        "--substitutions", f"_KOPI_MODEL={cfg['model']['id']},_IMAGE={cfg['image']}",
    ])


def create_service_account(cfg, project):
    _step(8, 9, "Service account + IAM")

    sa_name, sa_email = cfg["sa_name"], cfg["sa_email"]

    if _exists_gcloud(["gcloud", "iam", "service-accounts", "describe", sa_email]):
        _ok(f"Service account {sa_email} already exists.")
    else:
        _run([
            "gcloud", "iam", "service-accounts", "create", sa_name,
            "--display-name", "kopi-editor Cloud Run",
        ])

    _run([
        "gcloud", "projects", "add-iam-policy-binding", project,
        "--member", f"serviceAccount:{sa_email}",
        "--role", "roles/storage.objectAdmin",
    ])


def create_job(cfg):
    _step(9, 9, f"Cloud Run job  '{cfg['job_name']}'")

    region, job_name, image = cfg["region"], cfg["job_name"], cfg["image"]
    model, sa_email, bucket = cfg["model"], cfg["sa_email"], cfg["bucket"]

    if _exists_gcloud(["gcloud", "run", "jobs", "describe", job_name, "--region", region]):
        _info("Job already exists — updating image, resources, and service account.")
        _run([
            "gcloud", "run", "jobs", "update", job_name,
            "--image", image,
            "--command", "./entrypoint_llm.sh",
            "--region", region,
            "--cpu", model["cpu"],
            "--memory", model["mem"],
            "--service-account", sa_email,
            "--set-env-vars", f"KOPI_BUCKET={bucket},KOPI_MODEL={model['id']}",
        ])
    else:
        _run([
            "gcloud", "run", "jobs", "create", job_name,
            "--image", image,
            "--command", "./entrypoint_llm.sh",
            "--region", region,
            "--cpu", model["cpu"],
            "--memory", model["mem"],
            "--max-retries", "0",
            "--task-timeout", "60m",
            "--service-account", sa_email,
            "--set-env-vars", f"KOPI_BUCKET={bucket},KOPI_MODEL={model['id']}",
        ])


def finish(cfg, project):
    _header("Setup complete")
    print()
    _save_config(cfg, project)
    print()
    _info(f"run.py will read the config automatically — no environment variables needed.")
    _info(f"Model baked into image: {cfg['model']['id']}")
    print()
    print("  Run the pipeline:")
    print("    python run.py chapter.docx 1000")
    print("    (select [c] at the LLM prompt to use Cloud Run)")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    _header("kopi-editor  --  Google Cloud setup")
    print()
    print("  This script provisions the Cloud Run infrastructure for the")
    print("  LLM concision step. The deterministic pipeline always runs")
    print("  locally; only qualifying paragraphs are sent to the cloud.")
    print()
    print("  What will be created:")
    print("    - Artifact Registry Docker repository")
    print("    - GCS bucket (paragraph exchange)")
    print("    - Docker image (built via Cloud Build, model baked in)")
    print("    - Service account with GCS read/write access")
    print("    - Cloud Run job")
    print()
    print("  Prerequisites: gcloud CLI installed, project with billing enabled.")
    print()

    try:
        check_gcloud()
        authenticate()
        project = select_project()
        cfg = gather_config(project)
        enable_apis()
        create_infrastructure(cfg, project)
        build_image(cfg)
        create_service_account(cfg, project)
        create_job(cfg)
        finish(cfg, project)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
