"""Align an original paragraph with its edited form, at two levels.

Level 1, sentences. A copy-edit is monotone: an editor tightens, splits, merges
and drops sentences but almost never reorders them. That makes the classic
parallel-corpus alignment of Gale and Church (1993) directly applicable, with
the beads relabelled for editing rather than translation: 1-1 rewrite, 1-n
split, n-1 merge, 1-0 deletion, 0-1 insertion. A Needleman-Wunsch style DP over
the monotone grid finds the cheapest bead sequence, so the *shape* of an edit
(did a sentence go, or was it absorbed?) is recovered, not guessed.

Level 2, spans. Inside a 1-1 or n-m bead, ``difflib.SequenceMatcher`` over
lowercased tokens yields the minimal edit script. Each non-equal opcode becomes
a :class:`SpanEdit`: what was there, what replaced it, and where it sat. Those
spans are the raw material the taxonomy classifies.

Similarity is IDF-weighted content-lemma containment, the same measure
kopi-editor's redundancy scan uses, so alignment needs a parser but no
embedding model and stays deterministic.
"""
import difflib
import math
from dataclasses import dataclass, field

_CONTENT_POS = frozenset(["NOUN", "PROPN", "VERB", "ADJ", "ADV", "NUM"])

_DELETE_COST = 1.0
_INSERT_COST = 1.4
_SPLIT_PENALTY = 0.15
_MERGE_PENALTY = 0.15
_MAX_FANOUT = 3
# Bead shapes the aligner will consider: 1-1 rewrites, 1-n splits, n-1 merges.
# n-m beads are excluded because a copy-edit that fuses and divides in one step is
# not recoverable as a single transformation anyway.
_FANOUTS = tuple(
    (di, dj)
    for di in range(1, _MAX_FANOUT + 1)
    for dj in range(1, _MAX_FANOUT + 1)
    if di == 1 or dj == 1
)


@dataclass
class SpanEdit:
    """One contiguous difference inside an aligned sentence bead."""
    op: str
    source: str
    target: str
    source_tokens: list = field(default_factory=list)
    target_tokens: list = field(default_factory=list)
    left_context: str = ""
    right_context: str = ""

    @property
    def delta(self) -> int:
        return len(self.source.split()) - len(self.target.split())


@dataclass
class Bead:
    """An aligned group of source sentences and target sentences."""
    op: str
    source: list
    target: list
    similarity: float = 0.0
    spans: list = field(default_factory=list)

    @property
    def source_text(self) -> str:
        return " ".join(s.text.strip() for s in self.source)

    @property
    def target_text(self) -> str:
        return " ".join(s.text.strip() for s in self.target)


def _content(span) -> set:
    return {t.lemma_.lower() for t in span if t.pos_ in _CONTENT_POS and not t.is_stop}


def _build_idf(lemma_sets: list[set]) -> dict:
    n = len(lemma_sets) or 1
    df: dict = {}
    for lemmas in lemma_sets:
        for lemma in lemmas:
            df[lemma] = df.get(lemma, 0) + 1
    return {lemma: math.log((n + 1) / (count + 1)) + 1.0 for lemma, count in df.items()}


def _mass(lemmas, idf: dict) -> float:
    """Total IDF weight of a lemma set, summed in sorted order.

    The sort is not cosmetic. Python randomises string hashing per process, so
    summing over set iteration order gives float results that differ in the last
    bits between runs, which flips ties in the alignment DP and makes the report
    move by a fraction of a percent from one run to the next. A linter that
    claims determinism cannot afford that.
    """
    return sum(idf.get(lemma, 1.0) for lemma in sorted(lemmas))


def _similarity(a: set, b: set, idf: dict) -> float:
    shared = a & b
    if not shared:
        return 0.0
    denom = min(_mass(a, idf), _mass(b, idf))
    return _mass(shared, idf) / denom if denom > 0 else 0.0


def _bead_op(di: int, dj: int) -> str:
    if di == 1 and dj == 1:
        return "rewrite"
    return "split" if dj > 1 else "merge"


def _moves(cell: tuple, shape: tuple, cost_of) -> list:
    """Every bead that may start at grid point ``cell``, as (di, dj, cost, op).

    Args:
        cell: ``(i, j, base_cost)``, the grid point and the cost of reaching it.
        shape: ``(n, m)``, the two sentence-list lengths.
        cost_of: ``(i, j, di, dj) -> float`` bead cost.
    """
    i, j, base = cell
    n, m = shape
    out = []
    if i < n:
        out.append((1, 0, base + _DELETE_COST, "delete"))
    if j < m:
        out.append((0, 1, base + _INSERT_COST, "insert"))
    out.extend(
        (di, dj, base + cost_of(i, j, di, dj), _bead_op(di, dj))
        for di, dj in _FANOUTS
        if i + di <= n and j + dj <= m
    )
    return out


def _relax(best, back, cell, move) -> None:
    i, j = cell
    di, dj, cost, op = move
    if cost < best[i + di][j + dj]:
        best[i + di][j + dj] = cost
        back[i + di][j + dj] = (i, j, op, di, dj)


def _fill(n: int, m: int, cost_of) -> list:
    """Backpointer grid for the cheapest monotone alignment."""
    best = [[math.inf] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if best[i][j] == math.inf:
                continue
            for move in _moves((i, j, best[i][j]), (n, m), cost_of):
                _relax(best, back, (i, j), move)
    return back


def _align_sentences(src_sents, tgt_sents, idf) -> list[Bead]:
    """Cheapest monotone bead sequence over the two sentence lists.

    Costs are ``1 - similarity`` for a match, plus a small penalty for the
    many-to-one and one-to-many beads so a genuine split is preferred over two
    unrelated matches but a spurious one is not invented.
    """
    src_content = [_content(s) for s in src_sents]
    tgt_content = [_content(t) for t in tgt_sents]
    n, m = len(src_sents), len(tgt_sents)

    def cost_of(i, j, di, dj):
        similarity = _similarity(
            set().union(*src_content[i:i + di]), set().union(*tgt_content[j:j + dj]), idf
        )
        return (1.0 - similarity) + _SPLIT_PENALTY * (dj - 1) + _MERGE_PENALTY * (di - 1)

    back = _fill(n, m, cost_of)
    beads = []
    i, j = n, m
    while (i, j) != (0, 0) and back[i][j] is not None:
        pi, pj, op, di, dj = back[i][j]
        src, tgt = list(src_sents[pi:pi + di]), list(tgt_sents[pj:pj + dj])
        similarity = _similarity(
            set().union(*[_content(s) for s in src]) if src else set(),
            set().union(*[_content(t) for t in tgt]) if tgt else set(),
            idf,
        )
        beads.append(Bead(op=op, source=src, target=tgt, similarity=similarity))
        i, j = pi, pj
    beads.reverse()
    return [_mark_untouched(bead) for bead in beads]


def _mark_untouched(bead: Bead) -> Bead:
    if bead.op == "rewrite" and bead.similarity >= 0.999:
        source = bead.source_text.strip()
        if source and source == bead.target_text.strip():
            bead.op = "keep"
    return bead


_CONTEXT_TOKENS = 4


def _span_edits(source_tokens, target_tokens) -> list[SpanEdit]:
    src_words = [t.text for t in source_tokens]
    tgt_words = [t.text for t in target_tokens]
    matcher = difflib.SequenceMatcher(
        a=[w.lower() for w in src_words], b=[w.lower() for w in tgt_words], autojunk=False
    )
    edits = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        edits.append(SpanEdit(
            op={"replace": "replace", "delete": "delete", "insert": "insert"}[op],
            source=" ".join(src_words[i1:i2]),
            target=" ".join(tgt_words[j1:j2]),
            source_tokens=list(source_tokens[i1:i2]),
            target_tokens=list(target_tokens[j1:j2]),
            left_context=" ".join(src_words[max(0, i1 - _CONTEXT_TOKENS):i1]),
            right_context=" ".join(src_words[i2:i2 + _CONTEXT_TOKENS]),
        ))
    return edits


_ABSORPTION_FLOOR = 0.25


def _split_out_deletions(beads: list[Bead]) -> list[Bead]:
    """Separate genuine deletions from the merge beads that swallowed them.

    A monotone aligner has no way to tell "these two sentences became one" from
    "one sentence was dropped and its neighbour kept", because both are n-to-1
    beads. Left alone that silently reports every drop as a merge. A source
    sentence whose content lemmas almost entirely fail to survive into the
    target was not absorbed, it was cut, so it is promoted to its own delete
    bead.
    """
    out = []
    for bead in beads:
        out.extend(_unpack_merge(bead) if bead.op == "merge" and len(bead.source) > 1 else [bead])
    return out


def _unpack_merge(bead: Bead) -> list[Bead]:
    target = set().union(*[_content(t) for t in bead.target]) if bead.target else set()
    kept, dropped = [], []
    for sentence in bead.source:
        source = _content(sentence)
        survival = len(source & target) / len(source) if source else 1.0
        (dropped if survival < _ABSORPTION_FLOOR else kept).append(sentence)
    if not dropped or not kept:
        return [bead]
    out = []
    for sentence in bead.source:
        if sentence in dropped:
            out.append(Bead(op="delete", source=[sentence], target=[]))
        elif sentence is kept[0]:
            out.append(Bead(op="merge" if len(kept) > 1 else "rewrite", source=kept,
                            target=bead.target, similarity=bead.similarity))
    return out


def align(original: str, edited: str, nlp) -> list[Bead]:
    """Bead-align a paragraph pair and fill each bead's span-level edit script.

    Args:
        original: the paragraph as the author wrote it.
        edited: the same paragraph after an editor (model or human) worked on it.
        nlp: a loaded spaCy pipeline with a sentencizer or parser.

    Returns:
        Beads in document order. ``keep`` beads carry no spans; every other bead
        carries the minimal token-level edit script between its two sides.
    """
    src_doc, tgt_doc = nlp(original), nlp(edited)
    src_sents = [s for s in src_doc.sents if s.text.strip()]
    tgt_sents = [s for s in tgt_doc.sents if s.text.strip()]
    if not src_sents or not tgt_sents:
        return []
    idf = _build_idf([_content(s) for s in src_sents] + [_content(t) for t in tgt_sents])
    beads = _split_out_deletions(_align_sentences(src_sents, tgt_sents, idf))
    for bead in beads:
        if bead.op in ("keep", "delete", "insert"):
            continue
        src_tokens = [t for s in bead.source for t in s if not t.is_space]
        tgt_tokens = [t for s in bead.target for t in s if not t.is_space]
        bead.spans = _span_edits(src_tokens, tgt_tokens)
    return beads
