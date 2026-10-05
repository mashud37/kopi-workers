"""Find, receive and open the files in each app's input and output folders, never reaching outside them.
The app pages, the folder browser and the viewer use these.
"""
import os
import subprocess
from pathlib import Path

from registry import app_folder
from settings import SETTINGS
from web import documents

FOLDERS = {
    "input": "Input",
    "output": "Output",
}


def folder_path(app, folder):
    """The full path of one of the app's two folders.

    Raises:
        ValueError: the folder is neither input nor output.
    """
    if folder not in FOLDERS:
        raise ValueError(f"No folder called {folder}.")
    return app_folder(app) / folder


def inside_folder(app, folder, relative):
    """The full path of something inside one of the app's folders, or None when the path leads outside it."""
    try:
        base = folder_path(app, folder).resolve()
    except ValueError:
        return None
    path = (base / relative).resolve()
    if path != base and base not in path.parents:
        return None
    return path


def resolve_file(app, folder, relative):
    """The full path of a file inside one of the app's folders, or None when there is no such file."""
    path = inside_folder(app, folder, relative)
    if path is None or not path.is_file():
        return None
    return path


def resolve_folder(app, folder, relative):
    """The full path of a sub-folder inside one of the app's folders, or None when there is none."""
    path = inside_folder(app, folder, relative)
    if path is None or not path.is_dir():
        return None
    return path


def card_rows(app, folder):
    """The newest files and sub-folders directly in a folder, for the card on the app page."""
    listing = documents.folder_listing(folder_path(app, folder), "", "", 1)
    return {
        "rows": listing["rows"][:SETTINGS["files_shown"]],
        "total": listing["total"],
    }


def input_choices(app):
    """The files in the app's input folder that it can read, newest first, for the run forms."""
    folder = folder_path(app, "input")
    if not folder.is_dir():
        return []
    found = []
    for entry in folder.iterdir():
        if entry.is_file() and not entry.name.startswith((".", "~$")) and entry.suffix.lower() in app["accepts"]:
            found.append(entry)
    found.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    return [entry.name for entry in found]


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


def open_folder(app, folder, relative):
    """Open one of the app's folders, or a sub-folder of it, in the system's file manager.

    Raises:
        ValueError: the path is not a folder inside the app's folders.
    """
    folder_path(app, folder).mkdir(exist_ok=True)
    path = resolve_folder(app, folder, relative)
    if path is None:
        raise ValueError("That folder is not there.")
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
