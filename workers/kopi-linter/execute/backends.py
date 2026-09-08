"""Registry of span executors, from free to expensive: each turns one marked
span and its context into a replacement, or refuses. The oracle probe scores
them side by side.
"""
from execute import decoder, tagger, template


def _no_state(context: dict) -> dict:  # lint-style: ignore FN004
    return {}


def _keep(task: dict, state: dict) -> str:  # lint-style: ignore FN004
    return task["source"]


def _delete(task: dict, state: dict) -> str:  # lint-style: ignore FN004
    return ""


BACKENDS = {
    "keep": {
        "prepare": _no_state,
        "execute": _keep,
        "anchor": True,
        "reads_gold": False,
        "free": True,
        "what": "leave the span alone, which is the zero of the scale",
    },
    "delete": {
        "prepare": _no_state,
        "execute": _delete,
        "anchor": True,
        "reads_gold": False,
        "free": True,
        "what": "drop the span, the only move the linter can already make",
    },
    "template": {
        "prepare": template.prepare,
        "execute": template.execute,
        "anchor": False,
        "reads_gold": False,
        "free": True,
        "what": "plain code: drop the span, or respell it",
    },
    "tagger-ceiling": {
        "prepare": tagger.prepare,
        "execute": tagger.execute,
        "anchor": False,
        "reads_gold": True,
        "free": True,
        "what": "the best an edit tagger could do with every tag choice correct",
    },
    "decoder": {
        "prepare": decoder.prepare,
        "execute": decoder.execute,
        "anchor": False,
        "reads_gold": False,
        "free": False,
        "what": f"a small model on local Ollama ({decoder.MODEL}), decoded greedily",
    },
}

NAMES = tuple(BACKENDS)
FREE = tuple(name for name in BACKENDS if BACKENDS[name]["free"])
