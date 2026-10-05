"""`StepSpinner` fronts a blocking step so the terminal is never dead;
`BatchProgress` reports a countable batch. Both are no-ops off a TTY and
ASCII-safe on older Windows consoles.
"""
import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CHECK = "✓"
_LABEL_W = 24
_BAR_W = 20


class StepSpinner:
    """Animated spinner for a single step. No-op when stdout is not a TTY."""

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
        safe = summary.encode("ascii", "replace").decode("ascii")
        suffix = f"  {safe}" if safe else ""
        if sys.stdout.isatty():
            try:
                sys.stdout.write(f"\r  {_CHECK}  {self._label:<{_LABEL_W}}{suffix}\n")
            except UnicodeEncodeError:
                sys.stdout.write(f"\r  *  {self._label:<{_LABEL_W}}{suffix}\n")
            sys.stdout.flush()
        else:
            print(f"  {self._label}... {safe}")


class BatchProgress:
    """Live one-line bar with an ETA for a countable batch."""

    def __init__(self, total: int, label: str = "processing"):
        self._total = total
        self._label = label
        self._done = 0
        self._started = time.perf_counter()
        self._tty = sys.stdout.isatty()
        self._lock = threading.Lock()
        if self._tty and total:
            self._render()

    def advance(self, step: int = 1) -> None:
        with self._lock:
            self._done += step
            if self._tty:
                self._render()

    def on_item(self, index: int, total: int, item) -> None:
        """Take the `on_progress(index, total, item)` call the analysis layers make.

        The bar counts its own way through the batch, so the three arguments are
        read and dropped; the method exists to be passed by name where a caller
        would otherwise write a lambda that throws them away.
        """
        self.advance()

    def _render(self) -> None:
        span = self._total or 1
        filled = int(_BAR_W * self._done / span)
        bar = "#" * filled + "." * (_BAR_W - filled)
        elapsed = time.perf_counter() - self._started
        eta = (elapsed / self._done) * (self._total - self._done) if self._done else 0.0
        line = (
            f"\r  {self._label}  [{bar}]  {self._done}/{self._total}"
            f"  |  {eta:.0f}s left   "
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
