"""Register candidate methods grouped by the transformation family they
attack, including deliberate ablations, so a family is compared across
methods rather than measured by a single one.
"""
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from rules import probe_lexical_relative, rule_adjunct, rule_relative
from rules.rule_adjunct import Licence
from rules.rule_relative import Gates


@dataclass(frozen=True)
class Method:
    """One candidate solution for one family.

    Attributes:
        name: unique, ``family/variant``.
        family: the transformation family from ``docs/typology.md``.
        propose: ``propose(doc) -> Iterable[Edit]``, the rule contract.
        note: what this variant is testing, in one line.
        baseline: True when this is the currently shipped behaviour.
    """
    name: str
    family: str
    propose: Callable
    note: str
    baseline: bool = False


def _relative(**overrides) -> Callable:
    return partial(rule_relative.propose, gates=Gates(**overrides))


def _adjunct(**overrides) -> Callable:
    return partial(rule_adjunct.propose, licence=Licence(**overrides))


METHODS = (
    Method(
        "relative/all-gates", "relative-clause", _relative(),
        "every licence condition enforced, including the it-cleft block",
        baseline=True,
    ),
    # Probe-only, on its own family name so no experiment picks it up. Kept so
    # that C13's refusal stays reproducible rather than resting on a script.
    Method(
        "relative/lexical-probe", "relative-clause-lexical",
        probe_lexical_relative.propose,
        "probe only, never registered: 'which revolve around' to 'revolving around'",
    ),
    Method(
        "relative/no-cleft-gate", "relative-clause", _relative(block_cleft=False),
        "what shipped before 2026-07-26, which broke it-clefts",
    ),
    Method(
        "relative/no-copula-gate", "relative-clause", _relative(copula_only=False),
        "ablation: drops the be-terminal test, so an active perfect may reduce",
    ),
    Method(
        "relative/no-complement-gate", "relative-clause",
        _relative(adjective_complement=False),
        "ablation: allows a bare predicate adjective to reduce",
    ),
    Method(
        "relative/no-subject-gate", "relative-clause",
        _relative(subject_relativiser=False),
        "ablation: allows an object relativiser to reduce, stranding the verb",
    ),
    Method(
        "adjunct/ranked", "adjunct", _adjunct(model="ranked"),
        "band as budget: propose freely, order by droppability, spend the word target",
    ),
    Method(
        "adjunct/ranked-arg", "adjunct", _adjunct(model="ranked", argument_ceiling=0.30),
        "as ranked, plus a distributional argument test: refuse a preposition the "
        "governor takes 30% of the time or more",
    ),
    Method(
        "adjunct/ranked-arg-strict", "adjunct",
        _adjunct(model="ranked", argument_ceiling=0.15),
        "as ranked-arg, but half as tolerant before calling a preposition obligatory",
    ),
    Method(
        "adjunct/syntactic", "adjunct", _adjunct(model="syntactic"),
        "baseline with no lexical knowledge: attachment and phrase size only",
        baseline=True,
    ),
    Method(
        "adjunct/frame", "adjunct", _adjunct(model="frame"),
        "induced drop rate for this exact governor and preposition, else refuse",
    ),
    Method(
        "adjunct/backoff", "adjunct", _adjunct(model="backoff"),
        "induced rate with backoff from frame to governor class to preposition",
    ),
    Method(
        "adjunct/backoff-strict", "adjunct", _adjunct(model="backoff", minimum=20),
        "same, but four times the evidence before a rate is trusted",
    ),
)

FAMILIES = tuple(dict.fromkeys(method.family for method in METHODS))


def for_family(family: str) -> tuple:
    return tuple(method for method in METHODS if method.family == family)


def named(name: str) -> Method:
    for method in METHODS:
        if method.name == name:
            return method
    raise SystemExit(f"unknown method: {name}")
