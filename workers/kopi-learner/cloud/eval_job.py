"""Submit the held-out A/B (base vs `kopi` LoRA) as a CPU-only Vertex job
driving the served Qwen, writing edits to GCS. `status` polls it, `pull`
grades against Opus's gold.
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path

from cli import config, ui
from cloud import _common, vertex

_STORE = config.data_dir() / "eval" / "eval_runs.json"
# CPU-only by design: the loop is pure HTTP to the served Qwen, so it must NOT use the
# GPU training image (cloud.container_uri): Vertex rejects a GPU image with no
# accelerator attached. Vertex's prebuilt CPU PyTorch container starts instantly.
_CPU_IMAGE = "us-docker.pkg.dev/vertex-ai/training/pytorch-cpu.2-4.py310:latest"


def submit(adapter: str = "kopi") -> None:
    target = vertex._target()
    project, bucket, cfg = target["project"], target["bucket"], target["config"]
    from eval import baseline
    baseline._require_endpoint()
    reqs = baseline.build_requests(baseline._load_test())

    run = "eval-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"kopi-learner/{run}"
    region = cfg.get("region", "us-central1")
    ui.step("Vertex eval: 1 stage code · 2 stage requests · 3 submit (async)")
    ui.info("loading google-cloud SDKs…")
    sdks = vertex._sdks()
    storage, aiplatform = sdks["storage"], sdks["aiplatform"]
    gbucket = storage.Client(project=project).bucket(bucket)

    ui.step("[1/3] staging eval code")
    vertex._upload(gbucket, f"{prefix}/code.tar.gz", _common.code_tar())
    ui.step(f"[2/3] staging {len(reqs)} eval request(s)")
    tmp = Path(tempfile.gettempdir()) / "kopi-eval-requests.jsonl"
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in reqs) + "\n", encoding="utf-8")
    vertex._upload(gbucket, f"{prefix}/eval/requests.jsonl", tmp)

    name = _launch(aiplatform, _spec(project, bucket, prefix, cfg, adapter))
    _common.save_run(run, {
        "backend": "eval-vertex",
        "job": name,
        "region": region,
        "bucket": bucket,
        "adapter": adapter,
    }, store=_STORE)
    ui.ok(f"submitted: {name}")
    ui.info("it runs on Vertex (CPU); your terminal is free. Billing stops when the job ends.")
    ui.info(f"watch:  python manage.py eval-status --run {run} --wait")
    ui.info(f"then:   python manage.py pull-eval --run {run}")


def _spec(project: str, bucket: str, prefix: str, cfg: dict, adapter: str) -> dict:
    gcs = f"/gcs/{bucket}/{prefix}"  # Vertex auto-mounts buckets under /gcs
    ecfg = cfg.get("eval", {})
    return {
        "project": project,
        "bucket": bucket,
        "prefix": prefix,
        "region": cfg.get("region", "us-central1"),
        "machine": ecfg.get("machine_type", "n1-standard-4"),
        "image": ecfg.get("container_uri") or _CPU_IMAGE,
        "timeout": int(ecfg.get("timeout_seconds", 2 * 3600)),
        # The loop is pure stdlib (cloud/eval_entry.py), no pip install, so the CPU
        # image starts instantly; never the GPU training image (needs an accelerator).
        "cmd": ("set -e; mkdir -p /workspace && cd /workspace && "
                f"cp {gcs}/code.tar.gz . && tar xzf code.tar.gz && python -m cloud.eval_entry"),
        # Token rides in env, never the command string, so it stays out of job logs.
        "env": [
            {"name": "KOPI_EVAL_DIR", "value": gcs},
            {"name": "KOPI_QWEN_URL", "value": config.qwen_base_url()},
            {"name": "KOPI_QWEN_TOKEN", "value": config.qwen_token()},
            {"name": "KOPI_ADAPTER", "value": adapter},
        ],
    }


def _launch(aiplatform, spec: dict) -> str:
    ui.step(f"[3/3] submitting CPU CustomJob to {spec['project']}/{spec['region']} · {spec['machine']}")
    aiplatform.init(project=spec["project"], location=spec["region"],
                    staging_bucket=f"gs://{spec['bucket']}")
    job = aiplatform.CustomJob(
        display_name=f"kopi-learner-{spec['prefix'].split('/')[-1]}",
        worker_pool_specs=[{
            "machine_spec": {"machine_type": spec["machine"]},
            "replica_count": 1,
            "container_spec": {"image_uri": spec["image"],
                               "command": ["bash", "-c", spec["cmd"]], "env": spec["env"]},
        }],
        base_output_dir=f"gs://{spec['bucket']}/{spec['prefix']}/vertex",
    )
    try:
        job.submit(timeout=spec["timeout"])  # async: does not block
    except Exception as e:
        vertex._explain(e, spec["project"])
        raise
    return job.resource_name


def status(run: str | None, wait: bool) -> None:
    loaded = _common.load_run(run, store=_STORE)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Checking Vertex eval job {run}")
    ui.info("loading google-cloud SDKs…")
    aiplatform = vertex._sdks()["aiplatform"]
    aiplatform.init(project=config.gcp_project(), location=rec["region"])
    state = aiplatform.CustomJob.get(rec["job"]).state.name
    ui.info(f"{run}: {state}")
    if wait and state not in vertex._TERMINAL:
        state = vertex._poll(aiplatform, rec["job"])
    if state == "JOB_STATE_SUCCEEDED":
        ui.ok(f"finished: pull it with python manage.py pull-eval --run {run}")
    elif state in vertex._TERMINAL:
        ui.warn(f"job ended without success: {state}")


def pull(run: str | None) -> None:
    loaded = _common.load_run(run, store=_STORE)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Fetching eval edits for {run} from GCS")
    ui.info("loading google-cloud SDKs…")
    storage = vertex._sdks()["storage"]
    bucket = rec["bucket"]
    key = f"kopi-learner/{run}/eval/edits.jsonl"
    blob = storage.Client(project=config.gcp_project()).bucket(bucket).blob(key)
    if not blob.exists():
        raise SystemExit(f"no edits at gs://{bucket}/{key} yet, "
                         f"check `python manage.py eval-status --run {run}`.")
    dest = config.data_dir() / "eval" / f"{run}.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(dest))
    rows = [json.loads(line) for line in dest.read_text(encoding="utf-8").splitlines() if line.strip()]
    ui.ok(f"{len(rows)} edits -> {dest}  (also kept at gs://{bucket}/{key})")
    from eval import baseline
    baseline.score_edits(rows)
