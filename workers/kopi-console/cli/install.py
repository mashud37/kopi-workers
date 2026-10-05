"""Check that Flask is installed and that each kopi app sits beside the console.
The console needs both before `python manage.py` can open the web page.
"""
from registry import APPS, app_folder

from . import ui


def run():
    ui.step("Checking kopi-console")
    try:
        import flask  # noqa: F401
        ui.ok("flask is installed")
    except ImportError:
        ui.error("flask is missing, run: pip install -r requirements.txt")
        return 1
    for app in APPS:
        script = app_folder(app) / app["script"]
        if script.exists():
            ui.ok(f"{app['name']} found")
        else:
            ui.warn(f"{app['name']} not found at {script.parent}")
    return 0
