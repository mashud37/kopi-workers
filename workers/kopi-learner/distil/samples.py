"""Define `Sample`, one model's edit of one paragraph: `role` marks it
opus (gold) or qwen (rejected), `key` groups the same paragraph across
models for DPO pairing.
"""
import editor


def role_of(model: str) -> str:
    m = (model or "").lower()
    if "opus" in m:
        return "opus"
    if "qwen" in m:
        return "qwen"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return "other"


def make(origin: dict, paragraph: dict, edit: str) -> dict:
    """Build a sample and attach the editor's guard verdict at `max_compression`.

    Args:
        origin: where the sample came from: `source`, `doc`, `idx`, `model`, `lang`.
        paragraph: what was asked of the editor: `original`, `instructions`,
            `mode`, `floor` and `max_compression`.
        edit: the edited text the model returned.

    Returns:
        One flat sample row, both mappings merged, plus the guard's `accepted`
        and `reason` and the edit's word count.
    """
    original = paragraph["original"]
    ceiling = paragraph["max_compression"]
    verdict = editor.guard_verdict(original, edit, ceiling)
    return {
        "key": f"{origin['doc']}#{origin['idx']}",
        "source": origin["source"],
        "doc": origin["doc"],
        "idx": origin["idx"],
        "model": origin["model"],
        "role": role_of(origin["model"]),
        "lang": origin["lang"],
        "original": original,
        "instructions": list(paragraph.get("instructions") or []),
        "mode": paragraph["mode"],
        "floor": paragraph.get("floor"),
        "max_compression": ceiling,
        "edit": edit,
        "accepted": verdict["accepted"],
        "reason": verdict.get("reason"),
        "words": len(edit.split()),
    }
