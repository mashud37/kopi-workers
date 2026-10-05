"""Answer every page and form of the console: app pages, dropped files, runs and their logs.
Each route checks its input and hands the work to jobs or files.
"""
from flask import (
    Blueprint,
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
from web import files, jobs

bp = Blueprint("console", __name__)


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
        inputs=files.listing(app, "input", app["accepts"]),
        outputs=files.listing(app, "output"),
    )


# ---- Files ----

@bp.route("/apps/<name>/upload", methods=["POST"])
def app_upload(name):
    app = find_app(name)
    try:
        saved = files.save_upload(app, request.files.get("file"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"saved": saved})


@bp.route("/apps/<name>/files/<folder>/<file_name>")
def app_file(name, folder, file_name):
    app = find_app(name)
    try:
        path = files.find_file(app, folder, file_name)
    except ValueError:
        abort(404)
    if path is None:
        abort(404)
    if path.suffix.lower() in files.SHOWN_AS_TEXT:
        return send_file(path, mimetype="text/plain")
    return send_file(path, as_attachment=True)


@bp.route("/apps/<name>/open/<folder>", methods=["POST"])
def app_open(name, folder):
    app = find_app(name)
    try:
        files.open_folder(app, folder)
    except (ValueError, OSError) as error:
        flash(str(error))
    return redirect(url_for("console.app_page", name=name))


# ---- Runs ----

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
