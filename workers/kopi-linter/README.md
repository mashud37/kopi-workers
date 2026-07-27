# kopi-linter

Plain-language copy-editing of academic prose currently needs a language model, which means
a GPU service or an API bill for every draft, and kopi-editor's deterministic route only
reaches the safe mechanical fixes: fixed filler phrases, cliché swaps, grammar. kopi-linter
exists to find out how far the rest can be taken deterministically, on one machine, with
nothing leaving it. Its wager is that the editorial judgement in question is not
unreachable, only undocumented: kopi-learner already holds 1,523 paragraphs edited by Opus
across four intensity bands, so what a good editor does to academic prose is a measurable
object rather than a matter of opinion. The repo starts from that measurement. The evidence
layer aligns every gold edit with its original, classifies each difference by its
linguistic type, and reports what a rule set would actually have to do; the transformation
layers are then built and justified against that report, not against intuition.

It holds no secrets and makes no network calls, because a linter that never sends a
paragraph anywhere is the point rather than a feature.

## Status

Early, and deliberately measured rather than advertised. The evidence layer, the linting
engine and the experiment harness all run. One transformation family is live
(relative-clause reduction); a second (`adjunct`) has three competing licence models under
comparison and none of them is registered yet.

Progress is tracked as a single per cent, **closure**, defined in
[docs/good.md](docs/good.md) section 0 and standing at 0.2%. The work follows a fixed loop,
analyse then plan then build then evaluate then analyse again, set out in
[docs/method.md](docs/method.md). Six documents carry the state:

| Document | Question it answers |
|---|---|
| [docs/plan.md](docs/plan.md) | where this is going, what each phase is worth, and how it fails |
| [docs/typology.md](docs/typology.md) | what a plain-language linter has to do, measured from 1,523 gold edits |
| [docs/approaches.md](docs/approaches.md) | which techniques might do it |
| [docs/constraints.md](docs/constraints.md) | what building it revealed, and what each limit blocks |
| [docs/good.md](docs/good.md) | what a correct edit is, and how anything is scored |
| [docs/method.md](docs/method.md) | how an increment is allowed to proceed |

## Data flow

```mermaid
flowchart TD
    CORPUS[("kopi-learner<br/>gold Opus edits")] --> EVIDENCE["evidence:<br/>align and classify<br/>every gold edit"]
    EVIDENCE --> REPORT[("output/evidence_&lt;role&gt;.md")]
    EVIDENCE --> INDUCE["induce:<br/>calibrate rule<br/>confidence from the gold"]
    INDUCE --> TABLES[("rules/induced_*.py")]

    DOC[/"input/*.md"/] --> PARSE["parse"]
    PARSE --> PROPOSE["rules propose<br/>(never apply)"]
    TABLES --> PROPOSE
    PROPOSE --> SELECT["select:<br/>band gate, then best<br/>non-overlapping set"]
    SELECT --> APPLY["apply + realise:<br/>splice, then repair<br/>the surface"]
    APPLY --> GUARD{"guard:<br/>citations, numbers,<br/>band ceiling"}
    GUARD -->|"pass"| OUT[("output/&lt;name&gt;_linted.md<br/>+ change log")]
    GUARD -->|"fail"| KEEP[("paragraph kept<br/>unchanged")]

    CORPUS --> SCORE["evaluate:<br/>corpus SARI vs Opus,<br/>agreement per rule"]
    APPLY --> SCORE

    classDef store fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a;
    classDef route fill:#e6f4ea,stroke:#34a853,color:#1a1a1a;
    class CORPUS,REPORT,TABLES,OUT,KEEP store;
    class GUARD route;
```

## Layout

```
manage.py               entrypoint (no args opens the menu)
requirements.txt
evidence/               load, align, taxonomy, induce, adjuncts: the measurement layer
lint/                   edit, registry, select, bands, guard, run: the engine
rules/                  one module per transformation family, plus induced tables
grammar/                orthography (British/American), realise (surface repair)
eval/                   sari, harness, grammatical: the gate every rule has to pass
experiments/            registry, cases, compare, report: method-versus-method comparison
cli/                    argparse dispatch, menu, install, ui, progress
docs/                   typology, approaches, constraints, good, method
input/ output/ data/    working folders (gitignored)
```

## Setup

Requires Python 3.10 or later, and a sibling checkout of `kopi-editor` and `kopi-learner`
for the rule tables and the edit corpus.

```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -c "import nltk; nltk.download('wordnet')"
python manage.py install      # checks packages, models, and the corpus link
python manage.py              # launch the interactive menu
```

`install` is idempotent and safe to re-run. It provisions nothing and asks for nothing; it
only reports what is missing and the command that fixes it.

## Commands

Running `python manage.py` with no arguments opens the interactive menu; every action is
also a direct subcommand.

| Action | Command |
|---|---|
| Lint a document and write the edited text | `manage.py lint <file.md> [--band {clarity\|light\|firm\|aggressive}]` |
| Ask whether Opus performs a transformation at all | `manage.py probe <generator> [-n N]` |
| Compare every method for one family | `manage.py experiment <family> [-n N]` |
| Compare scoring functions for which phrase to drop first | `manage.py rank [-n N]` |
| Score the linter against Opus on the gold corpus | `manage.py evaluate [-n N] [--show]` |
| Mine the gold edit corpus into a transformation report | `manage.py evidence [--role {opus\|qwen\|all}] [-n N]` |
| Rebuild rule tables from the gold corpus | `manage.py induce [--family {support-verb\|adjunct}] [--minimum N]` |
| Check dependencies, models, and the corpus link | `manage.py install` |

**`probe` comes first, before anything is built.** Point any candidate generator at the gold
corpus and it reports what Opus did there: `attested`, `declined`, or `rewritten or
dropped`. Only the first two are decidable and only their ratio means anything. This exists
because linguistic validity turned out not to predict attestation at all: reducing `which
revolve around time` to `revolving around time` is textbook whiz-deletion described in every
grammar of English, and Opus declines it 169 times to 1. Building it would have added 647
instances of reach at an accuracy that *subtracts* closure, while looking like the project's
biggest advance in any coverage-based measure.

`experiment` is the one to reach for once a family survives the probe: it runs every
registered method for a family against the same licence cases and the same corpus, and
writes a comparison. A method with no alternative to be compared against has been measured,
not evaluated.

`--role opus` measures the gold standard, `--role qwen` measures the cheap served model on
the same paragraphs, and the difference between the two reports is the editorial judgement
the linter has to supply. `-n` truncates the run for a quick pass; a full pass over the
1,523 gold edits takes about two minutes.

## How the evidence layer works

A copy-edit is monotone: sentences are tightened, absorbed, split and dropped, but almost
never reordered. That makes the sentence alignment used for parallel corpora (Gale and
Church, 1993) directly applicable, with the beads relabelled for editing rather than
translation. `evidence/align.py` runs a dynamic program over the monotone grid to recover
the cheapest sequence of 1-1 rewrites, 1-n splits, n-1 merges and 1-0 deletions, scoring
candidate beads by IDF-weighted content-lemma containment, the same measure kopi-editor's
redundancy scan uses. Inside each bead, a token-level diff yields the minimal edit script.

One correction matters enough to record. A monotone aligner cannot tell "two sentences
became one" from "one sentence was cut and its neighbour kept", since both are n-to-1
beads, and left alone it reports every drop as a merge. `_split_out_deletions` promotes a
source sentence to its own deletion when its content lemmas fail to survive into the
target, which on a 400-edit probe reclassified 23% of merge-bead sources.

`evidence/taxonomy.py` then classifies each span through an ordered cascade of structural
detectors: dependency relations, WordNet derivational morphology, word frequency, and a
concreteness test for dead metaphor. The order matters, so that "participants were given an
alias" becoming "we gave each participant an alias" is recorded as one voice change rather
than three unrelated word swaps.

Coverage against kopi-editor's 165 production rules is computed alongside, which is how the
project knows what it is adding rather than repeating.

## How the engine works

Six stages, and the order is the design: **parse, propose, select, apply, realise, guard.**

Rules only ever *propose*. They read the parse and return spans they would change, with a
confidence and the taxonomy family they belong to; nothing is applied until every proposal
has been seen. That is what makes the output independent of the order rules were
registered in, which is the difference between a linter that is deterministic and one that
merely looks it.

Selection is the interesting stage, because proposals conflict: two rules will claim the
same words. Choosing the best set of non-overlapping spans is weighted interval scheduling,
which has an exact dynamic program rather than needing a greedy heuristic, so `lint/select.py`
sorts by end offset and finds each proposal's predecessor by binary search. The word budget
is applied afterwards, dropping the weakest edits until the band's floor is respected.

Bands are per-family confidence thresholds over one rule set, not four rule sets, because
that is what the evidence says intensity is: every band draws on the same families in
different proportions. A band raises the bar rather than closing a door.

`grammar/realise.py` then repairs the surface: articles, doubled spaces and commas,
capitalisation. It is deliberately unaware of which rule fired, so it can fix damage from a
combination of edits no single rule anticipated, but it is **scoped to the joins the edits
created**. A paragraph nothing fired on comes back byte-identical. That scoping is not a
detail: repairing whole paragraphs made the pass responsible for every sentence in the
corpus rather than for the joins it made, and both of its observed corruptions happened in
paragraphs where no rule had fired at all.

Finally the guard checks the invariants (citations, numbers, the band ceiling) and, on
failure, returns the paragraph untouched. A failed lint is always a no-op, never a partial
edit. The guard is necessary and far from sufficient: it passed a sentence that had lost
its main predicate, and [docs/constraints.md](docs/constraints.md) section C4 records why
output-side grammaticality checking turned out not to be reachable.

## Results

One number tracks progress: **closure**, the per cent of the word-level distance from the
original text to Opus's edit that has been closed. Doing nothing scores 0, reproducing
Opus scores 100%, and an edit Opus did not make scores below 0. Over all 1,523 gold
paragraphs, against Opus's edit of the same paragraph at the same band:

| System | closure | reach | accuracy |
|---|---:|---:|---:|
| do nothing | 0.0% | 0.0% | n/a |
| **kopi-linter** | **0.3%** | 0.7% | 76.1% |
| served Qwen3-32B | -9.5% | 135.9% | 46.5% |

`reach` is how much of Opus's work was attempted, `accuracy` how much of that landed, and
`closure = reach x (2 x accuracy - 1)` exactly. At 50% accuracy closure is zero however much
is attempted. The linter's licence mechanism works and is applied to almost nothing;
reach is the whole problem. See [docs/plan.md](docs/plan.md) for what each family is worth.

> Closure measures agreement with Opus, not quality. Qwen at -9.5% has not written worse
> English, it has written different English, and it is quoted here as a reference point
> rather than a verdict. Reconstructing Opus is this project's objective, not Qwen's.

Corpus SARI is kept as a diagnostic, because its three components separate in a way the
composite does not:

| System | SARI | add | keep | delete |
|---|---:|---:|---:|---:|
| do nothing | 0.2439 | 0.0000 | 0.7316 | 0.0000 |
| kopi-linter | 0.5208 | 0.0018 | 0.7324 | 0.8280 |
| served Qwen3-32B | 0.5125 | 0.2040 | 0.7111 | 0.6224 |

That table says the linter beats a 32B model, which is why it is not the headline. The
score is delete precision earned on 154 changed paragraphs out of 1,523 and 349 words moved
against Opus's 23,047, and precision over few deletions is easy. The `add` column, 0.0018
against Qwen's 0.2040, is where the gap lives: the linter barely writes new words, because
every rule it has deletes.

The two metrics have already disagreed once, usefully. The relative-clause extension of
2026-07-26 moved closure up (0.2% to 0.3%) and SARI **down** (0.5250 to 0.5208), because
SARI's delete component is precision-only by design and penalises doing more work at
slightly lower precision even when that work is net-correct. For "how close are we to
Opus", closure is right by construction.

**What is nonetheless real.** Scoping the repair layer to edit joins (constraints C6) moved
SARI from 0.4580 to 0.5250 and delete precision from 0.6408 to 0.8415, purely by making the
linter stop touching text no rule had asked to change. Doing less was worth more than any
rule so far.

**What the harness has already decided.** `support-verb` was withdrawn after firing twice
and disagreeing twice. The relative-clause gates were ablated: the it-cleft gate is worth
+0.0020 SARI and one point of precision ceiling, the subject-relativiser gate is worth
**nothing at all** and its docstring claim is wrong, and the copula gate is a genuine trade,
buying 16 points of ceiling at the cost of half the coverage.

An earlier version of this section reported 100% rule agreement. That figure was an
artefact: the check compared content lemmas, the rule deletes only function words, so the
comparison set was always empty and the check could only return "agrees". The corrected
figure is a ceiling of 89%.

Coverage, not precision, is the open problem. See
[docs/constraints.md](docs/constraints.md) for why, and what it would take.

## Caveats

- Every count is a measurement of one teacher (Opus) on one author's corpus of 25
  documents in one discipline. It describes this editing task well and should not be read
  as a general account of academic prose.
- Alignment and classification are heuristic. The bead alignment is exact given its cost
  model, but the cost model is a choice; the span classifier is a cascade of detectors with
  no held-out accuracy figure yet. Treat the family shares as well-founded estimates.
- Rule agreement is scored against a single reference. An edit Opus did not make is not
  necessarily wrong, only unattested, so agreement is a floor on precision rather than a
  measure of correctness.
- `lint` reads `.md` and `.txt` only. Ingesting `.docx` is kopi-editor's job for now.
