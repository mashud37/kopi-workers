"""Check that the console's packages are installed and that each kopi app sits beside it.
The console needs both before `python manage.py` can open the web page.
"""
from registry import APPS, app_folder

from . import ui

MODULES = [
    "flask",
    "markdown",
    "docx",
]


def run():
    ui.step("Checking kopi-console")
    missing = []
    for module in MODULES:
        try:
            __import__(module)
            ui.ok(f"{module} is installed")
        except ImportError:
            missing.append(module)
    if missing:
        ui.error(f"{', '.join(missing)} missing, run: pip install -r requirements.txt")
        return 1
    for app in APPS:
        script = app_folder(app) / app["script"]
        if script.exists():
            ui.ok(f"{app['name']} found")
        else:
            ui.warn(f"{app['name']} not found at {script.parent}")
    return 0
