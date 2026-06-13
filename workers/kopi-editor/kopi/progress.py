import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CHECK = "✓"
_LABEL_W = 22
_BAR_W = 20


def _first_summary(new_log_entries: list) -> str:
    for entry in new_log_entries:
        if entry.get("para") is None:
            detail = entry.get("detail", "")
            if detail:
                return detail[:68]
    return ""


class StepSpinner:
    """Animated spinner for a single pipeline step. No-op when stdout is not a TTY."""

    def __init__(self, label: str):
        self._label = label
        self._stop = threading.Event()
        self._thread = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = _FRAMES[i % len(_FRAMES)]
            try:
                sys.stdout.write(f"\r  {frame}  {self._label:<{_LABEL_W}}")
                sys.stdout.flush()
            except Exception:
                pass
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        if sys.stdout.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def done(self, summary: str = "") -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        safe_summary = summary.encode("ascii", "replace").decode("ascii")
        suffix = f"  {safe_summary}" if safe_summary else ""
        if sys.stdout.isatty():
            try:
                sys.stdout.write(f"\r  {_CHECK}  {self._label:<{_LABEL_W}}{suffix}\n")
            except UnicodeEncodeError:
                sys.stdout.write(f"\r  *  {self._label:<{_LABEL_W}}{suffix}\n")
            sys.stdout.flush()
        else:
            print(f"  {self._label}... {safe_summary}")


class LLMProgress:
    """Live one-line progress bar for the LLM tightening phase.

    Thread-safe (``advance`` is called from worker threads as each paragraph
    finishes) and ASCII-only so it renders on legacy Windows consoles. A no-op
    when stdout is not a TTY, so captured/redirected output stays clean.
    """

    def __init__(self, total: int):
        self._total = total
        self._done = 0
        self._cut = 0
        self._tty = sys.stdout.isatty()
        self._lock = threading.Lock()
        if self._tty and total:
            self._render()

    def advance(self, words_cut: int = 0, accepted: bool = False) -> None:
        with self._lock:
            self._done += 1
            if accepted:
                self._cut += max(0, words_cut)
            if self._tty:
                self._render()

    def _render(self) -> None:
        span = self._total or 1
        filled = int(_BAR_W * self._done / span)
        bar = "#" * filled + "." * (_BAR_W - filled)
        remaining = self._total - self._done
        line = (
            f"\r  LLM tightening  [{bar}]  {self._done}/{self._total} para"
            f"  |  {self._cut} words cut  |  {remaining} left   "
        )
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass

    def finish(self) -> None:
        if self._tty:
            try:
                sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception:
                pass
