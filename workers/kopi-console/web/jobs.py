"""Run app commands as background subprocesses, keep each live log, and pass typed answers in.
The app pages read these records to show each run as it happens.
"""
import codecs
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

from registry import app_folder, documents_folder, get_app, get_command
from web import keys, options

STATUS_LABEL = {
    "running": "Running",
    "ok": "Done",
    "failed": "Failed",
    "cancelled": "Stopped",
}

# KOPI_ITEM_EVENTS asks an app to announce each item it starts and finishes, which the run panel lists.
CHILD_ENVIRONMENT = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONIOENCODING": "utf-8",
    "KOPI_ITEM_EVENTS": "on",
}
ITEM_PREFIX = "kopi-item:"
STOP_WAIT_SECONDS = 5
SECONDS_PER_MINUTE = 60
CLOCK_FORMAT = "%H:%M"
READ_BYTES = 4096

JOBS = {}
PROCESSES = {}
LOCK = threading.Lock()


# ---- Starting a job ----

def form_flags(command, values):
    """Turn a submitted form into the arguments for one command; a chosen input file becomes its full path.

    Raises:
        ValueError: a required value is missing, or a value has the wrong shape.
    """
    positionals = []
    flags = []
    for field in command["fields"]:
        name = field["name"]
        raw = values.get(name, "").strip()
        if field["type"] == "bool":
            if raw:
                flags.append(name)
            continue
        if not raw:
            if not name.startswith("-") and not field.get("optional"):
                raise ValueError(f"{command['name']} needs a value for {name}.")
            continue
        if field["type"] == "int" and not raw.isdigit():
            raise ValueError(f"{name} must be a whole number.")
        if field["type"] == "choice" and raw not in field["choices"]:
            raise ValueError(f"{name} must be one of {', '.join(field['choices'])}.")
        if field["type"] == "input":
            raw = str(input_path(raw))
        if name.startswith("-"):
            flags.extend([name, raw])
        else:
            positionals.append(raw)
    return positionals + flags


def input_path(file_name):
    """The full path of a file in the shared documents folder.

    Raises:
        ValueError: the name reaches outside the folder, or no such file is there.
    """
    path = documents_folder() / file_name
    if path.name != file_name or not path.is_file():
        raise ValueError(f"There is no {file_name} in the documents folder.")
    return path


def build_argv(app, command, flags):
    """The command line for one run: this Python, the app's script, --no-input so no question waits, the command, then the flags."""
    return [sys.executable, app["script"], "--no-input", command["name"], *flags]


def start_job(app_name, command_name, values):
    """Start one app command in the background and return its job id.

    Raises:
        ValueError: the command is unknown, the form is invalid, or the process will not start.
    """
    app = get_app(app_name)
    command = get_command(app, command_name) if app else None
    if command is None:
        raise ValueError(f"Unknown command: {app_name} {command_name}.")

    argv = build_argv(app, command, form_flags(command, values))
    environment = dict(os.environ)
    environment.update(options.environment_for(app_name))
    environment.update(keys.environment_for(app_name))
    environment.update(CHILD_ENVIRONMENT)
    try:
        process = subprocess.Popen(argv, cwd=str(app_folder(app)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
    except OSError as error:
        raise ValueError(f"Could not start {app_name} {command_name}: {error}") from error

    with LOCK:
        job_id = str(len(JOBS) + 1)
        JOBS[job_id] = {
            "id": job_id,
            "app": app_name,
            "command": command_name,
            "shown": " ".join(argv[1:]),
            "status": "running",
            "started_at": datetime.now().strftime(CLOCK_FORMAT),
            "started": time.monotonic(),
            "ended": None,
            "exit_code": None,
            "lines": [],
            "partial": "",
            "dismissed": False,
        }
        PROCESSES[job_id] = process
    threading.Thread(target=watch_job, args=(job_id,), daemon=True).start()
    return job_id


def add_output(job_id, text):
    """Add printed text to a job's log; a line still waiting for its newline stays unfinished.

    A carriage return starts its line over, as it does in a terminal.
    """
    with LOCK:
        job = JOBS[job_id]
        pieces = (job["partial"] + text).split("\n")
        job["partial"] = pieces.pop()
        for piece in pieces:
            job["lines"].append(piece.rstrip("\r").split("\r")[-1])


def watch_job(job_id):
    """Copy everything a job prints into its log while it runs, then record how it ended.

    Output is read in pieces rather than whole lines, so a question waiting for an answer shows at once.
    """
    process = PROCESSES[job_id]
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    chunk = process.stdout.read1(READ_BYTES)
    while chunk:
        add_output(job_id, decoder.decode(chunk))
        chunk = process.stdout.read1(READ_BYTES)
    exit_code = process.wait()
    try:
        process.stdin.close()
    except OSError:
        pass

    with LOCK:
        job = JOBS[job_id]
        if job["partial"]:
            job["lines"].append(job["partial"])
            job["partial"] = ""
        job["exit_code"] = exit_code
        job["ended"] = time.monotonic()
        if job["status"] == "running" and exit_code == 0:
            job["status"] = "ok"
        elif job["status"] == "running":
            job["status"] = "failed"


def send_input(job_id, text):
    """Type one line into a running job, as if answering its question in a terminal.

    Raises:
        ValueError: the job is not running, or it no longer reads what is typed.
    """
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or job["status"] != "running":
            raise ValueError("That job is no longer running.")
        job["lines"].append(job["partial"].split("\r")[-1] + text)
        job["partial"] = ""
    process = PROCESSES[job_id]
    try:
        process.stdin.write(text.encode("utf-8") + b"\n")
        process.stdin.flush()
    except (OSError, ValueError) as error:
        raise ValueError("That job no longer reads answers.") from error


# ---- Stopping jobs ----

def cancel_job(job_id):
    """Stop a running job and every process it started."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return
        job["status"] = "cancelled"
    process = PROCESSES[job_id]
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    try:
        process.wait(timeout=STOP_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()


def stop_all():
    """Cancel every job still running, so quitting the console leaves no child behind."""
    with LOCK:
        running = [job_id for job_id, job in JOBS.items() if job["status"] == "running"]
    for job_id in running:
        cancel_job(job_id)


def dismiss(job_id):
    """Close a finished job, so its app page stops showing it."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is not None and job["status"] != "running":
            job["dismissed"] = True


# ---- Reading jobs ----

def elapsed_text(job):
    """How long a job has run, or ran: seconds under a minute, otherwise minutes and seconds."""
    end = job["ended"] or time.monotonic()
    seconds = int(end - job["started"])
    if seconds < SECONDS_PER_MINUTE:
        return f"{seconds}s"
    return f"{seconds // SECONDS_PER_MINUTE}m {seconds % SECONDS_PER_MINUTE:02d}s"


def summary_row(job):
    """The fields a run panel or the jobs list shows for one job, with the last line's status symbols removed."""
    last_line = ""
    for line in reversed(job["lines"]):
        if line.startswith(ITEM_PREFIX):
            continue
        text = line.strip().lstrip("▶✓⚠·✗─ ")
        if text:
            last_line = text
            break
    return {
        "id": job["id"],
        "app": job["app"],
        "command": job["command"],
        "shown": job["shown"],
        "status": job["status"],
        "label": STATUS_LABEL[job["status"]],
        "started_at": job["started_at"],
        "elapsed": elapsed_text(job),
        "exit_code": job["exit_code"],
        "last_line": last_line,
    }


def job_summary(job_id):
    """One job's summary, or None when there is no such job."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return summary_row(job)


def job_log(job_id, after):
    """The log lines after a position, the unfinished line, and the job's state, for a live log."""
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        lines = job["lines"][after:]
        return {
            "lines": lines,
            "next": after + len(lines),
            "partial": job["partial"].split("\r")[-1],
            "running": job["status"] == "running",
            "status": job["status"],
            "label": STATUS_LABEL[job["status"]],
            "exit_code": job["exit_code"],
            "elapsed": elapsed_text(job),
        }


def shown_job(app_name, command_name):
    """The newest job for one command that its page still shows: not stopped and not closed, or None."""
    with LOCK:
        newest = None
        for job in JOBS.values():
            if job["app"] == app_name and job["command"] == command_name:
                newest = job
        if newest is None or newest["status"] == "cancelled" or newest["dismissed"]:
            return None
        return summary_row(newest)


def list_jobs():
    """Every job, newest first."""
    with LOCK:
        rows = [summary_row(job) for job in JOBS.values()]
    rows.reverse()
    return rows


def running_count():
    """How many jobs are working right now."""
    with LOCK:
        working = [job for job in JOBS.values() if job["status"] == "running"]
    return len(working)
