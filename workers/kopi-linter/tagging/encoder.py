"""Give every source word a contextual vector from a frozen sentence encoder,
so the keep-or-delete decision can be fitted on meaning rather than on lemmas.
"""
from functools import lru_cache

MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# One thread, because a summed float depends on the order the threads finish in
# and the whole point of a frozen encoder is that the same paragraph gives the
# same vector twice (`good.md` section 8).
THREADS = 1

# The encoder's own limit. A longer paragraph keeps its first pieces and the
# words past the cut get a zero vector, which the fit reads as no evidence.
MAX_PIECES = 512


@lru_cache(maxsize=1)
def _loaded() -> dict:
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(THREADS)
    model = AutoModel.from_pretrained(MODEL)
    model.eval()
    return {"tokenizer": AutoTokenizer.from_pretrained(MODEL), "model": model}


def available() -> bool:
    """Whether the encoder can be loaded at all on this machine."""
    try:
        _loaded()
        return True
    except Exception:
        return False


def width() -> int:
    """How many numbers one word's vector holds."""
    return int(_loaded()["model"].config.hidden_size)


def vectors_for(words: list) -> list:
    """One vector per word, averaged over the pieces the encoder split it into.

    Args:
        words: the paragraph's words, in order, as plain strings.

    Returns:
        A list of float lists, one per word and all the same length. A word the
        encoder never saw, because the paragraph ran past :data:`MAX_PIECES`,
        comes back as zeros.
    """
    import torch

    loaded = _loaded()
    encoded = loaded["tokenizer"](
        words,
        is_split_into_words=True,
        truncation=True,
        max_length=MAX_PIECES,
        return_tensors="pt",
    )
    with torch.no_grad():
        states = loaded["model"](**encoded).last_hidden_state[0]
    totals = torch.zeros(len(words), states.shape[1])
    counts = torch.zeros(len(words))
    for place, word in enumerate(encoded.word_ids(0)):
        if word is None:
            continue
        totals[word] += states[place]
        counts[word] += 1
    counts[counts == 0] = 1.0
    return (totals / counts.unsqueeze(1)).tolist()
