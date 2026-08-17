"""Run inside the cloud training container: copy the staged datasets from KOPI_RUN_DIR,
run the QLoRA SFT, write the adapter to KOPI_OUT_DIR for the backend to ship.
"""
import os
import shutil
from pathlib import Path

from cli import config, ui


def main() -> None:
    run_dir = os.environ.get("KOPI_RUN_DIR") or os.environ.get("KOPI_RUN_GCS")
    if not run_dir:
        raise SystemExit("KOPI_RUN_DIR unset, launch via `python manage.py train-cloud`.")
    run = Path(run_dir)

    out = config.data_dir() / "out"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted((run / "data" / "out").glob("*.jsonl"))
    ui.step(f"staging {len(files)} dataset file(s) from {run / 'data' / 'out'}")
    for i, f in enumerate(files, 1):
        ui.info(f"[{i}/{len(files)}] {f.name}")
        shutil.copy(f, out / f.name)

    from train import sft
    sft.run()

    adir = config.data_dir() / "adapters" / "sft"
    out_dir = os.environ.get("KOPI_OUT_DIR")
    if not out_dir:
        ui.ok(f"adapter written to {adir}, the backend will ship it")
        return
    items = sorted(p for p in adir.rglob("*") if p.is_file()
                   and not any(part.startswith("checkpoint-") for part in p.relative_to(adir).parts))
    dst = Path(out_dir)
    ui.step(f"uploading {len(items)} adapter file(s) -> {dst}")
    for i, p in enumerate(items, 1):
        rel = p.relative_to(adir)
        ui.info(f"[{i}/{len(items)}] {rel}")
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dst / rel)
    ui.ok("adapter written out, pull it with `python manage.py pull-adapter`")


if __name__ == "__main__":
    main()
