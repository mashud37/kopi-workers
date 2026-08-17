"""Thin argparse command handlers that dispatch into the packages
implementing mine, documents, complete, generate, collect, build, train, and
evaluate; no logic lives here.
"""
from cli import config, ui


def mine() -> None:
    from distil import pairs
    pairs.mine_to_disk()
    ui.info("next: `complete` to fill missing pairs, or `build` to assemble datasets")


def documents(batch: bool) -> None:
    from distil import pairs
    pairs.documents_to_disk(batch)


def complete(fill: str, limit: int | None, batch: bool) -> None:
    from distil import complete as complete_mod
    complete_mod.run(fill, limit, batch)


def generate(papers: int | None, max_paragraphs: int | None, seed: int | None, batch: bool) -> None:
    from distil import pairs
    s = config.settings().get("sample", {})
    pairs.generate_to_disk(
        papers=papers if papers is not None else int(s.get("papers", 80)),
        max_paragraphs=max_paragraphs if max_paragraphs is not None else int(s.get("max_paragraphs", 400)),
        seed=seed if seed is not None else int(s.get("seed", 7)),
        batch=batch,
    )


def collect(batch_id: str | None, wait: bool) -> None:
    from distil import batch
    batch.collect(batch_id, wait)
    ui.info("next: `python manage.py build`")


def build() -> None:
    from distil import dataset
    dataset.build()
    ui.info("next: `python manage.py train-sft`")


def train_sft() -> None:
    from train import sft
    sft.run()


def cloud_setup(args) -> None:
    from cli import cloud_setup as wizard
    wizard.run(args)


def _driver(name: str):
    from cloud import hf, vertex
    return {"vertex": vertex, "hf": hf}.get(name, vertex)


def train_cloud() -> None:
    _driver(config.backend()).submit()


def train_status(run: str | None, wait: bool) -> None:
    from cloud import _common
    rec = _common.load_run(run)["record"]
    _driver(rec.get("backend", "vertex")).status(run, wait)


def pull_adapter(run: str | None) -> None:
    from cloud import _common
    rec = _common.load_run(run)["record"]
    _driver(rec.get("backend", "vertex")).pull(run)


def train_dpo() -> None:
    from train import dpo
    dpo.run()


def evaluate(adapter: str, rescore: bool = False) -> None:
    from eval import baseline
    baseline.score_saved() if rescore else baseline.run(adapter)


def eval_failures() -> None:
    from eval import failures
    failures.run()


def evaluate_cloud(adapter: str) -> None:
    from cloud import eval_job
    eval_job.submit(adapter)


def eval_status(run: str | None, wait: bool) -> None:
    from cloud import eval_job
    eval_job.status(run, wait)


def pull_eval(run: str | None) -> None:
    from cloud import eval_job
    eval_job.pull(run)


def merge(adapter: str) -> None:
    from train import setup
    setup.merge(setup.ADAPTERS / adapter, setup.ADAPTERS / f"{adapter}-merged")
