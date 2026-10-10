#!/usr/bin/env python3
"""kopi-editor is an academic copyeditor for the humanities and social
sciences. No arguments launches the interactive menu; any subcommand runs
directly.
"""
import os

# Allow torch's and spaCy/blis's OpenMP runtimes to coexist (Windows loads two
# libiomp copies, which otherwise aborts or hangs). Must be set before imports.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import io
import sys

from cli import analyze, config, deploy, edit, install, menu, proof, settings, ui, update


def _build_parser():  # lint-style: ignore FN004
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="Academic copyeditor: plain-language editing for academic prose.",
    )
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    a = sub.add_parser("analyze", help="Diagnose a .docx: report cuts + per-paragraph needs (no edits)")
    a.add_argument("file", help="Input .docx (a bare name resolves against input/)")

    p = sub.add_parser("proof", help="Conservative deterministic edit (no LLM) -> output/")
    p.add_argument("file", help="Input .docx (a bare name resolves against input/)")
    p.add_argument("--lang", choices=list(config.LANGS), default=None, help="Output variety (default from env.yaml)")

    e = sub.add_parser("edit", help="Full plain-language edit via the LLM backend -> output/")
    e.add_argument("file", help="Input .docx (a bare name resolves against input/)")
    e.add_argument("reduction", type=int, nargs="?", default=None, help="Optional words-to-remove guide")
    e.add_argument("--lang", choices=list(config.LANGS), default=None, help="Output variety (default from env.yaml)")
    e.add_argument("--backend", choices=list(config.BACKENDS), default=None, help="Model backend (default from env.yaml)")

    ct = sub.add_parser("cloud-test", help="Send paragraphs straight to the configured model (dev smoke)")
    ct.add_argument("n", nargs="?", default="3", help="Paragraphs to send (integer or 'all')")
    ct.add_argument("--source", default=None, help="Text file (default: newest output/*_edited.md)")

    d = sub.add_parser("deploy", help="Fire the vLLM/Qwen3 image build async (frees the terminal)")
    d.add_argument("--ollama", action="store_true", help="Deploy the legacy L4 Ollama service (synchronous)")

    ds = sub.add_parser("deploy-status", help="Check the pending build; finish + deploy when it's ready")
    ds.add_argument("--wait", action="store_true", help="Block until the build finishes, then deploy")
    sub.add_parser("settings", help="Edit the model backend, model and language in env.yaml")
    sub.add_parser("config", help="Print the effective configuration")
    sub.add_parser("install", help="Create env.yaml + folders and check dependencies (idempotent)")
    sub.add_parser("update", help="Upgrade dependencies and the spaCy model")
    return parser


def main():
    args = _build_parser().parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()
    if args.command is None:
        return menu.main()
    if args.command == "analyze":
        return analyze.run(args.file)
    if args.command == "proof":
        return proof.run(args.file, args.lang)
    if args.command == "edit":
        return edit.run(args.file, args.reduction, args.lang, args.backend)
    if args.command == "cloud-test":
        source = args.source or config.newest_output()
        if not source:
            raise SystemExit("no source file; pass --source or run `edit` first.")
        from backends import llm as model_calls
        return model_calls.smoke(config.get("BACKEND"), source, args.n)
    if args.command == "deploy":
        return deploy.run(args.ollama)
    if args.command == "deploy-status":
        return deploy.status(args.wait)
    if args.command == "settings":
        return settings.run()
    if args.command == "config":
        return config.show()
    if args.command == "install":
        return install.run()
    if args.command == "update":
        return update.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except SystemExit as e:
        if isinstance(e.code, str):  # our own SystemExit("message")
            ui.error(e.code)
            sys.exit(1)
        raise
