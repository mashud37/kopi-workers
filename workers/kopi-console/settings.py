"""Hold the console's settings in one dictionary, read once at import from the defaults and the environment.
The web modules and manage.py import SETTINGS.
"""
import os

# ---- Defaults ----
# KOPI_CONSOLE_<KEY> in the environment overrides each of these.

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 5191,
    "upload_limit_mb": 200,
    "poll_ms": 700,
    "files_shown": 30,
}

ALLOWED = {
    "host": [
        "127.0.0.1",
        "localhost",
    ],
}

NUMERIC = [
    "port",
    "upload_limit_mb",
    "poll_ms",
    "files_shown",
]

ENV_PREFIX = "KOPI_CONSOLE_"


# ---- Functions ----

def load():
    """Merge the defaults with the environment and check the result, so a bad value fails at start."""
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        from_environment = os.environ.get(ENV_PREFIX + key.upper())
        if from_environment:
            settings[key] = from_environment

    for key in NUMERIC:
        settings[key] = int(settings[key])

    for key, options in ALLOWED.items():
        if settings[key] not in options:
            raise SystemExit(f"Setting '{key}' must be one of {options}, not '{settings[key]}'.")
    return settings


# ---- Read the settings once, at import ----

SETTINGS = load()
