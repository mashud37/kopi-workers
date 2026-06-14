"""The analyze report writer: visual gauges, editable levers, and key terms."""
from kopi import report


def _diag():
    return {
        "words": 1000,
        "readability": 25.2,
        "unnecessary": {"hits": 16, "savings": 51},
        "redundancy": {"count": 9, "savings": 271},
        "paragraphs": [
            {"index": 0, "words": 80, "is_quote": False,
             "tags": {"plain-language", "passive", "long-sentence"}, "instructions": ["x", "y"]},
            {"index": 1, "words": 10, "is_quote": True, "tags": set(), "instructions": []},
        ],
    }


def test_write_analysis_creates_report(tmp_path):
    path = report.write_analysis(_diag(), "Some prose. " * 200, "chapter 1.docx", tmp_path)
    assert path.exists()
    assert path.name == "chapter 1_analysis.md"
    body = path.read_text(encoding="utf-8-sig")
    for heading in ("## Readability at a glance", "## What to edit", "## Paragraph-by-paragraph"):
        assert heading in body
    assert "Wordiness" in body and "Redundancy" in body
    assert "~322 words removable" in body  # 51 + 271
    # The per-paragraph worksheet lists each paragraph with plain commands.
    assert "| P1 |" in body and "What to edit" in body
    assert "Shorten long sentences" in body  # P0 has the long-sentence tag


def test_write_comparison_shows_before_after(tmp_path):
    original = ("It is worth noting that the utilisation of the methodology is important here. " * 6
                + "\n\n" + "A further paragraph that endeavours to ascertain the facts at some length here. " * 4)
    final = ("Personalisation matters and the method is clear. " * 4
             + "\n\n" + "A further paragraph that finds the facts. " * 3)
    path = report.write_comparison(original, final, "chapter 1.docx", tmp_path)
    assert path.name == "chapter 1_comparison.md"
    body = path.read_text(encoding="utf-8-sig")
    assert "## Readability & length" in body
    assert "Reading ease" in body
    # Same slider visuals as the analysis report, stacked before/after inside a
    # code span (monospace) so the bars stay aligned.
    assert "`before [" in body and "`after  [" in body
    assert "●" in body
    # Word count dropped, so the header should show the reduction.
    assert "→" in body and "words" in body


def test_flesch_band():
    assert "plain English" in report.flesch_band(65)
    assert "very easy" in report.flesch_band(95)
    assert "very difficult" in report.flesch_band(10)
    assert report.flesch_band(None) == "—"


def test_scale_bar_marks_value_and_target():
    bar = report.scale_bar(0, 0, 100, target=100, width=10)
    assert bar.startswith("[") and bar.endswith("]")
    assert "●" in bar and "│" in bar
    # Value at the low end -> marker near the start.
    assert bar.index("●") < bar.index("│")


def test_key_terms_surface_distinctive_phrases():
    # Paragraphs must clear the 20-word floor; the target phrase appears in a
    # minority of them (under the max_df ceiling), as a real key concept would.
    pad = "and the broader argument continues across several further clauses to fill the line out here"
    paras = [
        f"Consumer culture shapes social media use among ordinary people every day {pad}.",
        f"Social media platforms reshape everyday consumer practice for many users today {pad}.",
        f"A separate paragraph about coastal weather patterns and seasonal tides nearby {pad}.",
        f"Another section discussing medieval cathedral architecture and stone vaulting {pad}.",
        f"A final passage on orbital mechanics and the trajectories of distant comets {pad}.",
    ]
    terms = report.key_terms(paras, top=10)
    joined = " ".join(t for t, _ in terms)
    assert terms  # sklearn produced something
    assert "social media" in joined
