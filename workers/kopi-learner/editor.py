"""The one bridge to kopi-editor: reuses its prompt builder, diagnosis,
quote guard, bands, and acceptance guard so training data matches
production exactly. Adds kopi-editor's root to sys.path.
"""
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path

_EDITOR_ROOT = (Path(__file__).resolve().parent.parent / "kopi-editor").resolve()


def _ensure_path() -> None:
    if not _EDITOR_ROOT.exists():
        raise SystemExit(
            f"kopi-editor not found at {_EDITOR_ROOT}: kopi-learner distils from it "
            "and expects it as a sibling in kopi-worker/."
        )
    p = str(_EDITOR_ROOT)
    if p not in sys.path:
        # Append, not insert: kopi-learner's own `cli` package must win the name; only
        # the editor's uniquely-named `kopi` package is resolved through this path.
        sys.path.append(p)


@lru_cache(maxsize=1)
def econfig():
    """kopi-editor's own config module, loaded by file path so its env.yaml is the
    single source of truth for the service URL/token, the Anthropic key, and the
    chosen models. No separate kopi-learner secrets: reuse what `deploy`/`settings`
    already wrote. Loaded standalone (it imports `cli` only lazily, inside show())."""
    _ensure_path()
    path = _EDITOR_ROOT / "cli" / "config.py"
    spec = importlib.util.spec_from_file_location("kopi_editor_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def output_dir() -> Path:
    """kopi-editor's output/: the existing edited bundles we mine for training."""
    return Path(econfig().OUTPUT_DIR)


def extract_docx(path) -> str:
    """Read a .docx into the editor's text form (paragraphs joined by blank lines,
    block quotes wrapped) so input documents ingest exactly like the editor's own."""
    _ensure_path()
    from kopi.extract import extract_docx as _x
    return _x(path)


@lru_cache(maxsize=1)
def _mods():
    _ensure_path()
    from kopi import diagnose, intensity, llm, pipeline, quote_guard, step_concision
    return {
        "llm": llm,
        "diagnose": diagnose,
        "intensity": intensity,
        "quote_guard": quote_guard,
        "step_concision": step_concision,
        "pipeline": pipeline,
    }


def build_messages(paragraph, instructions, lang, mode, floor):
    """The exact [system, user] chat messages production sends for this paragraph."""
    return _mods()["llm"].build_messages(paragraph, instructions, lang, mode, floor)


def prepare_doc(text: str, lang: str) -> dict:
    """Diagnose a document once (the expensive spaCy pass), returning editor state
    that `candidates_at` can re-query at any band without re-diagnosing."""
    return _mods()["pipeline"].prepare(text, target=0, lang=lang, reduction=0)


def candidates_at(state: dict, reduction: int) -> list[dict]:
    """Editable paragraphs at the intensity implied by `reduction`, reusing an
    already-diagnosed `state`. Each item carries the production `instructions`,
    `mode`, `floor`, and `max_compression`; `reduction` selects the band
    (0 = clarity), the per-document ratio does the rest. Does not modify the
    `state` the caller passed in, so the same state serves every band in turn.
    """
    state_at_band = {**state, "reduction": reduction}
    return _mods()["step_concision"].get_candidates(state_at_band)


def guard_verdict(original: str, edited: str, max_compression: float) -> dict:
    """Run the editor's acceptance guard (cosine meaning, citations, numbers,
    compression ceiling) on a candidate edit. Returns {accepted, reason, saved}."""
    return _mods()["step_concision"].guard_result(original, edited, max_compression)


def default_max_compression() -> float:
    return _mods()["step_concision"]._MAX_COMPRESSION


def cosine(a: str, b: str) -> float:
    """Meaning similarity between two texts (the editor's all-MiniLM cosine), reused
    here to score how close a candidate edit is to Opus's gold edit."""
    return _mods()["step_concision"]._cosine_sim(a, b)


def preload_embedding_model() -> None:
    """Load sentence-transformers once before any threads (the guard's cosine check
    is not safe under concurrent first-init)."""
    try:
        _mods()["step_concision"]._get_model()
    except Exception:
        pass
