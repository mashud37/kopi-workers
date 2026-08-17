"""Run every registered method for a transformation family against the same
cases and corpus, scoring each on case pass/fail, corpus SARI, attestation
ceiling against Opus, and introduced grammatical defects.
"""
from collections import Counter
from dataclasses import dataclass, field

from eval.grammatical import introduced
from eval.harness import _attested
from eval.sari import corpus_sari
from experiments import cases as case_bank
from lint import bands
from lint.run import lint_paragraph


@dataclass
class MethodReport:
    name: str
    note: str
    baseline: bool = False
    cases_run: int = 0
    case_failures: list = field(default_factory=list)
    fired: int = 0
    changed: int = 0
    words_removed: int = 0
    attested: int = 0
    defect_paragraphs: int = 0
    defects: Counter = field(default_factory=Counter)
    sari: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.case_failures

    @property
    def ceiling(self) -> float:
        return self.attested / self.fired if self.fired else 0.0


_CASE_BAND = "firm"


def _touched(case, spans: list) -> bool:
    """Whether the method acted on the span the case names, if it names one."""
    if not case.span:
        return bool(spans)
    wanted = " ".join(case.span.split()).lower()
    return any(wanted in " ".join(s.split()).lower() for s in spans)


def _fired(method, case, nlp) -> dict:
    """Whether the method acts on this case, and what it did.

    Threshold families are judged on what they *propose*, because for them a
    proposal that clears the band is an assertion that the edit is licensed.
    Ranked families are judged on what *survives the pipeline*: proposing freely
    is the design, and the band's word budget, not the rule, decides how deep the
    cut goes. Judging a ranked family on its proposals asks it to be a threshold
    family and fails it for not being one.
    """
    proposals = method.propose(nlp(case.text))
    if not any(e.ranked for e in proposals):
        acted = [e.source(case.text) for e in proposals]
        note = proposals[0].note if proposals else "proposed nothing"
        return {"fired": _touched(case, acted), "what": note}
    result = lint_paragraph(case.text, nlp, bands.band(_CASE_BAND),
                            rules=((method.name, method.propose),))
    acted = [e.source(case.text) for e in result.applied]
    what = f"applied {result.applied[0].note}" if result.applied else (
        result.reason or "applied nothing")
    return {"fired": _touched(case, acted), "what": what}


def _swallowed(method, case, nlp) -> str:
    """Text the case protects that the method deleted anyway, if any.

    Separate from :func:`_touched` because it asks the opposite question. A case
    can want an edit *and* want it to stop short, and containment matching
    cannot express that on its own.
    """
    if not case.survives:
        return ""
    wanted = " ".join(case.survives.split()).lower()
    for edit in method.propose(nlp(case.text)):
        if wanted in " ".join(edit.source(case.text).split()).lower():
            return f"deleted the protected text: {edit.source(case.text)!r}"
    return ""


def run_cases(method, nlp) -> dict:
    """Check one method against every case registered for its family."""
    failures = []
    relevant = case_bank.for_family(method.family)
    for case in relevant:
        outcome = _fired(method, case, nlp)
        if (case.expect == "refuse") == outcome["fired"]:
            failures.append((case, outcome["what"]))
            continue
        swallowed = _swallowed(method, case, nlp)
        if swallowed:
            failures.append((case, swallowed))
    return {"run": len(relevant), "failures": failures}


def run_corpus(method, samples, nlp, on_progress=None) -> MethodReport:
    """Score one method over the gold corpus, in isolation from every other."""
    report = MethodReport(name=method.name, note=method.note, baseline=method.baseline)
    cases = run_cases(method, nlp)
    report.cases_run, report.case_failures = cases["run"], cases["failures"]
    rules = ((method.name, method.propose),)
    triples = []
    for i, sample in enumerate(samples, 1):
        if on_progress:
            on_progress(i, len(samples), method.name)
        band = bands.band(sample.band) if sample.band in bands.BANDS else bands.band("firm")
        result = lint_paragraph(sample.original, nlp, band, rules=rules)
        report.changed += int(result.changed)
        report.words_removed += max(0, result.words_saved)
        for edit in result.applied:
            report.fired += 1
            report.attested += int(_attested(edit, sample.original, sample.edit, nlp))
        net = introduced(sample.original, result.edited, nlp)
        if net:
            report.defect_paragraphs += 1
            report.defects.update(net)
        triples.append((sample.original, result.edited, sample.edit))
    report.sari = corpus_sari(triples)
    return report


def baseline_sari(samples) -> dict:
    """Corpus SARI for doing nothing, which is the bar every method must clear."""
    return corpus_sari([(s.original, s.original, s.edit) for s in samples])


def check_realisation(nlp) -> list:
    """The repair layer's cases, which belong to no rule and so run on their own."""
    from grammar.realise import repair
    from lint.guard import quoted_spans

    failures = []
    for case in case_bank.for_family("realisation"):
        # Whole-paragraph scope on purpose. Scoping repair to edit joins means
        # the pipeline no longer touches these sentences at all, but a detector
        # that is wrong here is still wrong when an edit lands next to it, so the
        # strict version of the test is the one worth keeping.
        out = repair(case.text, protected=quoted_spans(case.text))
        changed = out.strip() != case.text.strip()
        if case.expect == "unchanged" and changed:
            failures.append((case, f"rewrote it as: {out}"))
        elif case.expect == "fire" and not changed:
            failures.append((case, "left it unchanged"))
    return failures
