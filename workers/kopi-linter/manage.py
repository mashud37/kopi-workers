#!/usr/bin/env python3
import argparse
import sys

from cli import (
    allocate_cmd,
    damage_cmd,
    encoder_cmd,
    eval_cmd,
    evidence_cmd,
    execute_cmd,
    experiment_cmd,
    induce_cmd,
    install,
    lint_cmd,
    probe_cmd,
    rank_cmd,
    sentence_cmd,
    tag_cmd,
    ui,
)
from cli import menu as menu_mod
from evidence import load
from execute import backends, decoder
from lint import bands


def _measurement_parsers(sub) -> None:
    """Subcommands that read the gold corpus and write a report."""
    evidence = sub.add_parser(
        "evidence", help="Mine the gold edit corpus into a transformation report"
    )
    evidence.add_argument("--role", choices=["opus", "qwen", "all"],
                          help="whose edits to analyse (default: ask)")
    evidence.add_argument("-n", "--limit", type=int, help="stop after this many edits")

    experiment = sub.add_parser(
        "experiment", help="Compare every method for one transformation family"
    )
    experiment.add_argument("family", nargs="?", help="family to compare (default: ask)")
    experiment.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")
    experiment.add_argument("--split", default="all", choices=load.SPLITS, help="which documents to score on (default: all)")

    ranker = sub.add_parser(
        "rank", help="Compare scoring functions for which phrase to drop first"
    )
    ranker.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")
    ranker.add_argument("--split", default="all", choices=load.SPLITS, help="which documents to score on (default: all)")

    executor = sub.add_parser(
        "execute", help="Probe whether a local backend can perform the gold edits"
    )
    executor.add_argument("--backend", choices=backends.NAMES, help="one backend (default: the free ones)")
    executor.add_argument("--family", help="score only this transformation family")
    executor.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")
    executor.add_argument("--transport", default=decoder.DEFAULT_TRANSPORT, choices=decoder.TRANSPORTS, help="where the decoder runs (default: served)")
    executor.add_argument("--reproduce", action="store_true", help="check two runs write the same bytes")

    prober = sub.add_parser(
        "probe", help="Ask whether Opus performs a transformation, before building it"
    )
    prober.add_argument("method", nargs="?", help="candidate generator (default: ask)")
    prober.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")

    inducer = sub.add_parser("induce", help="Rebuild rule tables from the gold corpus")
    inducer.add_argument("--family", default="support-verb", choices=induce_cmd.FAMILIES,
                         help="which table to rebuild (default: support-verb)")
    inducer.add_argument("--minimum", type=int, default=4,
                         help="fewest observations for a construction to be tabled")


def _fitting_parsers(sub) -> None:
    """Subcommands that fit a decision from the corpus or judge one by hand."""
    tagger = sub.add_parser(
        "tag", help="Fit the keep-or-delete decision the linter uses"
    )
    tagger.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")

    damage = sub.add_parser(
        "damage", help="Build the hand-judging sheet and report the damage rate"
    )
    damage.add_argument("-n", "--limit", type=int, default=damage_cmd.SIZE, help="how many changed paragraphs to judge")

    encoder = sub.add_parser(
        "encoder", help="Compare a frozen encoder against the one-hot features"
    )
    encoder.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")

    allocator = sub.add_parser(
        "allocate", help="Compare ways of splitting a document's reduction across paragraphs"
    )
    allocator.add_argument("--split", default="test", choices=load.SPLITS, help="which documents to score on (default: test)")

    sentencer = sub.add_parser(
        "sentence", help="Ask whether the sentences Opus drops can be told from the ones it keeps"
    )
    sentencer.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Deterministic, fully local plain-language linter for academic prose.",
    )
    sub = parser.add_subparsers(dest="command")
    _measurement_parsers(sub)
    _fitting_parsers(sub)

    linter = sub.add_parser("lint", help="Lint a document and write the edited text")
    linter.add_argument("file", nargs="?",
                        help="a .md or .txt file, bare names resolve against input/")
    linter.add_argument("--band", default="firm", choices=bands.BANDS,
                        help="editing intensity (default: firm)")

    scorer = sub.add_parser("evaluate", help="Score the linter against Opus on the gold corpus")
    scorer.add_argument("-n", "--limit", type=int, help="stop after this many paragraphs")
    scorer.add_argument("--show", action="store_true", help="show edits Opus did not make")

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
        return experiment_cmd.run(family=args.family, limit=args.limit, split=args.split)
    if args.command == "rank":
        return rank_cmd.run(limit=args.limit, split=args.split)
    if args.command == "execute":
        return execute_cmd.run(mode="reproduce" if args.reproduce else "oracle",
                               backend=args.backend, family=args.family, limit=args.limit,
                               transport=args.transport)
    if args.command == "tag":
        return tag_cmd.run(limit=args.limit)
    if args.command == "damage":
        return damage_cmd.run(size=args.limit)
    if args.command == "encoder":
        return encoder_cmd.run(limit=args.limit)
    if args.command == "allocate":
        return allocate_cmd.run(split=args.split)
    if args.command == "sentence":
        return sentence_cmd.run(limit=args.limit)
    if args.command == "probe":
        return probe_cmd.run(name=args.method, limit=args.limit)
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
