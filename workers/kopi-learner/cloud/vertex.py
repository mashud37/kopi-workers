"""Submit the QLoRA SFT as an asynchronous single-A100 Vertex CustomJob and
return at once; `status` polls it and `pull` downloads the finished adapter
to data/adapters/sft.
"""
import time
from datetime import datetime

from cli import config, ui
from cloud import _common

_TERMINAL = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


def submit() -> None:
    target = _target()
    project, bucket, cfg = target["project"], target["bucket"], target["config"]
    if not (config.data_dir() / "out" / "sft_train.jsonl").exists():
        raise SystemExit("missing data/out/sft_train.jsonl, run `python manage.py build` first.")
    ui.step("Vertex QLoRA SFT: 1 stage code · 2 stage data · 3 submit (async)")
    ui.info("loading google-cloud SDKs…")
    sdks = _sdks()
    storage, aiplatform = sdks["storage"], sdks["aiplatform"]

    run = "sft-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"kopi-learner/{run}"
    region = cfg.get("region", "us-central1")

    gbucket = storage.Client(project=project).bucket(bucket)
    ui.step("[1/3] staging training code")
    _upload(gbucket, f"{prefix}/code.tar.gz", _common.code_tar())
    ui.ok(f"code -> gs://{bucket}/{prefix}/code.tar.gz")

    files = sorted((config.data_dir() / "out").glob("*.jsonl"))
    ui.step(f"[2/3] staging {len(files)} dataset file(s)")
    for i, path in enumerate(files, 1):
        ui.info(f"[{i}/{len(files)}] {path.name}")
        _upload(gbucket, f"{prefix}/data/out/{path.name}", path)

    name = _launch(aiplatform, project, bucket, prefix, cfg)

    _common.save_run(run, {"backend": "vertex", "job": name, "region": region, "bucket": bucket})
    ui.ok(f"submitted: {name}")
    ui.info("it runs on Vertex; your terminal is free. Billing stops when the job ends.")
    ui.info(f"watch:  python manage.py train-status --run {run} --wait")
    ui.info(f"then:   python manage.py pull-adapter --run {run}")


def status(run: str | None, wait: bool) -> None:
    loaded = _common.load_run(run)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Checking Vertex job {run}")
    ui.info("loading google-cloud SDKs…")
    aiplatform = _sdks()["aiplatform"]
    aiplatform.init(project=config.gcp_project(), location=rec["region"])
    job = aiplatform.CustomJob.get(rec["job"])
    state = job.state.name
    ui.info(f"{run}: {state}")
    if wait:
        start = time.monotonic()
        while state not in _TERMINAL:
            time.sleep(30)
            state = aiplatform.CustomJob.get(rec["job"]).state.name
            ui.info(f"[{int((time.monotonic() - start) // 60)}m] {state}")
    if state == "JOB_STATE_SUCCEEDED":
        ui.ok(f"finished: pull it with python manage.py pull-adapter --run {run}")
    elif state in _TERMINAL:
        ui.warn(f"job ended without success: {state}")


def _launch(aiplatform, project: str, bucket: str, prefix: str, cfg: dict) -> str:
    gcs = f"/gcs/{bucket}/{prefix}"  # Vertex auto-mounts buckets under /gcs
    cmd = (
        "set -e; mkdir -p /workspace && cd /workspace && "
        f"cp {gcs}/code.tar.gz . && tar xzf code.tar.gz && "
        # No `-U`: the exact pins in requirements-train.txt must replace the
        # prebuilt image's torch/torchvision as a matched pair. `-U` strands
        # torchvision and re-breaks the build (see requirements-train.txt).
        "pip install -q -r requirements-train.txt && "
        f"KOPI_RUN_DIR={gcs} KOPI_OUT_DIR={gcs}/adapters/sft python -m cloud.train_entry"
    )
    region = cfg.get("region", "us-central1")
    ui.step(f"[3/3] submitting CustomJob to {project}/{region} · {cfg['machine_type']} "
            f"({cfg['accelerator_type']})")
    aiplatform.init(project=project, location=region, staging_bucket=f"gs://{bucket}")
    job = aiplatform.CustomJob(
        display_name=f"kopi-learner-{prefix.split('/')[-1]}",
        worker_pool_specs=[{
            "machine_spec": {
                "machine_type": cfg["machine_type"],
                "accelerator_type": cfg["accelerator_type"],
                "accelerator_count": int(cfg.get("accelerator_count", 1)),
            },
            "replica_count": 1,
            # The default 100GB boot disk can't hold the ~62GB Qwen3-32B download
            # plus the CUDA pip layer and HF cache, it fills mid-download and
            # fails after GPU billing has already started. Size it generously.
            "disk_spec": {
                "boot_disk_type": cfg.get("boot_disk_type", "pd-ssd"),
                "boot_disk_size_gb": int(cfg.get("boot_disk_gb", 200)),
            },
            "container_spec": {"image_uri": cfg["container_uri"], "command": ["bash", "-c", cmd]},
        }],
        base_output_dir=f"gs://{bucket}/{prefix}/vertex",
    )
    try:
        # timeout caps total run time so a hung job can't bill indefinitely:
        # the laptop walks away after submit, so this is the only budget brake.
        job.submit(timeout=int(cfg.get("timeout_seconds", 6 * 3600)))  # async: does not block
    except Exception as e:
        _explain(e, project)
        raise
    return job.resource_name


def _explain(e: Exception, project: str) -> None:
    msg = str(e)
    if "SERVICE_DISABLED" in msg or "has not been used in project" in msg:
        raise SystemExit(
            f"Vertex AI API isn't enabled on {project}. Enable it, then re-run train-cloud:\n"
            f"  python manage.py cloud-setup --project {project}"
        ) from None
    if "RESOURCE_EXHAUSTED" in msg or "exceed quota" in msg:
        raise SystemExit(
            "no GPU quota for this machine here: Vertex custom-training GPU quota defaults to 0.\n"
            f"  request it: https://console.cloud.google.com/iam-admin/quotas?project={project}\n"
            "  (service Vertex AI API, metric 'custom model training … gpus', region = your region)\n"
            f"  or try another GPU/region: python manage.py cloud-setup --project {project} "
            "--machine a100-40 --region us-central1\n"
            "  or switch to the Hugging Face backend (no quota wait): "
            "python manage.py cloud-setup --backend hf"
        ) from None


def pull(run: str | None) -> None:
    loaded = _common.load_run(run)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Fetching adapter for {run} from GCS")
    ui.info("loading google-cloud SDKs…")
    storage = _sdks()["storage"]
    bucket = rec["bucket"]
    prefix = f"kopi-learner/{run}/adapters/sft"
    gbucket = storage.Client(project=config.gcp_project()).bucket(bucket)
    blobs = [b for b in gbucket.list_blobs(prefix=prefix)
             if not b.name.endswith("/") and "/checkpoint-" not in b.name[len(prefix):]]
    if not blobs:
        raise SystemExit(f"no adapter at gs://{bucket}/{prefix} yet, "
                         f"check `python manage.py train-status --run {run}`.")

    dest = config.data_dir() / "adapters" / "sft"
    dest.mkdir(parents=True, exist_ok=True)
    ui.step(f"downloading {len(blobs)} adapter file(s) from gs://{bucket}/{prefix}")
    for i, blob in enumerate(blobs, 1):
        rel = blob.name[len(prefix) + 1:]
        ui.info(f"[{i}/{len(blobs)}] {rel}")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
    ui.ok(f"adapter -> {dest}  (also kept at gs://{bucket}/{prefix})")
    ui.info("serve: vLLM --enable-lora --lora-modules kopi=<dir> over Qwen3-32B-AWQ "
            "(gcloud-model-serving.md); no merge needed.")


def _target() -> dict:
    """The `project`, staging `bucket` and `config` a Vertex job needs."""
    project = config.gcp_project()
    cfg = config.cloud()
    bucket = (cfg.get("bucket") or "").removeprefix("gs://").strip("/")
    if not project:
        raise SystemExit("no GCP project, set PROJECT in kopi-editor's env.yaml or KOPI_PROJECT.")
    if not bucket:
        raise SystemExit("no cloud.bucket in config.yaml, set a gs:// bucket for staging + output.")
    for key in ("machine_type", "accelerator_type", "container_uri"):
        if not cfg.get(key):
            raise SystemExit(f"config.yaml cloud.{key} is unset.")
    return {"project": project, "bucket": bucket, "config": cfg}


def _sdks() -> dict:
    """The Google Cloud clients this module uses, under `storage` and `aiplatform`."""
    try:
        from google.cloud import aiplatform, storage
    except ImportError as e:
        raise SystemExit(
            "Vertex submit needs the cloud SDKs, pip install -r requirements.txt "
            "(google-cloud-aiplatform, google-cloud-storage)."
        ) from e
    return {"storage": storage, "aiplatform": aiplatform}


def _upload(bucket, key: str, path) -> None:
    bucket.blob(key).upload_from_filename(str(path))
