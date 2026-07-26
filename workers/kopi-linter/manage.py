#!/usr/bin/env python3
import argparse
import sys

from cli import eval_cmd, evidence_cmd, experiment_cmd, induce_cmd, install, lint_cmd, ui
from cli import menu as menu_mod
from lint import bands


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Deterministic, fully local plain-language linter for academic prose.",
    )
    sub = parser.add_subparsers(dest="command")

    evidence = sub.add_parser(
        "evidence", help="Mine the gold edit corpus into a transformation report"
    )
    evidence.add_argument("--role", choices=["opus", "qwen", "all"],
                          help="whose edits to analyse (default: ask)")
    evidence.add_argument("-n", "--limit", type=int, help="stop after this many edits")

    linter = sub.add_parser("lint", help="Lint a document and write the edited text")
    linter.add_argument("file", nargs="?",
                        help="a .md or .txt file, bare names resolve against input/")
    linter.add_argument("--band", default="firm", choices=bands.BANDS,
                        help="editing intensity (default: firm)")

    scorer = sub.add_parser("evaluate", help="Score the linter against Opus on the gold corpus")
    scorer.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")
    scorer.add_argument("--show", action="store_true", help="show edits Opus did not make")

    experiment = sub.add_parser(
        "experiment", help="Compare every method for one transformation family"
    )
    experiment.add_argument("family", nargs="?", help="family to compare (default: ask)")
    experiment.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")

    inducer = sub.add_parser("induce", help="Rebuild rule tables from the gold corpus")
    inducer.add_argument("--family", default="support-verb", choices=induce_cmd.FAMILIES,
                         help="which table to rebuild (default: support-verb)")
    inducer.add_argument("--minimum", type=int, default=4,
                         help="fewest observations for a construction to be tabled")

    sub.add_parser("install", help="Check dependencies, models, and the corpus link")
    return parser


def main():
    args = _parser().parse_args()
    if args.command is None:
        return menu_mod.main()
    if args.command == "evidence":
        return evidence_cmd.run(role=args.role, limit=args.limit)
    if args.command == "lint":
        return lint_cmd.run(name=args.file, band_name=args.band)
    if args.command == "evaluate":
        return eval_cmd.run(limit=args.limit, show=args.show)
    if args.command == "experiment":
        return experiment_cmd.run(family=args.family, limit=args.limit)
    if args.command == "induce":
        return induce_cmd.run(minimum=args.minimum, family=args.family)
    if args.command == "install":
        return install.run()


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
