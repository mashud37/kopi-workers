"""Answer every page and form of the console: app pages, settings, keys, runs and their logs.
Each route checks its input and hands the work to jobs or files.
"""
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from registry import get_app
from web import documents, files, jobs, keys, mascot, options

bp = Blueprint("console", __name__)

SHOWN_AS_TEXT = [
    ".md",
    ".txt",
    ".diff",
    ".jsonl",
    ".csv",
]
SHOWN_AS_IS = [
    ".pdf",
    ".png",
    ".jpg",
]
WALLED_POLICY = "sandbox"


# ---- Helpers ----

def find_app(name):
    """The registered app with this name, or a 404 page."""
    app = get_app(name)
    if app is None:
        abort(404)
    return app


def log_position():
    """The `after` query value as a number, or a 400 page when it is not one."""
    after = request.args.get("after", "0")
    if not after.isdigit():
        abort(400)
    return int(after)


# ---- Pages ----

@bp.route("/favicon.svg")
def favicon():
    drawing = str(mascot.svg(2)).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return Response(drawing, mimetype="image/svg+xml")


@bp.route("/")
def home():
    return render_template("home.html")


@bp.route("/apps/<name>")
def app_page(name):
    app = find_app(name)
    latest = {}
    for command in app["commands"]:
        latest[command["name"]] = jobs.shown_job(name, command["name"])
    return render_template(
        "app.html",
        app=app,
        latest=latest,
        inputs=files.input_choices(app),
        cards={folder: files.card_rows(app, folder) for folder in files.FOLDERS},
        settings=options.card_view(name),
        key_sources=keys.sources_for(name),
    )


@bp.route("/apps/<name>/settings", methods=["POST"])
def app_settings(name):
    find_app(name)
    try:
        options.save_choices(name, request.form)
        flash("Saved. The next run uses these settings.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.app_page", name=name))


# ---- Files ----

@bp.route("/apps/<name>/upload", methods=["POST"])
def app_upload(name):
    app = find_app(name)
    try:
        saved = files.save_upload(app, request.files.get("file"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except OSError as error:
        return jsonify({"error": f"Could not save the file: {error}"}), 500
    return jsonify({"saved": saved})


@bp.route("/apps/<name>/files/<folder>/<path:relative>")
def app_file(name, folder, relative):
    app = find_app(name)
    path = files.resolve_file(app, folder, relative)
    if path is None:
        abort(404)
    if path.suffix.lower() in SHOWN_AS_TEXT:
        return send_file(path, mimetype="text/plain")
    if path.suffix.lower() in SHOWN_AS_IS:
        return send_file(path)
    response = send_file(path, as_attachment=True)
    response.headers["Content-Security-Policy"] = WALLED_POLICY
    return response


@bp.route("/view/<name>/<folder>/<path:relative>")
def view_page(name, folder, relative):
    app = find_app(name)
    path = files.resolve_file(app, folder, relative)
    if path is None:
        abort(404)
    parent = str(Path(relative).parent)
    return render_template(
        "view.html",
        app=app,
        folder=folder,
        folder_label=files.FOLDERS[folder],
        relative=relative,
        parent="" if parent == "." else parent,
        document=documents.document_view(path),
    )


@bp.route("/browse/<name>/<folder>")
def browse_page(name, folder):
    app = find_app(name)
    inside = request.args.get("in", "")
    if files.resolve_folder(app, folder, inside) is None:
        abort(404)
    wanted = request.args.get("q", "")
    page = request.args.get("page", "1")
    listing = documents.folder_listing(files.folder_path(app, folder), inside, wanted, int(page) if page.isdigit() else 1)
    return render_template(
        "files.html",
        app=app,
        folder=folder,
        folder_label=files.FOLDERS[folder],
        inside=inside,
        wanted=wanted,
        listing=listing,
        path=str(files.folder_path(app, folder) / inside),
    )


@bp.route("/apps/<name>/open/<folder>", methods=["POST"])
def app_open(name, folder):
    app = find_app(name)
    inside = request.form.get("in", "")
    try:
        files.open_folder(app, folder, inside)
    except (ValueError, OSError) as error:
        flash(str(error))
    if inside:
        return redirect(url_for("console.browse_page", name=name, folder=folder, **{"in": inside}))
    return redirect(url_for("console.app_page", name=name))


# ---- Keys ----

@bp.route("/keys")
def keys_page():
    return render_template("keys.html", store=keys.page_view())


@bp.route("/keys/add", methods=["POST"])
def keys_add():
    form = request.form
    try:
        keys.add_key(form.get("name", ""), form.get("variable", ""), form.get("value", ""), form.get("everywhere") == "on")
        flash("Key saved.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.keys_page"))


@bp.route("/keys/delete", methods=["POST"])
def keys_delete():
    keys.delete_key(request.form.get("name", ""))
    flash("Key deleted.")
    return redirect(url_for("console.keys_page"))


@bp.route("/keys/assign", methods=["POST"])
def keys_assign():
    choices = []
    for field_name, value in request.form.items():
        parts = field_name.split("|")
        if len(parts) != 3 or parts[0] != "assign":
            continue
        choices.append({"app": parts[1], "variable": parts[2], "key": value})
    try:
        keys.save_assignments(choices)
        flash("Saved.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("console.keys_page"))


# ---- Runs ----

@bp.route("/jobs")
def jobs_page():
    rows = jobs.list_jobs()
    running = [row for row in rows if row["status"] == "running"]
    return render_template("jobs.html", jobs=rows, refresh=bool(running))


@bp.route("/jobs/<job_id>")
def job_page(job_id):
    job = jobs.job_summary(job_id)
    if job is None:
        abort(404)
    return render_template("job.html", job=job)


@bp.route("/apps/<name>/run/<command_name>", methods=["POST"])
def app_run(name, command_name):
    find_app(name)
    try:
        job_id = jobs.start_job(name, command_name, request.form.to_dict())
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    log_url = url_for("console.job_log", job_id=job_id)
    panel = render_template("_run.html", run=jobs.job_summary(job_id), log_url=log_url)
    return jsonify({"panel": panel})


@bp.route("/jobs/<job_id>/log")
def job_log(job_id):
    log = jobs.job_log(job_id, log_position())
    if log is None:
        abort(404)
    log["input_url"] = url_for("console.job_input", job_id=job_id) if log["running"] else None
    log["cancel_url"] = url_for("console.job_cancel", job_id=job_id) if log["running"] else None
    log["running_jobs"] = jobs.running_count()
    return jsonify(log)


@bp.route("/jobs/<job_id>/input", methods=["POST"])
def job_input(job_id):
    try:
        jobs.send_input(job_id, request.form.get("text", ""))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def job_cancel(job_id):
    jobs.cancel_job(job_id)
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/dismiss", methods=["POST"])
def job_dismiss(job_id):
    jobs.dismiss(job_id)
    return jsonify({"ok": True})
