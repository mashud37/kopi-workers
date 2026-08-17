"""Configure a cloud training backend (`vertex` or `hf`) without hand-editing files:
check credentials, list projects, buckets, or GPU flavours, write the picks to
config.local.yaml.
"""
import shutil
import subprocess

from cli import config, ui

_APIS = ["aiplatform.googleapis.com", "storage.googleapis.com"]
_REGIONS = ["us-central1", "us-east4", "europe-west4", "asia-southeast1"]
_MACHINES = {
    "a100-80": {"machine_type": "a2-ultragpu-1g", "accelerator_type": "NVIDIA_A100_80GB"},
    "a100-40": {"machine_type": "a2-highgpu-1g", "accelerator_type": "NVIDIA_A100_40GB"},
}
_HF_FLAVORS = [
    ("a100-large", "1x A100 80GB · $2.50/hr (recommended: sm_80, bnb-safe)"),
    ("h200", "1x H200 141GB · $5.00/hr (fastest: Hopper sm_90, bnb-safe)"),
    ("rtx-pro-6000", "1x RTX PRO 6000 96GB · $2.75/hr (Blackwell sm_120, needs a bnb build for it)"),
    ("l4x1", "1x L4 24GB · $0.80/hr (cheapest; 32B needs offload, slow)"),
]
_HF_NAMES = {name for name, _ in _HF_FLAVORS}
_CREDITS = "https://huggingface.co/settings/billing"


def run(args) -> None:
    backend = args.backend or config.backend()
    if backend == "hf":
        if args.no_input or args.flavor:
            return _hf_apply(args.flavor)
        return _hf_wizard()
    if args.no_input or any([args.project, args.bucket, args.region, args.machine]):
        return _apply(args.project, args.bucket, args.region, args.machine)
    _wizard()


def _apply(project, bucket, region, machine) -> None:
    updates = {"project": project, "region": region}
    if bucket:
        updates["bucket"] = bucket.removeprefix("gs://").strip("/")
    if machine:
        if machine not in _MACHINES:
            raise SystemExit(f"--machine must be one of: {', '.join(_MACHINES)}")
        updates.update(_MACHINES[machine])
    if not any(v for v in updates.values()):
        raise SystemExit("nothing to set, pass --project/--bucket/--region/--machine.")
    config.set_local("cloud", updates)
    ui.ok("config.local.yaml updated")
    if project:
        _ensure_apis(project)


def _set_hf(changes: dict) -> None:
    hf = {**config.hf_cfg(), **{k: v for k, v in changes.items() if v is not None}}
    config.set_local("cloud", {"backend": "hf", "hf": hf})


def _hf_apply(flavor) -> None:  # lint-style: ignore FN004
    if flavor and flavor not in _HF_NAMES:
        raise SystemExit(f"--flavor must be one of: {', '.join(sorted(_HF_NAMES))}")
    _set_hf({"flavor": flavor})
    ui.ok("config.local.yaml updated · backend hf")


def _hf_wizard() -> None:  # lint-style: ignore FN004
    ui.header("Cloud training setup (Hugging Face Jobs)")
    _ensure_hf_auth()
    ui.info(f"HF Jobs runs on pre-paid credits (no GPU-quota wait): top up at {_CREDITS}")

    chosen = ui.menu("Training GPU flavor", _HF_FLAVORS)
    if chosen is None:
        chosen = 0
    flavor = _HF_FLAVORS[chosen][0]

    namespace = ui.ask("HF namespace (user/org), blank for your account",
                       config.hf_cfg().get("namespace") or "")
    _set_hf({"flavor": flavor, "namespace": namespace or ""})
    ui.ok(f"saved · backend hf · flavor {flavor}" + (f" · namespace {namespace}" if namespace else ""))
    ui.info("next: python manage.py build  →  python manage.py train-cloud")


def _ensure_hf_auth() -> None:
    if not shutil.which("hf"):
        ui.warn("hf CLI not found, pip install -r requirements.txt, then `hf auth login`")
        return
    ui.step("Checking Hugging Face login (hf)")
    try:
        out = subprocess.run([shutil.which("hf") or "hf", "auth", "whoami"],
                             capture_output=True, text=True, timeout=60)
        who = out.stdout.strip()
    except Exception:
        who = ""
    if who and "Not logged in" not in who:
        ui.ok(f"logged in as {who.splitlines()[0]}")
        return
    ui.warn("not logged in to Hugging Face")
    if ui.confirm("Run `hf auth login` now?"):
        subprocess.call([shutil.which("hf") or "hf", "auth", "login"])
    else:
        ui.info("log in later: hf auth login")


def _wizard() -> None:
    ui.header("Cloud training setup (Vertex AI)")
    _ensure_auth()

    ui.step("Listing GCP projects (gcloud)")
    known = config.cloud().get("project") or _gcloud("config", "get-value", "project")
    listing = _gcloud("projects", "list", "--format=value(projectId)")
    projects = [line for line in listing.splitlines() if line.strip()]
    if projects:
        project = _pick("GCP project", projects, known)
    else:
        project = ui.ask("GCP project id", known) or _need("a project")

    _ensure_apis(project)
    region = _pick("Region (A100 availability)", _REGIONS, config.cloud().get("region") or _REGIONS[0])

    ui.step(f"Listing buckets in {project} (gcloud)")
    listing = _gcloud("storage", "buckets", "list", f"--project={project}", "--format=value(name)")
    buckets = [line.strip() for line in listing.splitlines() if line.strip()]
    chosen = ui.menu("GCS bucket (staging + adapter output)", buckets + ["(create a new bucket)"])
    if chosen is None:
        bucket = _need("a bucket")
    elif chosen == len(buckets):
        bucket = ui.ask("New bucket name (globally unique)") or _need("a bucket name")
        ui.step(f"Creating gs://{bucket} in {region} (gcloud)")
        code = subprocess.call([_exe(), "storage", "buckets", "create", f"gs://{bucket}",
                                f"--location={region}", f"--project={project}"])
        if code != 0:
            raise SystemExit("bucket creation failed, pick an existing bucket or a unique name.")
        ui.ok(f"created gs://{bucket}")
    else:
        bucket = buckets[chosen]

    machines = [
        ("a100-80", "1x A100 80GB · a2-ultragpu-1g (recommended for 32B)"),
        ("a100-40", "1x A100 40GB · a2-highgpu-1g (tighter, cheaper)"),
    ]
    chosen = ui.menu("Training GPU", machines)
    if chosen is None:
        chosen = 0
    machine = _MACHINES[machines[chosen][0]]

    config.set_local("cloud", {"project": project, "region": region, "bucket": bucket, **machine})
    ui.ok(f"saved · project {project} · gs://{bucket} · {machine['machine_type']} · {region}")
    ui.info("next: python manage.py build  →  python manage.py train-cloud")


def _ensure_auth() -> None:
    if not shutil.which("gcloud"):
        raise SystemExit("gcloud CLI not found, install the Google Cloud SDK first.")
    ui.step("Checking application-default credentials (gcloud)")
    if _gcloud("auth", "application-default", "print-access-token"):
        ui.ok("application-default credentials present")
        return
    ui.warn("no application-default credentials found")
    if ui.confirm("Run `gcloud auth application-default login` now?"):
        subprocess.call([_exe(), "auth", "application-default", "login"])
    else:
        ui.info("set them later: gcloud auth application-default login")


def _ensure_apis(project: str) -> None:
    if not shutil.which("gcloud"):
        ui.warn("gcloud not found, enable these APIs in the console: " + ", ".join(_APIS))
        return
    ui.step(f"Enabling required APIs in {project} (gcloud)")
    for i, api in enumerate(_APIS, 1):
        ui.info(f"[{i}/{len(_APIS)}] {api}")
        if subprocess.call([_exe(), "services", "enable", api, f"--project={project}"]) != 0:
            ui.warn(f"could not enable {api}, enable it in the console, then retry")
            continue
        ui.ok(f"{api} enabled")


def _pick(title: str, options: list, default):
    idx = ui.menu(title, options + ["(enter another)"])
    if idx is None:
        return default
    if idx == len(options):
        return ui.ask(title, default) or default
    return options[idx]


def _need(what: str):
    raise SystemExit(f"cloud training needs {what}.")


def _exe() -> str:
    return shutil.which("gcloud") or "gcloud"


def _gcloud(*args) -> str:
    try:
        out = subprocess.run([_exe(), *args], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:
        return ""
