#!/usr/bin/env python3
import argparse
import sys

from cli import commands, install, ui
from cli import menu as menu_mod


def _add_data_parsers(sub) -> None:
    sub.add_parser("install", help="Check kopi-editor link, credentials, and corpus")
    sub.add_parser("mine", help="PRIMARY: harvest existing kopi-editor edit bundles into samples")

    d = sub.add_parser("documents", help="Run your input/ documents through served Qwen + Opus")
    d.add_argument("--batch", action="store_true", help="send Opus via the Batch API (50%% cheaper)")

    c = sub.add_parser("complete", help="Fill the missing model side of mined paragraphs (for DPO)")
    c.add_argument("--fill", choices=["qwen", "opus", "both"], default="both")
    c.add_argument("--limit", type=int, help="cap paragraphs to complete")
    c.add_argument("--batch", action="store_true", help="send the Opus side via the Batch API")

    g = sub.add_parser("generate", help="EXPANSION: edit fresh pepa-prep paragraphs with Opus + Qwen")
    g.add_argument("--papers", type=int, help="number of papers to sample")
    g.add_argument("--max-paragraphs", type=int, help="hard cap on paragraphs (cost guard)")
    g.add_argument("--seed", type=int, help="sampling seed")
    g.add_argument("--batch", action="store_true", help="send Opus via the Batch API")

    cl = sub.add_parser("collect", help="Collect finished Opus Batch API jobs into samples")
    cl.add_argument("--batch", dest="batch_id", help="a specific batch id (default: all pending)")
    cl.add_argument("--wait", action="store_true", help="poll until pending batches finish")

    sub.add_parser("build", help="Assemble train/val/test SFT + DPO datasets from samples")


def _add_train_parsers(sub) -> None:
    sub.add_parser("train-sft", help="QLoRA supervised fine-tune toward Opus's edits (local GPU)")

    cs = sub.add_parser("cloud-setup", help="Configure a cloud backend (Vertex or HF Jobs)")
    cs.add_argument("--backend", choices=["vertex", "hf"], help="cloud training backend")
    cs.add_argument("--project", help="GCP project id (vertex)")
    cs.add_argument("--bucket", help="GCS bucket for staging + adapter output (vertex)")
    cs.add_argument("--region", help="training region, A100 availability (vertex)")
    cs.add_argument("--machine", choices=["a100-80", "a100-40"], help="GPU shape (vertex)")
    cs.add_argument("--flavor", choices=["a100-large", "h200", "rtx-pro-6000", "l4x1"],
                    help="GPU flavor (hf)")
    cs.add_argument("--no-input", action="store_true", help="apply flags only; no prompts")

    sub.add_parser("train-cloud", help="Submit the QLoRA SFT to the configured backend (async)")

    ts = sub.add_parser("train-status", help="Check or wait on a submitted training job")
    ts.add_argument("--run", help="run id (default: the last submitted run)")
    ts.add_argument("--wait", action="store_true", help="poll until the job finishes")

    pa = sub.add_parser("pull-adapter", help="Download a trained adapter to data/adapters")
    pa.add_argument("--run", help="run id to pull (default: the last submitted run)")

    sub.add_parser("train-dpo", help="Preference align (after SFT + eval), gated")

    e = sub.add_parser("evaluate", help="Held-out baseline: base vs tuned vs Opus gold (served Qwen)")
    e.add_argument("--adapter", default="kopi",
                   help="served LoRA module name to evaluate against the base (default: kopi)")
    e.add_argument("--rescore", action="store_true",
                   help="re-grade the last run's saved edits (no inference), use after a metric change")

    sub.add_parser("eval-failures",
                   help="Bucket the last eval's guard rejections by reason and mode (no inference)")

    ec = sub.add_parser("evaluate-cloud",
                        help="Run the held-out A/B on Vertex (CPU, async), no laptop babysitting")
    ec.add_argument("--adapter", default="kopi", help="served LoRA module to A/B (default: kopi)")

    es = sub.add_parser("eval-status", help="Check or wait on a submitted eval job")
    es.add_argument("--run", help="eval run id (default: the last submitted eval run)")
    es.add_argument("--wait", action="store_true", help="poll until the job finishes")

    pe = sub.add_parser("pull-eval", help="Download a finished eval's edits and score the verdict")
    pe.add_argument("--run", help="eval run id to pull (default: the last submitted eval run)")

    m = sub.add_parser("merge", help="Merge an adapter into base weights for vLLM serving")
    m.add_argument("--adapter", default="sft", help="adapter to merge (default: sft)")


def _build_parser() -> argparse.ArgumentParser:  # lint-style: ignore FN004
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Distil Opus academic copy-edits into a LoRA adapter for the served Qwen3 editor.")
    sub = parser.add_subparsers(dest="command")
    _add_data_parsers(sub)
    _add_train_parsers(sub)
    return parser


_DISPATCH = {
    "install": lambda a: install.run(),
    "mine": lambda a: commands.mine(),
    "documents": lambda a: commands.documents(a.batch),
    "complete": lambda a: commands.complete(a.fill, a.limit, a.batch),
    "generate": lambda a: commands.generate(a.papers, a.max_paragraphs, a.seed, a.batch),
    "collect": lambda a: commands.collect(a.batch_id, a.wait),
    "build": lambda a: commands.build(),
    "train-sft": lambda a: commands.train_sft(),
    "cloud-setup": lambda a: commands.cloud_setup(a),
    "train-cloud": lambda a: commands.train_cloud(),
    "train-status": lambda a: commands.train_status(a.run, a.wait),
    "pull-adapter": lambda a: commands.pull_adapter(a.run),
    "train-dpo": lambda a: commands.train_dpo(),
    "evaluate": lambda a: commands.evaluate(a.adapter, a.rescore),
    "eval-failures": lambda a: commands.eval_failures(),
    "evaluate-cloud": lambda a: commands.evaluate_cloud(a.adapter),
    "eval-status": lambda a: commands.eval_status(a.run, a.wait),
    "pull-eval": lambda a: commands.pull_eval(a.run),
    "merge": lambda a: commands.merge(a.adapter),
}


def main():
    args = _build_parser().parse_args()
    if args.command is None:
        return menu_mod.main()
    _DISPATCH[args.command](args)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):
            ui.error(e.code)
            sys.exit(1)
        raise
