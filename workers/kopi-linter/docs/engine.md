# Engine ledger

What exists, what it is measured at, and what is only designed. Maintained so that an overview
of the project never has to be reconstructed by reading code, and so that designed-but-unbuilt
techniques cannot read as built.

Status vocabulary, used strictly:

- **running**: in the pipeline, exercised on the full corpus
- **built, unverified**: code exists, no test or corpus measurement backs it
- **withdrawn**: built, measured, removed on the evidence
- **paper**: designed in `approaches.md`, not written

---

## 1. Measurement layer (`evidence/`)

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `align.py` | Gale and Church (1993) bead alignment, run monolingually; beads relabelled 1-1 rewrite / 1-n split / n-1 merge / 1-0 cut | running | 1,523 paragraphs, 22,631 transformations |
| `align.py` | Needleman-Wunsch DP over the monotone grid, fanout capped at 3 | running | exact given the cost model |
| `align.py` | IDF-weighted content-lemma containment as the bead cost, replacing the character-length prior that is meaningless monolingually | running | cost model is a choice, not validated |
| `align.py` | `_split_out_deletions`: promotes a source sentence to a deletion when its content lemmas fail to survive, which Gale and Church cannot express | running | reclassified 23% of merge sources on a 400-edit probe |
| `align.py` | Sorted-order float summation to defeat Python hash randomisation flipping DP ties | running | identical output over 3 processes |
| `taxonomy.py` | Ordered cascade: dependency relations, WordNet derivational morphology, `wordfreq`, concreteness | running | no held-out accuracy figure |
| `taxonomy.py` | MIP (Pragglejaz) operationalised as a WordNet `physical_entity` concreteness test for dead metaphor | running | unvalidated |
| `editor_rules.py` | Coverage bridge to kopi-editor's 165 production rules | running | 44 of 22,631 transformations (0.2%) |
| `induce.py` | Rule confidence induced from the gold's own behaviour rather than asserted | running | light-verb base rate 20.2%, 1,006 observations |

## 2. Engine (`lint/`)

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `run.py` | Six stages: parse, propose, select, apply, realise, guard | running | 1,523 paragraphs |
| `registry.py` | Rules propose only; nothing applies until every proposal is seen, so output is independent of rule order | running | property holds by construction |
| `registry.py` | Failures surfaced, never swallowed | running | added after a broken rule looked identical to a quiet one |
| `select.py` | Weighted interval scheduling, exact DP with `bisect` predecessors, over conflicting proposals | running | exact; untested against a greedy baseline |
| `bands.py` | Per-family confidence thresholds over one rule set, not four rule sets | running | thresholds hand-set, not induced |
| `guard.py` | Citation set, number preservation, band floor, non-empty | running | all four passed on a known-broken output |
| `guard.py` | Quoted spans protected from rule proposals | running | did not protect against the realiser until 2026-07-26 |

## 3. Transformation families (`rules/`)

| Family | Status | Fired | Attestation |
|---|---|---|---|
| `relative-clause` reduction (whiz-deletion) | running | 114 | **ceiling 89%**, previously misreported as 100% |
| `support-verb` collapse | withdrawn | 2 | disagreed twice; 20% base rate did not support firing |
| `adjunct` PP-drop, structural licence | built, rejected | 647 | **2%** ceiling; over-fires, see constraints C9 |
| `adjunct` PP-drop, induced licence (3 variants) | built, rejected | 3 | cannot reach any band threshold, see C9 |
| `voice` restoration | paper | | 1,176 / 3,032; the family that would open the SARI `add` column |
| `nominalisation` to verb | paper | | |
| `sentence` merge and cut | paper | | 457 instances / 8,255 words, the largest by word budget |
| lexical substitution | paper | | |
| connective repair | paper | | |

## 4. Surface repair (`grammar/`)

| Component | Technique | Status |
|---|---|---|
| `orthography.py` | Generative British/American suffix bridge with a curated exception set; load-bearing because WordNet answers in American and has no entry for coinages like "anonymisation" | running, round-trip verified |
| `realise.py` | Repair scoped to the joins the edits created; a paragraph nothing fired on is returned byte-identical | running, verified |
| `realise.py` | Article selection by sound rather than spelling | running |
| `realise.py` | Abbreviation and initialism detection before sentence-start capitalisation | running, case-checked |
| `realise.py` | Ellipsis is not a sentence end | running, case-checked |
| `realise.py` | Quoted spans passed through verbatim | running, case-checked |

## 5. Evaluation (`eval/`)

| Component | Technique | Status |
|---|---|---|
| `sari.py` | Corpus-level SARI (Xu et al. 2016), pooled not averaged | running |
| `harness.py` | Per-rule attestation against the gold | running, **shape corrected 2026-07-26** |
| `harness.py` | Function-word deletions checked on the anchored surface, because the content-lemma test degenerates to a constant | built, unverified |
| | Grammaticality check | **missing**; this is what would have caught the it-cleft |
| | Damage rate on a hand-checked held-out set | **missing**; nothing substitutes for it |
| `experiments/compare.py` | Method-versus-method comparison for one family, cases plus corpus | running |
| `experiments/ranking.py` | Ranking evaluation (precision at oracle k, MAP) against a shuffle baseline, decoupled from the pipeline | running |

## 6. Headline numbers, with their caveats

Corpus SARI over 1,523 gold paragraphs:

| System | SARI | add | keep | delete |
|---|---:|---:|---:|---:|
| do nothing | 0.2439 | 0.0000 | 0.7316 | 0.0000 |
| kopi-linter | 0.5250 | 0.0012 | 0.7322 | 0.8415 |
| served Qwen3-32B | 0.5125 | 0.2040 | 0.7111 | 0.6224 |

Read with section 5.4 of `good.md`: the linter changes **108 of 1,523 paragraphs (7.1%)** and
moves **229 words against Opus's 23,047**. It passes a 32B model on the composite while doing
about one percent of the work, which is the clearest possible argument for never reporting the
composite alone.

The previous figures on this line were 0.4580 and 0.6408 delete. The gain came entirely from
scoping the repair layer (constraints C6), not from a rule.

The `add` column is the whole remaining gap and none of the families that would fill it exist.
