"""Announce each paragraph a batch starts and finishes, as lines the web console turns into its progress list.
Silent in a terminal; the console switches it on through KOPI_ITEM_EVENTS."""
import os
import threading

ON = os.environ.get("KOPI_ITEM_EVENTS") == "on"
PREFIX = "kopi-item:"
LOCK = threading.Lock()


def announce(state, name="", detail=""):
    """One event: "total" with the count as name, then "start", "ok" or "failed" per item."""
    if not ON:
        return
    with LOCK:
        print(f"{PREFIX} {state} | {name} | {detail}", flush=True)
