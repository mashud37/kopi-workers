"""Turn a manuscript or outline into a styled slide deck and a PDF.
No arguments opens the menu; a subcommand runs directly."""

import argparse
import io
import sys

from cli import config, deck, install, menu, ui


def _build_parser():
    parser = argparse.ArgumentParser(prog="manage.py", description="Manuscript or outline to a styled .pptx and PDF.")
    parser.add_argument("--no-input", action="store_true", help="Never ask a question: each one takes its default answer")
    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("slides", help="Plan the slides with the model and build the deck")
    build.add_argument("file", help="Manuscript or outline (.docx, .txt, .md); a bare name resolves against input/")
    build.add_argument("-o", "--output", default=None, help="Output folder (default: output/)")
    build.add_argument("--venue", default=None, help="Venue line, overriding the manuscript and config")
    build.add_argument("--no-pdf", action="store_true", help="Build the deck only, no PDF")
    build.add_argument("--plan", default=None, metavar="FILE", help="Build from a saved plan, with no model call")
    build.add_argument("-n", "--dry-run", action="store_true", help="Print the plan as JSON and write no files")
    build.add_argument("--review", action="store_true", help="Review and revise the plan before building")
    build.add_argument("--emoji", action="store_true", help="Use colour emoji instead of the default icons")
    build.add_argument("--condense", action="store_true", help="Send only each paragraph's first and last sentence")

    sub.add_parser("config", help="Print the effective configuration")
    sub.add_parser("install", help="Create config.local.yaml and folders, check dependencies")
    return parser


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args()
    if args.no_input:
        sys.stdin = io.StringIO()

    if args.command is None:
        return menu.main()
    if args.command == "slides":
        options = {
            "output": args.output,
            "venue": args.venue,
            "no_pdf": args.no_pdf,
            "plan": args.plan,
            "dry_run": args.dry_run,
            "review": args.review,
            "emoji": args.emoji,
            "condense": args.condense,
        }
        return deck.run(args.file, options)
    if args.command == "config":
        return config.show()
    if args.command == "install":
        return install.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(0)
    except ValueError as error:
        ui.error(str(error))
        sys.exit(1)
    except SystemExit as error:
        if isinstance(error.code, str):
            ui.error(error.code)
            sys.exit(1)
        raise
