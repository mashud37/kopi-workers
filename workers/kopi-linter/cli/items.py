"""Announce a batch's size and progress as lines the web console turns into its progress bar.
Silent unless the console sets KOPI_ITEM_EVENTS."""
import os
import threading

ON = os.environ.get("KOPI_ITEM_EVENTS") == "on"
PREFIX = "kopi-item:"
LOCK = threading.Lock()


def announce(state, name="", detail=""):
    """One event: "total" with the batch size as name, then "done" with the count finished so far."""
    if not ON:
        return
    with LOCK:
        print(f"{PREFIX} {state} | {name} | {detail}", flush=True)
