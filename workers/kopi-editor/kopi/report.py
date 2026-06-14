"""Build the `analyze` report — a comprehensive, human-readable Markdown file.

The report is designed to be *read*, not decoded: each measure is shown on a
visual scale (`[──●───│────]`, ● = this document, │ = a good target) with a plain
interpretation, and the measures are organised by the editable lever they speak
to (sentence length, word complexity, passive voice, wordiness, redundancy)
rather than dumped as a table of overlapping indices.

It also extracts the document's **key terms / concepts** (TF-IDF over the
paragraphs, with bigrams/trigrams — the interpretable IR baseline) so the author
can check that the concepts they care about actually surface prominently.
"""
from datetime import date
from pathlib import Path

# Flesch Reading Ease bands -> plain interpretation (higher = easier).
_FLESCH_BANDS = [
    (90, "very easy (5th grade)"),
    (80, "easy (6th grade)"),
    (70, "fairly easy (7th grade)"),
    (60, "plain English (8th–9th grade)"),
    (50, "fairly difficult (10th–12th grade)"),
    (30, "difficult (college)"),
    (0, "very difficult (college graduate)"),
]


def flesch_band(score) -> str:
    if score is None:
        return "—"
    for threshold, label in _FLESCH_BANDS:
        if score >= threshold:
            return label
    return "very difficult"


def _grade_audience(grade: float) -> str:
    if grade <= 8:
        return "general public"
    if grade <= 12:
        return "high school"
    if grade <= 15:
        return "undergraduate"
    return "postgraduate"


def scale_bar(value: float, lo: float, hi: float, target: float = None, width: int = 24) -> str:
    """A text scale `[──●────│────]`: ● = value's position, │ = the target."""
    def _pos(v):
        frac = (v - lo) / (hi - lo) if hi > lo else 0.0
        frac = max(0.0, min(1.0, frac))
        return int(round(frac * (width - 1)))

    cells = ["─"] * width
    if target is not None:
        cells[_pos(target)] = "│"
    p = _pos(value)
    cells[p] = "●"  # value marker wins if it coincides with the target
    return "[" + "".join(cells) + "]"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _metrics(text: str) -> dict:
    """Document-level readability/complexity numbers (None where unavailable)."""
    try:
        import textstat
    except Exception:
        return {}
    wps = _safe(lambda: getattr(textstat, "words_per_sentence", textstat.avg_sentence_length)(text))
    lex = _safe(lambda: textstat.lexicon_count(text, removepunct=True)) or 0
    diff = _safe(lambda: textstat.difficult_words(text)) or 0
    return {
        "flesch": _safe(lambda: textstat.flesch_reading_ease(text)),
        "grade": _safe(lambda: textstat.flesch_kincaid_grade(text)),
        "fog": _safe(lambda: textstat.gunning_fog(text)),
        "dale_chall": _safe(lambda: textstat.dale_chall_readability_score(text)),
        "syll_per_word": _safe(lambda: textstat.avg_syllables_per_word(text)),
        "words_per_sentence": wps,
        "difficult_pct": (100.0 * diff / lex) if lex else None,
    }


def key_terms(paragraphs: list[str], top: int = 15) -> list[tuple[str, float]]:
    """Top key terms/concepts by TF-IDF over the paragraphs (uni/bi/tri-grams).

    The interpretable IR baseline (TF-IDF + n-grams, per the cs/ir reference):
    terms that are frequent in some paragraphs but not ubiquitous score highest,
    so the document's distinctive concepts surface. Substring duplicates are
    collapsed (prefer the longer phrase). Returns [] if sklearn/text is too thin.
    """
    paras = [p for p in paragraphs if len(p.split()) >= 20]
    if len(paras) < 3:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
    except Exception:
        return []
    try:
        vec = TfidfVectorizer(
            ngram_range=(1, 3), stop_words="english",
            min_df=2, max_df=0.5,
            token_pattern=r"(?u)\b[A-Za-z][A-Za-z-]{2,}\b",
        )
        X = vec.fit_transform(paras)
        scores = np.asarray(X.sum(axis=0)).ravel()
        terms = vec.get_feature_names_out()
        order = scores.argsort()[::-1]
    except Exception:
        return []

    out: list[tuple[str, float]] = []
    for i in order:
        term = terms[i]
        if any(term in o or o in term for o, _ in out):  # collapse substrings
            continue
        out.append((term, float(scores[i])))
        if len(out) >= top:
            break
    return out


def _lever(label: str, value_str: str, bar: str, note: str) -> str:
    return f"- **{label}** — {value_str}\n  `{bar}`  {note}"


def write_analysis(diag: dict, text: str, source_name: str, out_dir: Path) -> Path:
    """Write the analysis report and return its path."""
    from collections import Counter

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{Path(source_name).stem}_analysis.md"

    words = diag["words"]
    un = diag["unnecessary"]
    red = diag["redundancy"]
    total_cut = un["savings"] + red["savings"]
    paras = diag["paragraphs"]
    editable = sum(1 for p in paras if p["instructions"])
    quotes = sum(1 for p in paras if p["is_quote"])
    tag_counts = Counter(t for p in paras for t in p["tags"])
    n_editable = max(1, editable)
    m = _metrics(text)

    L = [
        f"# kopi-editor — Analysis: {source_name}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        f"{words} words · {len(paras)} paragraphs ({editable} editable, {quotes} quotation(s)) · "
        f"~{total_cut} words removable ({(total_cut / words * 100) if words else 0:.0f}%)",
        "",
        "## Readability at a glance",
        "",
        "`●` = this document · `│` = a good target",
        "",
    ]

    if m.get("flesch") is not None:
        f = m["flesch"]
        L.append(f"- **Reading ease** — {f:.0f}/100 · {flesch_band(f)}")
        L.append(f"  harder `{scale_bar(f, 0, 100, target=60)}` easier")
    if m.get("grade") is not None:
        g = m["grade"]
        L.append(f"- **Reading grade** — {g:.0f} (≈ {_grade_audience(g)})")
        L.append(f"  grade 6 `{scale_bar(g, 6, 18, target=12)}` 18+")
    L.append("")

    # --- Editable levers: each measure tied to the edit it argues for ----------
    L += ["## What to edit", "", "Each lever shows where the document sits and what editing it would address.", ""]

    if m.get("words_per_sentence") is not None:
        wps = m["words_per_sentence"]
        long_paras = tag_counts.get("long-sentence", 0)
        L.append(_lever(
            "Sentence length", f"{wps:.0f} words per sentence on average",
            scale_bar(wps, 10, 40, target=20),
            f"{long_paras} paragraph(s) run long → break them up (target ≈ 20).",
        ))
    if m.get("syll_per_word") is not None or m.get("dale_chall") is not None:
        spw = m.get("syll_per_word") or 0
        dc = m.get("dale_chall")
        dc_str = f", Dale–Chall {dc:.1f}" if dc is not None else ""
        L.append(_lever(
            "Word complexity", f"{spw:.2f} syllables per word{dc_str}",
            scale_bar(spw, 1.2, 2.2, target=1.5),
            "→ prefer short, plain words over long Latinate ones.",
        ))
    passive = tag_counts.get("passive", 0)
    L.append(_lever(
        "Passive voice", f"{passive} of {editable} editable paragraph(s)",
        scale_bar(passive, 0, n_editable, target=n_editable * 0.15),
        "→ prefer the active voice where it reads naturally.",
    ))
    L.append(_lever(
        "Wordiness", f"{un['hits']} filler/padding phrase(s), ~{un['savings']} words",
        scale_bar(un["savings"], 0, max(50, words * 0.05), target=0),
        "→ cut hedges, fillers, and padding.",
    ))
    L.append(_lever(
        "Redundancy", f"{red['count']} restated sentence(s), ~{red['savings']} words",
        scale_bar(red["savings"], 0, max(50, words * 0.08), target=0),
        "→ consolidate points already made.",
    ))
    L.append("")

    # --- Key terms / concepts --------------------------------------------------
    terms = key_terms(text.split("\n\n"))
    if terms:
        L += [
            "## Key terms & concepts",
            "",
            "The document's most distinctive terms (TF-IDF). Check that the concepts "
            "you intend to foreground actually appear here — and prominently.",
            "",
        ]
        top = terms[0][1] or 1.0
        for term, score in terms:
            fill = int(round((score / top) * 20))
            bar = "█" * fill + "░" * (20 - fill)
            L.append(f"- `{bar}` {term}")
        L.append("")

    # --- Paragraph-by-paragraph worksheet -------------------------------------
    L += _paragraph_section(paras)

    path.write_text("\n".join(L), encoding="utf-8-sig")
    return path


# Short, plain imperative commands shown directly in the worksheet (in this
# order). These are the human-facing form of the LLM's per-paragraph directives.
_TAG_COMMAND = [
    ("wordiness", "Cut filler and padding"),
    ("redundancy", "Merge repeated points"),
    ("long-sentence", "Shorten long sentences"),
    ("passive", "Use the active voice"),
]


def _paragraph_section(paras: list) -> list[str]:
    """A full per-paragraph worksheet: every paragraph in order, its scores, and
    plain-language editing commands written straight into the table."""
    L = [
        "## Paragraph-by-paragraph",
        "",
        "Every paragraph in document order. **Plain-language editing applies to all of them** — "
        "prefer short plain words, cut clichés, and remove every word you can. The **What to edit** "
        "column lists any *extra* work. Lower Flesch = harder to read.",
        "",
        "| # | Opening | Words | Flesch | What to edit |",
        "|---|---------|------:|-------:|--------------|",
    ]
    for p in paras:
        n = f"P{p['index'] + 1}"
        snip = (p.get("snippet") or "").replace("|", "\\|")
        fl = p.get("flesch")
        fl_str = "—" if fl is None else str(fl)
        if p.get("is_heading"):
            snip, fl_str, edit = f"*{snip}*", "—", "Heading — leave as is"
        elif p["is_quote"]:
            edit = "Quotation — leave as is"
        elif not p["instructions"]:
            edit = "Too short to edit"
        else:
            cmds = [cmd for tag, cmd in _TAG_COMMAND if tag in p["tags"]]
            edit = "; ".join(cmds) if cmds else "Plain words; cut what you can"
        L.append(f"| {n} | {snip} | {p['words']} | {fl_str} | {edit} |")
    L.append("")
    return L


def _num(v, nd=1) -> str:
    return "—" if v is None else f"{v:.{nd}f}"


def _delta_mark(before: float, after: float, better: str, nd: int) -> str:
    delta = after - before
    if abs(delta) < (10 ** -nd) / 2:
        return "➖ no change"
    improved = (delta < 0) if better == "down" else (delta > 0)
    return f"{'✅' if improved else '⚠️'} {delta:+.{nd}f}"


def _compare_gauge(label, vb, va, lo, hi, target, better, nd, suffix="") -> list[str]:
    """One measure as before/after sliders, stacked. The whole label+bar lives in
    one code span so the monospace font keeps the bars aligned column-for-column
    (plain-text spaces would collapse in rendered markdown and misalign them)."""
    if vb is None or va is None:
        return [f"- **{label}** — {_num(vb, nd)} → {_num(va, nd)}", ""]
    return [
        f"- **{label}** — {vb:.{nd}f}{suffix} → {va:.{nd}f}{suffix}  {_delta_mark(vb, va, better, nd)}",
        f"  `before {scale_bar(vb, lo, hi, target=target)}`",
        f"  `after  {scale_bar(va, lo, hi, target=target)}`",
        "",
    ]


def write_comparison(original: str, final: str, source_name: str, out_dir: Path) -> Path:
    """After a full edit, write a before/after report in the SAME visual language as
    the analysis report — slider gauges per measure (showing the value move) and the
    key-terms bar plot — so the impact reads at a glance. Returns the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{Path(source_name).stem}_comparison.md"

    mb, ma = _metrics(original), _metrics(final)
    wb, wa = len(original.split()), len(final.split())

    L = [
        f"# kopi-editor — Before / After: {source_name}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        f"{wb} → {wa} words ({_delta_mark(wb, wa, 'down', 0)})",
        "",
        "## Readability & length",
        "",
        "`●` = value · `│` = a good target · top bar = before, bottom = after",
        "",
    ]
    L += _compare_gauge("Reading ease", mb.get("flesch"), ma.get("flesch"), 0, 100, 60, "up", 0)
    L += _compare_gauge("Reading grade", mb.get("grade"), ma.get("grade"), 6, 18, 12, "down", 1)
    L += _compare_gauge("Sentence length", mb.get("words_per_sentence"), ma.get("words_per_sentence"),
                        10, 40, 20, "down", 1, " words")
    L += _compare_gauge("Word complexity", mb.get("syll_per_word"), ma.get("syll_per_word"),
                        1.2, 2.2, 1.5, "down", 2, " syll/word")
    L += _compare_gauge("Difficult words", mb.get("difficult_pct"), ma.get("difficult_pct"),
                        0, 40, 8, "down", 1, "%")
    L += _compare_gauge("Length", float(wb), float(wa), 0, max(1, wb), wa, "down", 0, " words")

    # --- Key terms: before/after prominence (shared scale) per top concept -----
    before_terms = key_terms(original.split("\n\n"), top=15)
    if before_terms:
        import re
        orig_low, final_low = original.lower(), final.lower()

        def _count(term: str, text: str) -> int:
            return len(re.findall(r"\b" + re.escape(term) + r"\b", text))

        b_counts = [_count(t, orig_low) for t, _ in before_terms]
        denom = max(b_counts) or 1  # shared scale -> the two bars are comparable
        kept = sum(1 for t, _ in before_terms if t.lower() in final_low)
        L += [
            "## Key terms — did they survive the edit?",
            "",
            f"{kept} of {len(before_terms)} top concepts from the original still appear in the edit. "
            "Each term's bars show how often it occurs **before** vs **after** (same scale), so you "
            "can see whether its prominence held.",
            "",
        ]
        for (term, _), bc in zip(before_terms, b_counts):
            ac = _count(term, final_low)
            mark = "✅" if ac > 0 else "⚠️ check"
            L += [
                f"- **{term}** — {bc} → {ac} occurrences {mark}",
                f"  `before {_fill_bar(bc, denom)}`",
                f"  `after  {_fill_bar(ac, denom)}`",
            ]
        L.append("")

    path.write_text("\n".join(L), encoding="utf-8-sig")
    return path


def _fill_bar(value: float, denom: float, width: int = 20) -> str:
    fill = min(width, int(round((value / denom) * width))) if denom else 0
    return "█" * fill + "░" * (width - fill)
