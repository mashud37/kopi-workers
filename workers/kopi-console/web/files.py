"""List, receive and hand out the files in each app's input and output folders.
The app pages show these lists, and dropped files land in the input folder.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from registry import app_folder
from settings import SETTINGS

FOLDERS = [
    "input",
    "output",
]
SHOWN_AS_TEXT = [
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".csv",
]
TIME_FORMAT = "%d %b %H:%M"
BYTES_PER_KILOBYTE = 1024


def folder_path(app, folder):
    """The full path of one of the app's two folders.

    Raises:
        ValueError: the folder is neither input nor output.
    """
    if folder not in FOLDERS:
        raise ValueError(f"No folder called {folder}.")
    return app_folder(app) / folder


def listing(app, folder, accepted=None):
    """The files directly in a folder, newest first, each with its name, time and size.

    Args:
        accepted: suffixes to keep, such as [".docx"]; None keeps every file.
    """
    path = folder_path(app, folder)
    if not path.is_dir():
        return []
    files = []
    for entry in path.iterdir():
        if not entry.is_file() or entry.name.startswith((".", "~$")):
            continue
        if accepted is not None and entry.suffix.lower() not in accepted:
            continue
        files.append(entry)
    files.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)

    rows = []
    for entry in files[:SETTINGS["files_shown"]]:
        stat = entry.stat()
        rows.append({
            "name": entry.name,
            "when": datetime.fromtimestamp(stat.st_mtime).strftime(TIME_FORMAT),
            "size": f"{max(1, stat.st_size // BYTES_PER_KILOBYTE):,} KB",
        })
    return rows


def find_file(app, folder, file_name):
    """The full path of a file directly in one of the app's folders, or None when there is none."""
    path = folder_path(app, folder) / file_name
    if path.name != file_name or not path.is_file():
        return None
    return path


def save_upload(app, upload):
    """Save one dropped file into the app's input folder, replacing a file of the same name.

    Raises:
        ValueError: the file has no usable name, or the app does not read its kind.
    """
    file_name = Path(upload.filename or "").name
    if not file_name or file_name.startswith("."):
        raise ValueError("That file has no usable name.")
    if Path(file_name).suffix.lower() not in app["accepts"]:
        raise ValueError(f"{app['name']} reads {', '.join(app['accepts'])} files, not {file_name}.")
    folder = folder_path(app, "input")
    folder.mkdir(exist_ok=True)
    upload.save(folder / file_name)
    return file_name


def open_folder(app, folder):
    """Open one of the app's folders in the system's file manager."""
    path = folder_path(app, folder)
    path.mkdir(exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
