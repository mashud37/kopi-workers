"""Run the QLoRA SFT on Hugging Face Jobs, the backend with no quota wait: stage
code and datasets to a private repo, launch a GPU job, then `pull` the adapter.
"""
import time
from datetime import datetime

from cli import config, ui
from cloud import _common

_TERMINAL = {"COMPLETED", "ERROR", "CANCELED", "CANCELLED", "DELETED"}
_IMAGE = "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime"


def submit() -> None:
    cfg = config.hf_cfg()
    if not cfg.get("flavor"):
        raise SystemExit("config.yaml cloud.hf.flavor is unset, run `python manage.py cloud-setup "
                         "--backend hf`.")
    if not (config.data_dir() / "out" / "sft_train.jsonl").exists():
        raise SystemExit("missing data/out/sft_train.jsonl, run `python manage.py build` first.")
    ui.step("HF Jobs QLoRA SFT: 1 stage code · 2 stage data · 3 submit (async)")
    ui.info("loading the Hugging Face SDK…")
    hub = _sdk()
    token = hub.get_token()
    if not token:
        raise SystemExit("not logged in to Hugging Face, run `python manage.py cloud-setup "
                         "--backend hf` (offers `hf auth login`).")
    namespace = (cfg.get("namespace") or "").strip()

    run = "sft-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    repo = (f"{namespace}/" if namespace else "") + f"kopi-learner-{run}"
    api = hub.HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    api.create_repo(repo, repo_type="model", private=True, exist_ok=True)

    _stage(api, repo)
    job_id = _launch(hub, repo, cfg, token, namespace)

    _common.save_run(run, {
        "backend": "hf",
        "job": job_id,
        "repo": repo,
        "namespace": namespace,
        "flavor": cfg["flavor"],
    })
    ui.ok(f"submitted: job {job_id} · flavor {cfg['flavor']}")
    ui.info("it runs on HF; your terminal is free. Billing stops when the job ends.")
    ui.info(f"watch:  python manage.py train-status --run {run} --wait")
    ui.info(f"then:   python manage.py pull-adapter --run {run}")


def status(run: str | None, wait: bool) -> None:
    loaded = _common.load_run(run)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Checking HF job {run}")
    ui.info("loading the Hugging Face SDK…")
    hub = _sdk()
    stage = _stage_of(hub, rec)
    ui.info(f"{run}: {stage}")
    if wait:
        start = time.monotonic()
        while stage not in _TERMINAL:
            time.sleep(30)
            stage = _stage_of(hub, rec)
            ui.info(f"[{int((time.monotonic() - start) // 60)}m] {stage}")
    if stage == "COMPLETED":
        ui.ok(f"finished: pull it with python manage.py pull-adapter --run {run}")
    elif stage in _TERMINAL:
        ui.warn(f"job ended without success: {stage}")


def _stage_of(hub, rec: dict) -> str:
    job = hub.inspect_job(job_id=rec["job"], namespace=rec.get("namespace") or None)
    return getattr(job.status, "stage", "UNKNOWN")


def _stage(api, repo: str) -> None:
    ui.step("[1/3] staging training code")
    api.upload_file(path_or_fileobj=str(_common.code_tar()), path_in_repo="code.tar.gz",
                    repo_id=repo, repo_type="dataset")
    ui.ok(f"code -> {repo} (dataset)")

    files = sorted((config.data_dir() / "out").glob("*.jsonl"))
    ui.step(f"[2/3] staging {len(files)} dataset file(s)")
    for i, f in enumerate(files, 1):
        ui.info(f"[{i}/{len(files)}] {f.name}")
        api.upload_file(path_or_fileobj=str(f), path_in_repo=f"data/out/{f.name}",
                        repo_id=repo, repo_type="dataset")


def _launch(hub, repo: str, cfg: dict, token: str, namespace: str) -> str:
    bootstrap = (
        "set -e; pip install -q -U 'huggingface_hub>=1.8.0'; "
        "mkdir -p /workspace && cd /workspace; "
        f"hf download {repo} --repo-type dataset --local-dir run; "
        "tar xzf run/code.tar.gz; "
        # No `-U`: exact pins replace the image's torch/torchvision as a matched
        # pair; `-U` strands torchvision and re-breaks the build (see reqs file).
        "pip install -q -r requirements-train.txt; "
        "KOPI_RUN_DIR=$PWD/run python -m cloud.train_entry; "
        f"hf upload {repo} data/adapters/sft --repo-type model"
    )
    ui.step(f"[3/3] submitting Job · {cfg['flavor']}")
    try:
        job = hub.run_job(
            image=cfg.get("image") or _IMAGE,
            command=["bash", "-lc", bootstrap],
            flavor=cfg["flavor"],
            timeout=cfg.get("timeout", "6h"),
            secrets={"HF_TOKEN": token},
            namespace=namespace or None,
        )
    except Exception as e:
        _explain(e)
        raise
    return job.id


def _explain(e: Exception) -> None:
    msg = str(e).lower()
    if "payment" in msg or "credit" in msg or "quota" in msg or "402" in msg:
        raise SystemExit(
            "HF Jobs needs pre-paid credits on your account, add them, then re-run train-cloud:\n"
            "  https://huggingface.co/settings/billing"
        ) from None
    if "401" in msg or "403" in msg or "token" in msg or "authenticated" in msg:
        raise SystemExit(
            "HF authentication failed, log in, then re-run train-cloud:\n"
            "  python manage.py cloud-setup --backend hf   (offers `hf auth login`)"
        ) from None


def pull(run: str | None) -> None:
    loaded = _common.load_run(run)
    run, rec = loaded["name"], loaded["record"]
    ui.step(f"Fetching adapter for {run} from {rec['repo']} (model)")
    ui.info("loading the Hugging Face SDK…")
    hub = _sdk()
    dest = config.data_dir() / "adapters" / "sft"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        hub.snapshot_download(repo_id=rec["repo"], repo_type="model", local_dir=str(dest))
    except Exception as e:
        _explain(e)
        raise SystemExit(f"no adapter in {rec['repo']} yet, "
                         f"check `python manage.py train-status --run {run}`.") from None
    ui.ok(f"adapter -> {dest}  (also kept in {rec['repo']})")
    ui.info("serve: vLLM --enable-lora --lora-modules kopi=<dir> over Qwen3-32B-AWQ "
            "(gcloud-model-serving.md); no merge needed.")


def _sdk():
    try:
        import huggingface_hub
    except ImportError as e:
        raise SystemExit(
            "HF submit needs the Hugging Face SDK, pip install -r requirements.txt "
            "(huggingface_hub>=1.8.0)."
        ) from e
    return huggingface_hub
