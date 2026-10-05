#!/usr/bin/env python3
"""Open the local web console over the kopi apps, or run one app command headlessly.
No arguments opens the web page; the subcommands are its scriptable twin.
"""
import argparse
import sys
import time

from cli import install, ui
from registry import APPS, get_app, get_command

POLL_SECONDS = 0.2


def cmd_status():
    for app in APPS:
        print(f"{app['name']}  :  {app['blurb']}")
        for command in app["commands"]:
            print(f"  {command['name']:<10} {command['kind']:<6} {command['help']}")
        print()
    return 0


def cmd_run(app_name, command_name, values):
    """Run one command through the same job runner the web page uses, printing its log as it arrives."""
    from web import jobs

    sys.stdout.reconfigure(errors="replace")
    app = get_app(app_name)
    if app is None or get_command(app, command_name) is None:
        raise SystemExit(f"unknown command: {app_name} {command_name}, see: python manage.py status")
    try:
        job_id = jobs.start_job(app_name, command_name, values)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    position = 0
    while True:
        log = jobs.job_log(job_id, position)
        for line in log["lines"]:
            if not line.startswith(jobs.ITEM_PREFIX):
                print(line)
        position = log["next"]
        if log["status"] != "running" and not log["lines"]:
            return log["exit_code"] or 0
        time.sleep(POLL_SECONDS)


def parse_values(pairs):
    """Turn `name=value` words into the form values a command reads; a bare `--flag` switches it on."""
    values = {}
    for pair in pairs:
        name, _, value = pair.partition("=")
        values[name] = value if value else "on"
    return values


def main():
    parser = argparse.ArgumentParser(prog="manage.py", description="Local web console over the kopi apps.")
    sub = parser.add_subparsers(dest="command")

    web = sub.add_parser("web", help="Open the web console in the browser (the default)")
    web.add_argument("--port", type=int, default=None, metavar="N", help="Port (default: 5191)")
    web.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")

    run = sub.add_parser("run", help="Run one app command and print its log")
    run.add_argument("app", help="App, for example kopi-editor")
    run.add_argument("cmd", help="Command, for example analyze")
    run.add_argument("values", nargs=argparse.REMAINDER, help="Form values as name=value, for example file=chapter.docx --lang=british")

    sub.add_parser("status", help="List the apps and their commands")
    sub.add_parser("install", help="Check dependencies and find the apps")

    args = parser.parse_args()
    if args.command is None or args.command == "web":
        from web.app import run as run_web
        port = getattr(args, "port", None)
        run_web(port, open_browser=not getattr(args, "no_browser", False))
        return 0
    if args.command == "run":
        return cmd_run(args.app, args.cmd, parse_values(args.values))
    if args.command == "status":
        return cmd_status()
    if args.command == "install":
        return install.run()
    return 0


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
