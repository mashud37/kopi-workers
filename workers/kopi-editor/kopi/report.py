"""Write the `analyze` report as readable Markdown: each measure on a visual
scale bar with plain interpretation, grouped by the editable lever it speaks
to, plus TF-IDF key terms.
"""
from datetime import date
from pathlib import Path

_SCALE_WIDTH = 24
_KEY_TERM_BAR_WIDTH = 20
_KEY_TERMS_SHOWN = 15

# Short, plain imperative commands shown directly in the worksheet (in this
# order). These are the human-facing form of the LLM's per-paragraph directives.
_TAG_COMMAND = [
    ("wordiness", "Cut filler and padding"),
    ("redundancy", "Merge repeated points"),
    ("long-sentence", "Shorten long sentences"),
    ("passive", "Use the active voice"),
]

# Each before/after gauge: where the bar starts and ends, the mark for a good
# value, which direction counts as an improvement, and how the number prints.
_SENTENCE_LENGTH_SCALE = {
    "lo": 10,
    "hi": 40,
    "target": 20,
    "better": "down",
    "decimals": 1,
    "suffix": " words",
}
_WORD_COMPLEXITY_SCALE = {
    "lo": 1.2,
    "hi": 2.2,
    "target": 1.5,
    "better": "down",
    "decimals": 2,
    "suffix": " syll/word",
}
_DIFFICULT_WORDS_SCALE = {
    "lo": 0,
    "hi": 40,
    "target": 8,
    "better": "down",
    "decimals": 1,
    "suffix": "%",
}
_LENGTH_SCALE = {
    "lo": 0,
    "hi": 1,
    "target": 0,
    "better": "down",
    "decimals": 0,
    "suffix": " words",
}

# Flesch-Kincaid grade -> the audience that reads comfortably at that level.
_GRADE_BANDS = [
    (8, "general public"),
    (12, "high school"),
    (15, "undergraduate"),
]

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
        return "-"
    for threshold, label in _FLESCH_BANDS:
        if score >= threshold:
            return label
    return "very difficult"


def _cell_for(value: float, lo: float, hi: float, width: int) -> int:
    """Which cell of a scale bar a value falls in."""
    frac = (value - lo) / (hi - lo) if hi > lo else 0.0
    frac = max(0.0, min(1.0, frac))
    return int(round(frac * (width - 1)))


def scale_bar(value: float, lo: float, hi: float, target: float = None,
              width: int = _SCALE_WIDTH) -> str:
    """A text scale `[──●────│────]`: ● = value's position, │ = the target."""
    cells = ["─"] * width
    if target is not None:
        cells[_cell_for(target, lo, hi, width)] = "│"
    cells[_cell_for(value, lo, hi, width)] = "●"  # the value wins if it lands on the target
    return "[" + "".join(cells) + "]"


def _safe(measure, text: str, default=None):
    """One readability measurement, or the default when textstat cannot take it."""
    try:
        return measure(text)
    except Exception:
        return default


def _words_per_sentence(text: str):
    """Mean sentence length, under whichever name this textstat version gives it."""
    import textstat

    measure = getattr(textstat, "words_per_sentence", textstat.avg_sentence_length)
    return measure(text)


def _lexicon_count(text: str):
    """How many words the document has, punctuation not counted."""
    import textstat

    return textstat.lexicon_count(text, removepunct=True)


def _metrics(text: str) -> dict:
    """Document-level readability/complexity numbers (None where unavailable)."""
    try:
        import textstat
    except Exception:
        return {}
    lex = _safe(_lexicon_count, text) or 0
    diff = _safe(textstat.difficult_words, text) or 0
    return {
        "flesch": _safe(textstat.flesch_reading_ease, text),
        "grade": _safe(textstat.flesch_kincaid_grade, text),
        "fog": _safe(textstat.gunning_fog, text),
        "dale_chall": _safe(textstat.dale_chall_readability_score, text),
        "syll_per_word": _safe(textstat.avg_syllables_per_word, text),
        "words_per_sentence": _safe(_words_per_sentence, text),
        "difficult_pct": (100.0 * diff / lex) if lex else None,
    }


def key_terms(paragraphs: list[str], top: int = _KEY_TERMS_SHOWN) -> list[tuple[str, float]]:
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
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
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
    return f"- **{label}**: {value_str}\n  `{bar}`  {note}"


def _headline_section(source_name: str, summary: dict, m: dict) -> list[str]:
    """The report's opening: the document's counts, then reading ease and grade.

    Args:
        source_name: the file the report is about.
        summary: `words`, `paragraphs`, `editable`, `quotes` and `total_cut`.
        m: the document metrics from :func:`_metrics`.
    """
    words, total_cut = summary["words"], summary["total_cut"]
    removable = (total_cut / words * 100) if words else 0
    L = [
        f"# kopi-editor: Analysis: {source_name}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        f"{words} words · {summary['paragraphs']} paragraphs ({summary['editable']} editable, "
        f"{summary['quotes']} quotation(s)) · "
        f"~{total_cut} words removable ({removable:.0f}%)",
        "",
        "## Readability at a glance",
        "",
        "`●` = this document · `│` = a good target",
        "",
    ]
    if m.get("flesch") is not None:
        ease = m["flesch"]
        L.append(f"- **Reading ease**: {ease:.0f}/100 · {flesch_band(ease)}")
        L.append(f"  harder `{scale_bar(ease, 0, 100, target=60)}` easier")
    if m.get("grade") is not None:
        grade = m["grade"]
        audience = "postgraduate"
        for threshold, label in _GRADE_BANDS:
            if grade <= threshold:
                audience = label
                break
        L.append(f"- **Reading grade**: {grade:.0f} (≈ {audience})")
        L.append(f"  grade 6 `{scale_bar(grade, 6, 18, target=12)}` 18+")
    L.append("")
    return L


def _lever_section(m: dict, levers: dict) -> list[str]:
    """Each measure tied to the edit it argues for.

    Args:
        m: the document metrics from :func:`_metrics`.
        levers: `tag_counts`, `editable` and `n_editable` paragraph counts, the
            `unnecessary` and `redundancy` diagnosis totals, and the document
            `words` count the two savings bars are scaled against.
    """
    tag_counts = levers["tag_counts"]
    un, red, words = levers["unnecessary"], levers["redundancy"], levers["words"]
    n_editable = levers["n_editable"]
    L = [
        "## What to edit",
        "",
        "Each lever shows where the document sits and what editing it would address.",
        "",
    ]

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
        "Passive voice", f"{passive} of {levers['editable']} editable paragraph(s)",
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
    return L


def _key_terms_section(text: str) -> list[str]:
    """The document's most distinctive terms, each on a bar scaled to the top one."""
    terms = key_terms(text.split("\n\n"))
    if not terms:
        return []
    L = [
        "## Key terms & concepts",
        "",
        "The document's most distinctive terms (TF-IDF). Check that the concepts "
        "you intend to foreground actually appear here, and prominently.",
        "",
    ]
    top = terms[0][1] or 1.0
    for term, score in terms:
        L.append(f"- `{_fill_bar(score, top)}` {term}")
    L.append("")
    return L


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
    tag_counts = Counter()
    for paragraph in paras:
        tag_counts.update(paragraph["tags"])
    n_editable = max(1, editable)
    m = _metrics(text)

    L = _headline_section(source_name, {
        "words": words,
        "paragraphs": len(paras),
        "editable": editable,
        "quotes": quotes,
        "total_cut": total_cut,
    }, m)

    L += _lever_section(m, {
        "tag_counts": tag_counts,
        "editable": editable,
        "n_editable": n_editable,
        "unnecessary": un,
        "redundancy": red,
        "words": words,
    })
    L += _key_terms_section(text)

    # ---- Paragraph-by-paragraph worksheet ----
    L += _paragraph_section(paras)

    path.write_text("\n".join(L), encoding="utf-8-sig")
    return path


def _paragraph_section(paras: list) -> list[str]:
    """A full per-paragraph worksheet: every paragraph in order, its scores, and
    plain-language editing commands written straight into the table."""
    L = [
        "## Paragraph-by-paragraph",
        "",
        "Every paragraph in document order. **Plain-language editing applies to all of them**: "
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
        fl_str = "-" if fl is None else str(fl)
        if p.get("is_heading"):
            snip, fl_str, edit = f"*{snip}*", "-", "Heading: leave as is"
        elif p["is_quote"]:
            edit = "Quotation: leave as is"
        elif not p["instructions"]:
            edit = "Too short to edit"
        else:
            cmds = [cmd for tag, cmd in _TAG_COMMAND if tag in p["tags"]]
            edit = "; ".join(cmds) if cmds else "Plain words; cut what you can"
        L.append(f"| {n} | {snip} | {p['words']} | {fl_str} | {edit} |")
    L.append("")
    return L


def _num(v, nd=1) -> str:
    return "-" if v is None else f"{v:.{nd}f}"


def _delta_mark(before: float, after: float, better: str, nd: int) -> str:
    delta = after - before
    if abs(delta) < (10 ** -nd) / 2:
        return "➖ no change"
    improved = (delta < 0) if better == "down" else (delta > 0)
    return f"{'✅' if improved else '⚠️'} {delta:+.{nd}f}"


def _count_term(term: str, text: str) -> int:
    """How many times a key term appears in the text as a whole word."""
    import re

    return len(re.findall(r"\b" + re.escape(term) + r"\b", text))


def _compare_gauge(label: str, before, after, scale: dict) -> list[str]:
    """One measure as before/after sliders, stacked.

    Args:
        label: the measure's name, as the reader sees it.
        before: the value in the original text, or None if it could not be taken.
        after: the same measure on the edited text.
        scale: `lo`, `hi` and `target` for the bar, `better` ("up" or "down"),
            `decimals` for how the number prints, and an optional `suffix`.

    The whole label and bar live in one code span so the monospace font keeps the
    bars aligned column for column; plain-text spaces would collapse in rendered
    markdown and misalign them.
    """
    lo, hi, target = scale["lo"], scale["hi"], scale["target"]
    decimals = scale["decimals"]
    suffix = scale.get("suffix", "")
    if before is None or after is None:
        return [f"- **{label}**: {_num(before, decimals)} → {_num(after, decimals)}", ""]
    moved = _delta_mark(before, after, scale["better"], decimals)
    return [
        f"- **{label}**: {before:.{decimals}f}{suffix} → {after:.{decimals}f}{suffix}  {moved}",
        f"  `before {scale_bar(before, lo, hi, target=target)}`",
        f"  `after  {scale_bar(after, lo, hi, target=target)}`",
        "",
    ]


def comparison_lines(original: str, final: str) -> list[str]:
    """The before/after comparison as markdown lines (no title/date header), so it
    can stand alone or be embedded in the merged edit report.

    Same visual language as the analysis report: slider gauges per measure (showing
    the value move) and the key-terms bar plot, so the impact reads at a glance.
    """
    mb, ma = _metrics(original), _metrics(final)
    wb, wa = len(original.split()), len(final.split())

    L = [
        f"{wb} → {wa} words ({_delta_mark(wb, wa, 'down', 0)})",
        "",
        "## Readability & length",
        "",
        "`●` = value · `│` = a good target · top bar = before, bottom = after",
        "",
    ]
    L += _compare_gauge("Reading ease", mb.get("flesch"), ma.get("flesch"),
                        {"lo": 0, "hi": 100, "target": 60, "better": "up", "decimals": 0})
    L += _compare_gauge("Reading grade", mb.get("grade"), ma.get("grade"),
                        {"lo": 6, "hi": 18, "target": 12, "better": "down", "decimals": 1})
    L += _compare_gauge("Sentence length", mb.get("words_per_sentence"), ma.get("words_per_sentence"),
                        _SENTENCE_LENGTH_SCALE)
    L += _compare_gauge("Word complexity", mb.get("syll_per_word"), ma.get("syll_per_word"),
                        _WORD_COMPLEXITY_SCALE)
    L += _compare_gauge("Difficult words", mb.get("difficult_pct"), ma.get("difficult_pct"),
                        _DIFFICULT_WORDS_SCALE)
    L += _compare_gauge("Length", float(wb), float(wa),
                        {**_LENGTH_SCALE, "hi": max(1, wb), "target": wa})

    # ---- Key terms: before/after prominence (shared scale) per top concept ----
    before_terms = key_terms(original.split("\n\n"), top=_KEY_TERMS_SHOWN)
    if before_terms:
        orig_low, final_low = original.lower(), final.lower()
        b_counts = [_count_term(term, orig_low) for term, _ in before_terms]
        denom = max(b_counts) or 1  # shared scale -> the two bars are comparable
        kept = sum(1 for term, _ in before_terms if term.lower() in final_low)
        L += [
            "## Key terms: did they survive the edit?",
            "",
            f"{kept} of {len(before_terms)} top concepts from the original still appear in the edit. "
            "Each term's bars show how often it occurs **before** vs **after** (same scale), so you "
            "can see whether its prominence held.",
            "",
        ]
        for (term, _), bc in zip(before_terms, b_counts):
            ac = _count_term(term, final_low)
            mark = "✅" if ac > 0 else "⚠️ check"
            L += [
                f"- **{term}**: {bc} → {ac} occurrences {mark}",
                f"  `before {_fill_bar(bc, denom)}`",
                f"  `after  {_fill_bar(ac, denom)}`",
            ]
        L.append("")

    return L


def write_comparison(original: str, final: str, source_name: str, out_dir: Path) -> Path:
    """Standalone before/after report (title + date header + the comparison body)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{Path(source_name).stem}_comparison.md"
    L = [
        f"# kopi-editor: Before / After: {source_name}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        *comparison_lines(original, final),
    ]
    path.write_text("\n".join(L), encoding="utf-8-sig")
    return path


def _fill_bar(value: float, denom: float, width: int = _KEY_TERM_BAR_WIDTH) -> str:
    fill = min(width, int(round((value / denom) * width))) if denom else 0
    return "█" * fill + "░" * (width - fill)
