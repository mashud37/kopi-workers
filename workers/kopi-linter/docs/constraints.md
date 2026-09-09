# Constraints

`typology.md` says what has to be solved, derived from the corpus before anything was built.
`approaches.md` catalogues techniques, also written before anything was built. This document is
the third kind: **the constraints that only became visible by building the engine and running
it against real prose.** They are not restatements of the typology. Each one is a limit on the
approach itself, established by a measurement, and each blocks something specific.

Measured 2026-07-26 on 18 real body paragraphs (reference lists excluded), and on the full
gold corpus where stated. Corpus figures written before **C14** refer to a corpus that
double-counted 33 paragraphs and read as 1,523 slots; it holds 1,490, and C14 restates every
headline that changed. The counts left in place below are what those runs actually saw.

| | Original | Opus | Qwen | Linter |
|---|---:|---:|---:|---:|
| words | 2,262 | 1,934 | 1,768 | 2,246 |
| reduction | | **14.5%** | 21.8% | **0.7%** |

Opus removes 328 words across those paragraphs. The linter removes 16, and roughly half of its
changed paragraphs were changed by surface repair rather than by any rule.

---

## C1. The engine can only delete

**Evidence.** Corpus SARI `add` is 0.0015 against Qwen's 0.2040. Every rule ever registered
proposes `replacement=""`. The `Edit` type supports a replacement string; nothing produces one.

**Why it is a constraint.** Deletion and generation are different machines. Writing a word
requires choosing a lemma, inflecting it to agree with a context that the edit itself is
changing, and placing it. None of that infrastructure exists, so the families that carry the
work in every real example (voice restoration, nominalisation, sentence merge, lexical
substitution) are not merely unbuilt, they are unbuildable in the current architecture.

**How far deletion alone can go. Corrected 2026-07-26: 68.9%, not 46%.** The original figure
classified whole families as deletion-reachable or not, by their dominant subtype. Measured
instead per finding, by whether the target span is empty, the answer is much higher, because
several families I had written off as generation are overwhelmingly deletion:

| Family | Dropped | Rewritten | Deletion share | Drop decisions | Words per decision |
|---|---:|---:|---:|---:|---:|
| `sentence` | 8,212 | 0 | 100% | 454 | 18.1 |
| `adjunct` | 5,572 | 729 | 88% | 1,699 | 3.3 |
| `clause` | 2,957 | 208 | 93% | 713 | 4.1 |
| `realisation` | 2,032 | 228 | 90% | 1,556 | 1.3 |
| `voice` | 1,863 | 1,125 | 62% | 453 | 4.1 |
| `phrase` | 1,192 | 5,889 | 17% | 417 | 2.9 |
| `relative-clause` | 996 | 42 | 96% | 182 | 5.5 |
| `stance` | 846 | 23 | 97% | 602 | 1.4 |
| `lexical` | 814 | 41 | 95% | 771 | 1.1 |
| `modifier` | 572 | 25 | 96% | 434 | 1.3 |
| `support-verb` | 0 | 2,580 | 0% | 0 | |
| `nominalisation` | 0 | 330 | 0% | 0 | |
| **Total** | **25,662** | **11,571** | **68.9%** | | |

`clause` at 93% and `voice` at 62% are the corrections that matter: both were counted as
generation families and both are mostly Opus cutting rather than rewriting. Only `phrase`,
`support-verb` and `nominalisation` genuinely require words to be written.

So a purely deleting linter tops out near **seven tenths** of Opus's word reduction, not half,
and only if every one of those families is built and licensed perfectly. A generation spine is
still not optional, but it is further deferrable than this document claimed.

**The second column of that table matters as much as the first.** Words per decision ranges from
18.1 (`sentence`) to 1.1 (`lexical`). Every decision is a licence risk and every licence risk is
paid for in accuracy, so for an engine whose binding constraint is precision, the families worth
building first are the ones that move the most words per decision taken. `sentence` moves 5.5x
more per decision than `adjunct`, the family this project has spent most of its cycles on.

**Strategy.** Defer generation, but stop pretending it is a family. Build it once as shared
infrastructure: `lemminflect` for inflection, the parse for agreement features, and a
surface-realisation step that takes a target lemma plus a syntactic slot and returns the correct
form. Then voice, nominalisation, connective and lexical all become licence problems rather than
engineering problems.

**Experiments.**
1. *Feasibility floor.* Build the deletion ceiling into the harness as a reference line, so any
   deletion family's contribution is reported against what deletion can ever achieve. **Convert
   the units carefully.** 68.9% is a share of *words moved*; closure is denominated in *edit
   operations*, of which the corpus holds 52,043. Deleting a word costs one operation, so the
   25,662 droppable words are 49.3% of the gap, and that is the reach ceiling for a
   deletion-only engine: **49.3 closure points at perfect accuracy, 26.2 at today's 76.6%, 39.4
   at 90%.** The linter's own run confirms the conversion, having spent 350 operations to remove
   347 words.
2. *Generation spine, tested in isolation.* Given a gold (source lemma, target lemma, slot)
   triple mined from the `derivational-swap` and `morphology` families, how often does the
   realiser produce Opus's exact surface form? A spine that scores below about 95% here will
   poison every family built on it, and this is measurable before any rule exists.

---

## C2. Coverage is bounded at proposal, not at selection

**Evidence.** 12.4% of paragraphs changed. The selection stage is an exact weighted-interval-
scheduling DP; in a run where the median paragraph receives zero or one proposal, it never has a
conflict to resolve.

**Why it is a constraint.** Effort has gone into the parts of the pipeline that arbitrate between
proposals, and those parts are correct and idle. The band system, the confidence thresholds and
the interval DP are all downstream of a bottleneck none of them can widen.

**Strategy.** Freeze the selection and band machinery. Judge every future increment by proposals
generated per paragraph, not by how well they are arbitrated.

**Experiment.** Report proposals-per-paragraph as a first-class number in every comparison, next
to edits applied. A method that proposes plenty and loses at selection is a different problem
from one that proposes nothing, and the current reports cannot tell them apart.

---

## C3. Every licence condition so far was found by breaking something

**Evidence.** The relative-clause rule's five gates each entered after damage: subject
relativiser, copula-only span, adjective complement, and most recently the it-cleft block, which
was found by reading output rather than by any test. The withdrawn support-verb rule reversed
the meaning of two sentences before its modifier gate existed.

**Why it is a constraint.** This is the method that failed in every previous deterministic
attempt in this workspace, and it does not scale. There are eight families left. Finding their
licence conditions by shipping them and reading the damage is both slow and, at 1,523 paragraphs
per pass, unreliable: the it-cleft appeared twice in the sample I happened to read.

**Strategy.** Induce licences from the corpus instead of asserting them. The `induce` command
already does this for one family, and the generalisation is straightforward: for a candidate
transformation, enumerate every site in the *originals* where it could apply, check whether Opus
applied it, and estimate a drop rate conditioned on syntactic context. A rule then fires where
the gold's own behaviour says it is safe, and the contexts with a near-zero rate become the
negative cases automatically rather than after a defect.

**First result, from the ablation** (5 variants of the relative rule, 400 gold paragraphs, one
command). Two things the harness established that reading code could not.

*The cleft gate did not work, and only the harness knew.* It passed review, it was documented,
and it failed its own test case on the first run: a relative clause attaches to the nearest
eligible noun, not to the cleft focus, so in the sentence that motivated the gate the clause
hangs off `power` while the focus is `kinds` five hops higher. Checking the immediate head found
nothing. Fixed by walking nominal-internal relations up to the first clause boundary; the rule
now passes 11 of 11 cases, and each ablation fails exactly the cases its own gate protects.

*One gate is doing nothing.* `no-subject-gate` scores identically to `all-gates` on every
measure: same SARI, same firings, same case results. The subject-relativiser condition, which the
module docstring calls the thing that makes the rule safe, is fully redundant with the other
gates on this corpus. It stays for now, but the claim in the docstring is wrong and this is
exactly what ablation is for.

*The copula gate is a real trade, not a free win.* Removing it doubles firing (58 against 29) and
nearly triples words removed (153 against 58), at the cost of 19 points of attestation ceiling
and 3 case failures. Given C1's finding that coverage is the binding constraint, "the safest
variant wins" is not obviously right, and the trade should be re-examined once a damage set
exists to price the errors properly.

**Experiments.**
1. *Negative-case mining.* For the relative-clause rule as it stands, enumerate all sites where
   it fires and Opus kept the clause intact. It fired 121 times; Opus kept the span verbatim in
   at least 14. Those 14 are unexamined and are the cheapest available source of gate number six.
2. *Licence model comparison,* on `adjunct` as the test family: a hand-written
   argument-versus-adjunct rule, versus a syntactic-frame table keyed on (governor lemma,
   preposition, dependency label), versus a feature-based drop-rate model. Same cases, same
   corpus, one command. This is the experiment that decides whether induction beats authoring,
   and it should be run before any more rules are authored.

---

## C4. The guard checks invariants, not grammaticality

**Evidence.** `It is X ... power key to my thesis` passed all four guard checks: citations
intact, numbers intact, length above the band floor, output non-empty.

**Why it is a constraint.** The guard is the only thing between a bad proposal and the user, and
it is blind to the failure mode that matters most for a structural rewriter. Truth preservation
does not imply well-formedness, and every deletion rule risks well-formedness specifically.

**Strategy attempted.** A differential parse-defect check: count syntactic defects before and
after, flag only what the edit introduced. Written as `eval/grammatical.py`.

**Result: the strategy failed, twice, and the failure generalises.** Recorded here rather than
patched away, because it changes what output-side validation can be asked to do.

*Attempt 1, absolute defect detectors* (no root predicate, dangling preposition, orphan
predicate, stranded auxiliary). Run against the it-cleft: **zero defects before, zero after.**
Run against four more known-bad outputs including "The theory central has been widely discussed":
**zero in every case.** The detectors are structurally incapable of firing, because a statistical
parser always returns a well-formed tree. It never leaves a preposition dangling; it reinterprets
until the tree is valid. In the cleft output spaCy re-reads `power key` as a compound noun, so
the damaged sentence parses cleanly. This is a check that cannot fail, which `good.md` section 7
forbids and which I wrote one document after writing that rule.

*Attempt 2, parse re-analysis.* If the parser normalises the damage away, the normalisation
itself should be the signal: count content tokens outside the edited span whose attachment
changed. Probed on 7 cases (3 known-bad, 4 known-good):

| Case | Tokens re-analysed |
|---|---:|
| BAD it-cleft | 5 |
| BAD bare adjective | 1 |
| BAD modal lost | 1 |
| GOOD past participle | 1 |
| GOOD present participle | 1 |
| GOOD prepositional | 3 |
| GOOD adjective with complement | 4 |

**No separation.** A good edit re-analyses as much as a bad one, because a correct whiz-deletion
*is* a re-analysis: `relcl` becomes `acl` by design. There may be signal in *which* relabelings
occur (`relcl` to `acl` is expected; a content noun demoted to `compound` is not), but 7 cases
cannot establish that and the probe's token matching is broken on repeated words. Not built on.

**What this means.** Output-side grammaticality validation is much weaker than assumed. The
parser is not an oracle for well-formedness; it is a normaliser that destroys the evidence. So:

- The guard cannot be the safety net for constituency-changing deletions. **Licence conditions
  have to carry that weight**, which raises the value of C3 and lowers the value of any further
  work on output validation.
- What might still work, in rough order of cost: a language-model surprisal check on the output
  (`approaches.md` section 2.2, needs a small n-gram model over the corpus, no GPU); a
  relabel-signature check trained on enough gold reductions to know which relabelings are normal;
  or nothing, accepting that the case bank plus induced licences is the defence.
- `eval/grammatical.py` stays in the tree, reported and near-useless, rather than being quietly
  deleted. It fires once across 1,523 paragraphs, identically for every method including ones
  that differ by 100 edits, which is the clearest possible statement of its value.

---

## C5. A single reference cannot separate "unattested" from "wrong"

**Evidence.** The agreement metric reported 100% for 121 firings. It compared content lemmas,
the rule deletes only function words, so the removed set was always empty and the test returned
`True` unconditionally. A surface test anchored on the following token finds Opus kept the span
in at least 14 of 121, so agreement is at most 88%, and that is a ceiling because when Opus
rewrote the sentence wholesale the anchor is absent and the edit passes by default.

**Why it is a constraint.** Opus spends a limited budget per paragraph and often improves one
clause while leaving an equally weak one alone. An edit Opus did not make may be correct. No
amount of care with a single reference resolves this, so precision is not measurable as
currently set up, only bounded.

**Correction, 2026-07-26.** An earlier version of this section claimed the corpus holds Sonnet,
Haiku and Qwen edits of the same paragraphs, so that a graded four-way agreement was available
free. It does not. Counted:

| Editors present for a paragraph and band | Slots |
|---|---:|
| opus + qwen | 1,333 |
| qwen only | 114 |
| opus only | 89 |
| opus + sonnet | 68 |
| haiku + qwen + sonnet (no opus) | 56 |

There is **no three-way agreement involving Opus anywhere in the corpus**. The only usable second
reference is Qwen, and Qwen is the weaker editor by the project's own measurement, so "Qwen also
made this edit" is not evidence that an edit is right. The free half of this strategy is much
thinner than claimed, and the claim should not have been written without counting first.

**Strategy, revised.** Use the second reference for **triage, not for scoring**. Three outcomes
per edit on the 1,333 slots where both editors are present:

* attested by both: very likely right, no attention needed
* attested by Opus only: unremarkable, Qwen edits differently
* **attested by neither**: two independent editors both declined to make this change

The third class is small and enriched for damage, which makes it the cheap way to *choose* what a
human looks at rather than a way to avoid looking. That turns the hand-checked damage set from a
100-paragraph random sample into a targeted one, and it is the only part of this constraint that
the corpus can actually pay for.

**A hand-checked damage set is therefore not optional.** Judged against G1 to G3 in `good.md`.
Nothing substitutes for it, and it is the only way to measure precision rather than bound it.

---

## C6. The repair layer edits text no rule touched

**Evidence.** Six of the 14 changed paragraphs I inspected had no rule fire at all. Both observed
corruptions (`U.S. politics` becoming `U.S. Politics`, and a capital inserted after an ellipsis
inside a participant quotation) occurred in paragraphs where nothing had been edited.

**Why it is a constraint.** `lint/run.py` calls `repair()` on every paragraph unconditionally, so
the realiser normalises the whole document whether or not an edit was made. Three consequences:
the coverage figure is inflated by paragraphs that were only tidied; the linter makes unrequested
changes to untouched prose; and the surface detectors have to be correct against the entire
corpus rather than against the neighbourhoods of actual edits, which is a far harder problem and
is where both bugs came from.

**Strategy.** This is the root cause, and patching the detectors treats the symptom. Repair
should be **scoped to the neighbourhood of applied edits**: when no edit was applied, the
paragraph is returned byte-identical. The detectors still matter, but they stop having to be
right about every sentence in the corpus.

**Result: resolved.** `grammar/realise.repair` now takes the spliced edit spans
(`lint.edit.spliced_spans`), widens each by one short clause, subtracts the quoted spans, and
repairs only inside what is left. Verified directly: all three observed corruption inputs return
byte-identical when no edit fired, and an edit still gets its join repaired
(`The data which were collected were coded.` still reduces cleanly). All six surface-repair cases
pass in the harness, including the two that were failing.

The widening margin (80 characters) is a choice, not a measurement. An edit's article sits one
word before it and a sentence start one clause after, so the margin covers what an edit can
disturb, but a principled version would widen to the enclosing sentence. Left as is because
sentence segmentation has the same abbreviation and ellipsis problems that caused the original
bug.

---

## C7. Restraint has no mechanism

**Evidence.** Opus returns 12.5% of sentences untouched. The linter currently achieves restraint
by having almost no rules, which is not restraint.

**Why it is a constraint.** A rule that matches fires. As coverage rises this inverts from a
non-issue into the dominant failure mode, and it is the specific way the cheap model already
fails: Qwen leaves a third fewer sentences alone than Opus and edits worse for it. The gap
kopi-linter is supposed to close is knowing when to stop.

**Strategy.** Restraint has to be a positive decision with its own evidence, not the absence of a
match. Two candidates worth comparing: a paragraph-level budget that spends the band's allowance
on the highest-yield edits and declines the rest (the interval DP already supports this, unused),
and a sentence-level quality prior that declines to edit a sentence already scoring well on the
objective.

**Experiment.** Once two families are live, compare fire-everything against budget-limited on
damage rate and SARI. Not runnable yet; recorded so it is not discovered late.

---

## C9. A per-category drop rate cannot license a deletion

**This is the C3 experiment's answer, and it is "neither".** Four licence models for `adjunct`,
400 gold paragraphs, one command:

| Method | Cases | SARI | Fired | Ceiling | Words |
|---|---|---:|---:|---:|---:|
| `adjunct/syntactic` (structural only) | 2/7 | 0.4118 | 647 | **2%** | 5,340 |
| `adjunct/frame` (induced, exact) | 3/7 | 0.5258 | 3 | 67% | 12 |
| `adjunct/backoff` (induced, backs off) | 3/7 | 0.5258 | 3 | 67% | 12 |
| `adjunct/backoff-strict` (n >= 20) | 2/7 | 0.2398 | 0 | 0% | 0 |

**Structural licensing over-fires catastrophically.** 647 firings at a 2% attestation ceiling:
Opus made a compatible change 2% of the time. It removes 5,340 words and scores *below* the
relative-clause rule while doing twenty times the damage. Attachment and phrase size carry
almost no information about whether a phrase may go.

**Induced licensing under-fires into irrelevance.** Three firings across 400 paragraphs. Not a
tuning problem: the drop rate ceiling is 0.40 at governor level and 0.238 at preposition level,
against an aggressive-band threshold of 0.60, so no category can ever clear the bar. Raising the
evidence requirement takes it to zero.

**Why, and this is the part that generalises.** A per-category drop rate is a statement about a
*class* of phrases; the engine asks it a question about *this* phrase. Roughly 90% of
prepositional phrases survive, so no conditioning on (governor, preposition) concentrates the
probability anywhere near a threshold, and no amount of extra corpus will change that. The
information that decides whether a given phrase goes is not in its lexical frame at all. It is in
whether the paragraph is being compressed, and whether this phrase is the least load-bearing one
available.

Improving the measurement helped and did not rescue it. Survival was first checked across the
whole paragraph, which reported a 4.0% base rate and 5 usable frames; rechecking inside each
sentence's own alignment bead more than doubled it to 9.7%. The right measurement was necessary
and nowhere near sufficient.

**This also explains the `support-verb` withdrawal in retrospect.** Same failure mode: a 20% base
rate used as a confidence, a threshold it could not reach, two firings. That was read at the time
as a fact about light-verb constructions. It was a fact about the architecture.

**Strategy: band as budget, not as threshold.** For deletion families the band should rank
candidates by droppability and take them until the word target is met, rather than admitting
everything above a fixed probability. `lint/select.py` already carries budget machinery that
nothing currently uses, and `bands.admits` is the wrong gate for this family.

## C10. The rate ranks even though it cannot license

**Confirmed.** Ranking is separable from the pipeline and much cheaper to evaluate: in each
paragraph the gold editor dropped some number of the phrases present, so take that number as
given, order the candidates, and ask how many of the top choices were the editor's. `manage.py
rank`, all 1,523 gold paragraphs, of which 883 both dropped and kept a phrase, 14,719 candidates.

| Scorer | precision@k | lift over random | MAP |
|---|---:|---:|---:|
| **rate + commonness** | **0.432** | **1.88x** | 0.527 |
| rate + earliness | 0.420 | 1.83x | 0.523 |
| rate | 0.415 | 1.81x | 0.517 |
| commonness | 0.332 | 1.44x | 0.422 |
| earliness | 0.323 | 1.41x | 0.424 |
| *random* | *0.230* | *1.00x* | *0.291* |
| depdist | 0.185 | 0.80x | 0.241 |
| redundancy | 0.154 | 0.67x | 0.255 |
| words | 0.144 | 0.63x | 0.193 |

The ordering is stable: an earlier pass over 250 paragraphs put the same three scorers on top in
the same order, at 1.77x, 1.62x and 1.64x.

**The induced rate is a good ranker and a useless licence.** Same statistic, same table, 1.81x
random as an ordering after C9 showed it could not clear any threshold. That settles the design:
the rate stays, the threshold goes, and the band becomes a budget.

**Three negative results worth as much as the positive one.** All three are techniques this
project had already committed to on paper.

*Redundancy is anti-predictive, at 0.67x random.* A phrase whose content words recur elsewhere in
the paragraph is markedly **less** likely to be dropped. Recurrence marks topical importance, not
redundancy. This is a direct hit on `typology.md` D1, which proposed reusing kopi-editor's
IDF-weighted overlap machinery for exactly this purpose: for phrase-level dropping it would have
actively chosen the wrong phrases. The machinery may still be right for whole-sentence dropping,
where it was originally built, but that now needs its own test rather than an assumption.

*Dependency locality does not transfer.* `depdist` scores 0.80x random, below chance. Dependency
distance minimisation is listed in `approaches.md` section 2.1 as a strong candidate for the
engine's objective function; it does not predict which adjunct a human editor removes.

*Length carries nothing.* `words` at 0.63x, the worst scorer tested. The obvious heuristic for a
word-budget product, "drop the longest", is worse than shuffling.

**What did work is the pairing of a corpus statistic with an information-theoretic one.** Neither
`rate` nor `commonness` alone reaches 1.88x; together they do, and they are the only two scorers
whose blend beats both its parts. The reading is that a drop needs the phrase to be both the kind
of phrase editors drop *and* low in information, and that the two conditions are close to
independent.

**One methodological correction, recorded because it inverted a reading.** The first run scored
`random` by calling `Random(0).random()` per candidate, which constructs a fresh generator each
time and therefore returns a constant, silently turning the random baseline into a document-order
baseline. It is now seeded once per paragraph. Separately, the reference must be the shuffle
baseline (0.221) and not the corpus drop rate (0.137): shuffling beats the corpus rate because
paragraphs with many drops contribute more picks, so a blind order gets more chances precisely
where hits are easy. Comparing against the corpus rate credits every scorer with about 0.6x of
lift it has not earned, and the first version of this table did exactly that.

## C11. Budget and licence are orthogonal, and ranking only solves one

Built: `lint/bands.RANKED_FAMILIES` marks families where the band sets a word budget instead of a
confidence threshold; those families enter selection unthresholded and the existing budget pass
in `lint/select.py` trims them best-first to the compression ceiling. The ranked adjunct rule
scores each phrase with `droppability`, the `rate + commonness` blend from C10, bounded into
[0, 1] and deliberately below the confidence a licensed rule asserts so the budget gives up a
guess before it gives up a licensed edit.

**It works as designed and it is not enough.** 300 gold paragraphs:

| Method | Cases | SARI | Fired | Ceiling | Words |
|---|---|---:|---:|---:|---:|
| adjunct/ranked | 4/7 | 0.4132 | 582 | 3% | 3,990 |
| adjunct/syntactic | 2/7 | 0.4142 | 457 | 2% | 3,715 |
| adjunct/frame | 3/7 | **0.5259** | 3 | 67% | 12 |
| adjunct/backoff | 3/7 | **0.5259** | 3 | 67% | 12 |
| adjunct/backoff-strict | 2/7 | 0.2400 | 0 | 0% | 0 |

Ranking buys the coverage it promised, 582 firings against 3, and the coverage is worthless: a 3%
attestation ceiling and a SARI *below* the models that do almost nothing. The best case score
improves from 2/7 to 4/7, so the ordering is real, and it is nowhere near a licence.

`adjunct/ranked` still drops `of three interviews` from "the sample consisted of three
interviews" and `on the perspective` from "this chapter draws on the perspective of other work",
because ranking answers *which phrase goes first* and never answers *which phrases are eligible
at all*. With the threshold removed, every structurally eligible phrase is a candidate, and an
argument that happens to score well is dropped as soon as the budget has room.

**A second cause, separable and cheap to fix.** The budget is calibrated to the band's
compression *ceiling*, which is a maximum and not a target. At firm the ceiling is 35% while the
gold editor's measured median reduction at firm is 14.3% (`typology.md` section 5), so the budget
invites a cut 2.4 times deeper than Opus makes. Even a perfect ranker would be asked to fill an
oversized quota, and would reach far down its own ordering to do it. The word target for ranked
families should be the measured median for the band, with the ceiling kept as the hard stop it
was designed to be.

Both causes have to be addressed before ranking can be judged fairly. The ordering result from
C10 stands; this run does not disconfirm it, it shows the ordering being spent badly.

So the two questions are independent, and C9's fix addresses only one:

* **licence**: may this phrase go? Still unsolved. Structural tests give a 2% agreement ceiling
  (C9); induced rates cannot threshold (C9); ranking does not attempt it.
* **budget**: how many go, and in what order? Solved, at 1.88x random (C10).

A ranked family without a licence is a better-ordered version of the wrecking ball. The next
attempt has to be an argument-versus-adjunct test that is neither a hand-written verb lexicon nor
a per-category rate, and the obvious candidate is subcategorisation evidence induced from the
corpus itself: how often does *this governor lemma* appear with *this preposition* at all,
against how often it appears without any preposition. A preposition that is nearly obligatory
after a verb is an argument, and that is a distributional question the corpus can answer.

**Three harness defects this cycle exposed, all of which had been silently passing.**

*The architecture flag was on the wrong object, and it invalidated a whole comparison.* The
ranked marker was first a set of family names in `lint/bands.py`. Since `adjunct` was in it, the
threshold models for that family were silently converted to budget models too: `adjunct/frame`
jumped from 3 firings to 459, and the comparison meant to decide between two architectures ran
both of them as one. Whether a confidence is a probability or an ordering is a property of the
*proposal*, so `ranked` now lives on :class:`lint.edit.Edit`, which is also what lets both
variants of a family be compared at all. The first version of the table in this section was
produced by the broken build and has been replaced.

*A case must be the size of the thing it tests.* The first adjunct cases were single sentences,
and every `fire` case failed: at the firm band a 13-word sentence may lose about 4 words, so an
8-word phrase could never fit the budget whatever the rule decided. They measured the band's
ceiling, not the licence. Now written as realistic paragraphs.

*A case must name the span it is about.* Without one, `refuse` meant "do not edit this paragraph
at all", so a method was failed for correctly dropping some *other* phrase, and `fire` passed
whenever a method removed anything at all. Both readings are wrong. `Case.span` now names the
text that must go, or must survive, and the runner checks that span rather than the paragraph.

*And the case runner has to match the architecture.* Threshold families are judged on what they
propose, since a proposal clearing the band asserts the edit is licensed. Ranked families are
judged on what survives the pipeline, since proposing freely is the design. Judging a ranked
family on its proposals asks it to be a threshold family and fails it for not being one.

**Still open.** Condition the rate on the band as well as the frame. The gradient is known to
exist (`typology.md` section 1.3 puts `adjunct` at 7.1% of clarity activity and 9.6% of
aggressive) and it is cheap to add to the survey.

## C12. A per-paragraph budget forces uniform cutting; the editor allocates unevenly

Both fixes from C11 were built and measured. 300 gold paragraphs, 7 methods:

| Method | Cases | SARI | Fired | Ceiling | Words | Defects |
|---|---|---:|---:|---:|---:|---:|
| adjunct/ranked (calibrated budget) | 3/7 | 0.4243 | 469 | 6% | 2,619 | 7 |
| adjunct/ranked-arg (+ argument gate) | **5/7** | 0.4227 | 430 | 5% | 2,402 | 5 |
| adjunct/ranked-arg-strict | 5/7 | 0.4191 | 420 | 3% | 2,412 | 5 |
| adjunct/syntactic | 2/7 | 0.4142 | 457 | 2% | 3,715 | 6 |
| adjunct/frame | 3/7 | **0.5259** | 3 | 67% | 12 | 0 |

**Both changes work and neither rescues the family.** The attestation ceiling doubled, 3% to 6%,
and the case score went from 2/7 to 5/7, and the ranked models still score well below threshold
models that make three edits in three hundred paragraphs. `adjunct` stays unregistered.

Attribution is clean, which is what the variants were for:

* **C11a, the calibrated budget**, fixed three of the four argument failures on its own. With a
  realistic word target the ranker never reaches far enough down its ordering to hit them. This
  was not a licence problem at all; it was an oversized quota.
* **C11b, the distributional argument gate**, fixed the fourth and cost almost nothing. Measured
  on the originals alone, `depend on` scores 1.00, `consist of` 1.00, `focus on` 0.85 and `draw
  on` 0.74, against `take during` at 0.04 and `be in` at 0.05. It is a fact about the language
  rather than about one teacher, which is the first licence in this project that should transfer
  to prose the corpus has never seen. It also cut introduced defects from 7 to 5.

**What the residual says.** The ranker is 1.88x random at ordering (C10) and reaches a 6% ceiling
in the pipeline, and that gap is the finding. Ranking was evaluated only on the 883 paragraphs of
1,523 that dropped at least one phrase and kept at least one. The pipeline runs on all of them
and spends its budget in every one, because the target is a median applied per paragraph. The
gold editor does not cut every paragraph by the median; it cuts some deeply and leaves others
alone, and a per-paragraph quota cannot express that.

This is `typology.md` D6 arriving as a measurement rather than a note, and it is C7, restraint,
surfacing exactly where C7 predicted it would. Budget allocation is a **document-level** problem:
given a requested reduction, decide which paragraphs absorb it. A uniform per-paragraph quota
guarantees the linter edits paragraphs the editor would have left untouched, and no improvement
in ranking can fix that, because the ranking is only ever asked which phrase goes first, never
whether any should go at all.

**Measured, and mostly negative.** `manage.py rank` now answers both questions from one corpus
pass. 399 paragraphs, of which 243 (60.9%) had a phrase dropped by the gold editor. Thresholds
are swept over 40 values rather than chosen, so each feature's ceiling is visible.

| Decision rule | precision | recall | F1 | fires on |
|---|---:|---:|---:|---:|
| candidates >= 9.25 (best sweep) | 0.675 | 0.938 | 0.785 | 338/399 |
| best >= 0.422 | 0.632 | 0.988 | 0.770 | 380/399 |
| *always cut* | *0.609* | *1.000* | *0.757* | *399/399* |
| **any candidate scores 0.5+** | **0.755** | 0.584 | 0.659 | 188/399 |

**By F1 there is no signal.** The best swept threshold beats cutting everything by 0.028, and
the feature that achieves it, candidate count, is paragraph length wearing a disguise: longer
paragraphs are likelier to contain at least one drop, which is close to tautological. Whether the
editor cut a paragraph is **not predictable from that paragraph's own drop candidates**.

**But F1 is the wrong summary for this decision, and reading it alone would have hidden the one
usable result.** The two errors are not symmetric: cutting a paragraph the editor left alone is
damage, while missing one is only a lost opportunity, and this project's whole position is that
precision matters more than coverage. On precision there is a real effect. Firing only where some
candidate scores 0.5 or better hits 75.5% against a 60.9% base rate, a **1.24x lift**, on 47% of
paragraphs. That is a usable rule for deciding *where* to spend, and it is invisible in the F1
column where it ranks last.

**What the negative half means.** A paragraph-local view cannot answer the allocation question,
which is `typology.md` D6 confirmed rather than assumed: it needs what the paragraph cannot see,
namely redundancy against its neighbours, the document's requested reduction, and where this
paragraph sits in the argument. Allocation is a document-level problem and has to be built as
one, not approximated per paragraph.

**Next.** Two separable pieces. Wire the high-precision gate (fire only where a strong candidate
exists) as a restraint rule and re-measure the attestation ceiling, which is cheap and uses a
result already in hand. Then treat allocation properly: given a document and a requested
reduction, choose which paragraphs absorb it, which is the first thing in this project that
cannot be decided one paragraph at a time.

## C8. The irreducible core, restated with the build's evidence

`typology.md` puts free paraphrase at 14.3% of transformations and calls it the honest problem.
Nothing in the build changed that estimate, but C1 sharpens what surrounds it: the reachable
portion is smaller than the typology implies, because reaching it needs a generation spine that
does not exist. The ordering is therefore generation spine, then licences, then paraphrase, and
paraphrase stays last.

---

## C13. Linguistic validity does not predict attestation

**Evidence.** Two extensions to the relative-clause rule were diagnosed by walking all 2,719
relative clauses in the corpus originals and attributing each refusal to the gate that caused
it. Both are textbook whiz-deletion. Their attestation could not be more different
(`manage.py probe`, counting only candidates whose treatment in the gold is decidable):

| Generator | Candidates | attested | declined | rate | Verdict |
|---|---:|---:|---:|---:|---|
| `relative/all-gates`, the shipped rule | 186 | 16 | 23 | **41.0%** | built |
| `relative/lexical-probe`, `which revolve` to `revolving` | 647 | 1 | 169 | **0.6%** | **refused** |

The second is the larger opportunity by a factor of three and a half, is described in every
grammar of English, and Opus declines it 169 times to 1.

**Anchor the probe on the left, or it lies.** The first version of this measurement did not, and
reported the shipped rule at 15 of 15 with no counterexamples. The reduced form is usually a
*suffix* of the original, so a gold that kept "that is socially organised" contains "socially
organised" and scored as attested for a reduction it never made. Prefixing three words of
untouched context makes the two readings mutually exclusive. The corrected figure is 41%, and the
lesson is the one this document keeps relearning: a test that cannot return "declined" is not a
test, and it will always agree with whatever is under it.

**Three numbers, one rule, all correct.** The shipped rule reads 86% on the harness attestation
ceiling, 76.1% on closure accuracy and 41% on the probe. They measure different things and the
spread is informative rather than contradictory: the ceiling counts the 147 paragraphs Opus
rewrote wholesale as attested by default, closure counts them as progress because a small
deletion inside a larger one does move the text toward the gold, and the probe refuses to count
them at all. Use the probe to decide whether to build, closure to decide whether it worked.

**Why it is a constraint.** A rule's licence cannot be argued from grammar. "This transformation
is valid English" and "this editor performs this transformation" are independent claims, and only
the second one predicts closure. Building the lexical-verb reduction would have added 647
instances of reach at roughly 1% accuracy; by the closure identity that multiplies to `2(0.01) -
1 = -0.98`, so it is very nearly pure damage. In any coverage-based measure it would have looked
like the single biggest advance the project had made.

**What this retro-explains.** The withdrawn support-verb family and the unregistered adjunct
family were both argued from linguistic soundness first and measured second. The order has to be
the other way round, and it is cheap: an attestation probe over the gold corpus costs one parse
pass and answers the question before any rule is written.

**Strategy.** No family is built before an attestation probe on the construction it targets. The
probe is the same shape every time: find the construction in the originals, apply the intended
transformation, and ask whether the gold contains the result, the original, or neither. Report
the ratio among decidable cases, since "dropped or rewritten" is the majority class everywhere
and tells you nothing.

**Experiments.**
1. ~~*Probe before build, as a subcommand.*~~ Built: `manage.py probe <generator>`, over any
   `doc -> Edits` callable including deliberately loose ones with no licence at all. Looseness is
   the point, since the question is asked before the licence exists. The refused lexical-verb
   generator is kept in `rules/probe_lexical_relative.py` and registered under its own family so
   no experiment picks it up, which keeps this finding reproducible.
2. *Retro-probe the queue.* Run it over the families in `plan.md` section 3 before any of them is
   scheduled, and expect at least one more to die the way the lexical-verb reduction did.
3. *Calibrate the probe against closure.* The 41%/76.1% spread is explained above but not
   measured. Probing a generator and then shipping it gives both numbers on the same edits, and
   two or three such pairs would say what probe rate predicts positive marginal closure. Until
   then, 20% is a guess dressed as a threshold.

---

## C14. The corpus was 1,490 slots, not 1,523, and none of it was held out

**Evidence.** `evidence/load.load_samples` documented deduplication on
`(key, role, band)` and implemented it on `(key, role, band, edit[:80])`. Counted over the
files themselves:

| | rows |
|---|---:|
| raw rows across `data/pairs/*.jsonl` and `data/out/test.jsonl` | 3,533 |
| distinct `(key, role, band)` | 3,173 |
| distinct as the code actually keyed them | 3,227 |
| **gold slots, documented key** | **1,490** |
| **gold rows, as loaded** | **1,523** |

33 paragraphs were re-edited at the same band and entered twice, carrying double weight in
every family count and in the pooled closure denominator. This document already contained
the right number and nobody noticed: C5's own table sums to 1,333 + 89 + 68 = **1,490**.

Separately, all 235 rows of kopi-learner's held-out `data/out/test.jsonl` are already present
in `data/pairs`, so pooling the two dissolved the split rather than extending it. `induce`
fitted the drop-rate tables in `rules/induced_*.py` on the whole corpus and `evaluate` scored
on the same corpus, which is why `adjunct/frame`'s 67% ceiling was read off its own training
data.

**Why it is a constraint.** Nothing fitted to this corpus could be measured, and the failure
was invisible because the only fitted things so far were rejected anyway. It becomes fatal
the moment a classifier or a tagger exists.

**Resolved.** The fingerprint matches its docstring. `load_samples(split=...)` holds out
every fifth document by name: 20 documents and 1,257 slots to train, 5 documents and 233
slots to test. The split is by **document** and never by paragraph, because paragraphs from
one document share an author, a topic and a vocabulary, and splitting inside a document puts
near-copies of the training data into the test set. No paragraph text is shared between two
document names, checked directly, so the split separates what it claims to.

`induce` and `probe` now read `train` only, so a build decision never spends the held-out
documents. `evaluate` runs over everything and reports both sides.

**Restated numbers**, all previously quoted against the double-counted corpus:

| | before | after |
|---|---:|---:|
| gold paragraphs | 1,523 | **1,490** |
| sentence beads | 7,355 | 7,225 |
| span transformations | 22,631 | 22,279 |
| words moved | 37,622 | 37,233 |
| edit operations (closure denominator) | 52,749 | 52,043 |
| words Opus removes | 23,047 | 22,816 |
| closure | 0.3% | **0.4%** |
| accuracy | 76.1% | 76.6% |
| corpus SARI, linter | 0.5208 | 0.5218 |
| corpus SARI, do-nothing | 0.2439 | 0.2433 |

Every conclusion in this document survives the correction. The family shares move in the
third significant figure and none of the orderings change, which is worth stating because it
would have been just as easy for them not to.

**One calibration constant was genuinely wrong, and only this correction exposed it.** All 33
duplicates sat in the `light` band, which therefore held 101 paragraphs where it holds 68, a
third of it counted twice. Re-measuring the median cut per band:

| Band | Paragraphs | Median cut, before | after |
|---|---:|---:|---:|
| clarity | 454 | 0.057 | 0.057 |
| **light** | **68** | **0.034** | **0.018** |
| firm | 528 | 0.142 | 0.142 |
| aggressive | 440 | 0.191 | 0.191 |

`lint/bands._TARGET["light"]` was set to 0.034, so a ranked family at the light band was
asked to cut about twice as deep as the gold editor does. Three bands were unaffected and
the one that was is the smallest, which is why nothing downstream had caught it. Corrected
to 0.018. This is the C11a error a second time and from a different cause: a budget is only
as good as the measurement behind it.

**The one new result, and it is a null.** Closure now reports each side of the split:

| Split | Paragraphs | Edits applied | Gap | Work | Closure | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| train | 1,257 | 149 | 44,592 | 320 | 0.39% | 77.3% |
| test (held out) | 233 | 14 | 7,451 | 30 | 0.15% | 68.3% |

The nine-point accuracy drop is **not reportable**. It rests on 14 edits and 30 word
operations, and at that size a true rate of 77% produces a reading of 68% routinely. The
finding is the sample size itself: **at current reach the held-out split cannot referee
anything.** A rule firing on 6% of paragraphs leaves too few held-out edits to separate two
methods, so a single train/test split is the right structure for reporting and the wrong one
for comparison.

**Strategy.** Keep the split for reporting. For method comparison use k-fold over the 25
documents, which costs one extra corpus pass per fold and puts every paragraph in a held-out
position exactly once. Until that exists, no learned method should be admitted on a held-out
number, because there is not enough held-out signal to admit it with.

---

## C15. A closed edit vocabulary writes most of what Opus writes; plain code writes none of it

**Evidence.** `manage.py execute` hands a backend one span the gold editor changed, four words
of context each side, and the name of the change made there, and asks for the replacement. The
site is a gift and the wording is not, which separates *can a local executor perform this
transformation* from *can it decide where*. Nothing in the repo had asked those two questions
apart before. 20,243 spans from 1,490 paragraphs: 13,316 rewriting (replace or insert) and
6,927 deletions.

Span closure is the master metric read at span level, so the two anchors are the two things the
engine can already do:

| Backend | Answered | Exact | Span closure | Rewriting closure | Rewriting exact |
|---|---:|---:|---:|---:|---:|
| `keep`, the zero of the scale | 100% | 0.0% | 0.0% | 0.0% | 0.0% |
| `delete`, drop the span | 100% | 34.2% | 50.1% | 28.8% | 0.0% |
| `template`, plain code | 35% | 34.6% | 30.0% | **0.2%** | 0.5% |
| `tagger-ceiling`, a closed vocabulary | 100% | 76.7% | 66.8% | **52.6%** | 64.6% |

Two readings, and they point opposite ways.

**Plain code is done.** The `template` backend drops a span and respells one, which is
everything a rule layer can justify without knowing what an editor would have written. On the
rewriting spans it closes **0.2%**, against 28.8% for deleting the span blind. C1 said the
engine can only delete; this is the same finding at span level and with the ceiling attached,
and it settles that no further work on hand-written realisation is worth doing.

**A tiny induced vocabulary is not.** `tagger-ceiling` holds **970 phrases**, every stretch of
words written twice or more in the training documents, plus the inflection changes a tagger
generates rather than looks up. With perfect tag choice that vocabulary reproduces Opus exactly
on 64.6% of rewriting spans and closes 52.6% of the rewriting gap. It reads the gold and is a
ceiling, not a system score, but it is the ceiling that decides whether the tagger is worth
building, and it is nearly twice the delete anchor.

**It transfers.** The vocabulary is counted on training documents only and scored on both sides:

| Backend | Train closure | Held-out closure | Held-out spans |
|---|---:|---:|---:|
| `delete` | 50.0% | 50.8% | 2,916 |
| `tagger-ceiling` | 67.0% | 65.1% | 2,916 |

A two-point gap on **2,916 held-out spans**, which is the first held-out measurement in this
project with enough behind it to mean anything. C14's held-out closure rests on 14 edits; this
rests on two thousand nine hundred. Span-level measurement is what makes the corpus big enough
to referee, and that is a structural finding, not an incidental one.

**The residual is one family.** Per family, over rewriting spans only:

| Family | Spans | Share of gap | `delete` | `tagger-ceiling` | Share of residual |
|---|---:|---:|---:|---:|---:|
| phrase | 5,537 | 62.1% | 23.9% | **35.4%** | **84.7%** |
| support-verb | 1,194 | 9.6% | 67.3% | 91.9% | 1.6% |
| voice | 703 | 7.5% | 37.4% | 50.5% | 7.8% |
| realisation | 2,240 | 6.6% | 8.6% | 93.7% | 0.9% |
| lexical | 2,063 | 5.4% | 1.9% | 82.0% | 2.0% |
| adjunct | 234 | 2.5% | 73.0% | 93.9% | 0.3% |
| connective | 719 | 2.2% | 11.1% | 90.1% | 0.5% |
| nominalisation | 173 | 1.7% | 48.5% | 55.1% | 1.6% |
| morphology | 309 | 0.8% | 0.6% | 96.8% | 0.1% |

Everything a closed vocabulary can be expected to hold, it holds: connectives at 90.1% against
11.1% for deleting them, morphology at 96.8% against 0.6%, lexical swaps at 82.0% against 1.9%.
These are the families where deletion is not merely worse but useless, and they are exactly the
families a tag vocabulary is shaped for.

**84.7% of everything a perfect tagger cannot reach is `phrase`**, and `phrase` plus `voice` is
92.5% of it. That is the head-changing paraphrase core `typology.md` has been naming since the
first pass, now sized against a method rather than against nothing. It is the argument for a
decoder and the argument against reaching for one before the tagger exists: eight rewriting
spans in ten are not paraphrase.

**A metric this probe had to fix in flight.** The bar was named beforehand as 40% exact-or-near
match, near meaning within one word of Opus. Doing nothing scores **39.1%** on it, because a
one-word replacement is by definition one word from its own source. That is a metric nobody can
fail, which is the defect this project has shipped before, and it was caught by the `keep`
anchor rather than by inspection. Near match is dropped. The 40% is applied to exact match, and
a second gate is added that a do-nothing also cannot pass: a rewriting backend has to close more
of the span gap than blindly deleting the span does.

**Two numbers that must not be confused.** Span-level gap sums 57,220 operations against the
paragraph-level closure denominator of 52,043. They differ because span distances are summed per
segment and do not cancel across a paragraph. Span closure orders methods for one transformation;
paragraph closure is still the number the project is scored on.

**Not measured.** The `decoder` backend is written and unexercised: no Ollama is installed on
this machine, so it reports unavailable and refuses every task. Its row is therefore absent
rather than zero, and the paraphrase residual has an argued size and no measured executor.

**Why it is a constraint.** The generation spine was deferred through this whole document on the
grounds that deletion still had room. That was right about the ordering and wrong about the
difficulty: the part of generation that is a closed vocabulary is 970 entries and reaches half
the rewriting gap, and the part that needs a model is one family. Those are different projects
and were being treated as one.

**Strategy.** Build the tagger next, not the decoder. It is CPU-feasible, it cannot write
outside an inspectable vocabulary so G8 holds by construction, and its per-token threshold is
the band dial that replaces the hand-set numbers in `lint/bands._THRESHOLDS`. The decoder is
scoped to `phrase` and `voice` and does not start until the tagger's real (not oracle) score
exists, because the residual is only worth a model if the tagger has already taken the rest.

**Experiments.**
1. ~~*Oracle-execution probe before building any of it.*~~ Built: `manage.py execute`, with
   `keep` and `delete` as anchors and `--reproduce` for the determinism check.
2. *Measure the decoder.* Install Ollama, pull one small instruct model, run
   `manage.py execute --backend decoder --family phrase -n 200`. The question is narrow: on the
   one family a vocabulary cannot hold, does a 4B model at a gold site beat 35.4%?
3. *Sweep the vocabulary threshold.* 970 phrases is one setting of "written at least twice".
   The curve from 1 to 10 sightings says how much of the ceiling is memorisation of the training
   documents and how much is a genuinely closed set, and the held-out column already says the
   answer is mostly the latter.
4. *Split the `phrase` residual.* 84.7% of the residual in one bucket is a classification
   failure as much as a linguistic fact. `phrase` currently absorbs reordering, compression and
   full rewrite alike, and the three have different executors.

---

## C16. The licence is learnable per token, and the wall was the feature set

**Evidence.** `manage.py tag` reads the corpus as an edit-tagging problem. Every source word gets
one tag: keep it or delete it, plus an optional phrase to write before it. That one scheme
expresses deletion, sentence dropping, lexical swap, connective repair and sentence merge, which
is why it is worth measuring before anything is fitted to it. **205,800 words tagged over 1,490
paragraphs, 0 paragraphs unalignable.**

| Tag | Share, train | Share, held out |
|---|---:|---:|
| `KEEP` | 73.5% | 74.7% |
| `DELETE` | 26.5% | 25.2% |
| carries a phrase | 7.2% | 6.3% |

**Deletion is a quarter of every paragraph, not a rare event.** The problem this project has
called intractable is a 74/26 binary classification with 174,231 training examples. Nothing in
C9 to C12 said that, because none of them looked at a token.

**A plain logistic regression breaks the wall.** 17 parse and frequency features, 6,136 columns
after one-hot encoding, fitted on the training documents and scored on 31,464 held-out words.
No embeddings, no tuning. This is the learned linear baseline `approaches.md` 2.5 has called
standard since the first pass and nobody had built:

| Threshold | Words fired on | Precision | Recall | Projected closure |
|---:|---:|---:|---:|---:|
| 0.50 | 2,716 | 55.4% | 19.0% | 3.9% |
| **0.60** | **1,118** | **64.9%** | **9.1%** | **4.5%** |
| 0.70 | 446 | 74.9% | 4.2% | 3.0% |
| 0.80 | 165 | 87.3% | 1.8% | 1.7% |
| 0.90 | 35 | 97.1% | 0.4% | 0.4% |
| 0.95 | 16 | 100.0% | 0.2% | 0.2% |

Guessing delete for every word scores **25.2%**. So 0.60 is a **2.6x lift** and 0.80 is **3.5x**,
against C10's hand-crafted ranking at 1.88x and C12's best gate at 1.24x. And unlike either of
those it yields a *probability*, which is what C9 said a per-category rate could never be and
what the band system has always needed.

**The best operating point is 0.60, at a projected 4.5% closure.** The measured held-out closure
before this was 0.15%, so it is thirty times the reach at better accuracy, from a model that took
one afternoon and no GPU. Projected, not measured: it counts one deleted word as one word
operation and ignores the repair a deletion forces and the guard that can reject a paragraph.
Both only cost, so 4.5% is an upper bound, and C17 prices the gap.

**The 0.90 and 0.95 rows are not reportable.** They rest on 35 words and 16 words, and 100%
precision on 16 tokens is C14's lesson arriving a second time. The trustworthy range is 0.50 to
0.80, where hundreds of tokens sit behind each figure.

**The solver has to be allowed to converge.** The first version of this table capped lbfgs at 400
iterations, where it needs about 2,400, and reported 61.0% precision at a projected 2.7%. That is
not a rounding difference: a capped fit under-weights the badly scaled features unevenly, which
is precisely the thing the ablation below is trying to measure, so the ablation would have been
reading the solver rather than the features. Every figure in this constraint is from a converged
fit.

**The lift is lexical first, syntactic second, and not length at all.** C12 found that its best
hand-swept feature was length in disguise, so the same fit was run over each slice of the columns,
scored on the same held-out words at 0.60. `length` holds every feature that measures a size or a
place, so that dropping it leaves a model with no way to count:

| Features | Columns | Words fired on | Precision | Closure |
|---|---:|---:|---:|---:|
| everything | 6,136 | 1,118 | 64.9% | **4.5%** |
| without length | 6,132 | 957 | 66.1% | 4.1% |
| without syntax | 5,928 | 767 | 66.9% | 3.5% |
| without lexical | 212 | 361 | 60.7% | 1.0% |
| length only | 4 | **0** | 0.0% | 0.0% |
| syntax only | 208 | 296 | 63.2% | 1.0% |
| lexical only | 5,924 | 577 | 69.3% | 3.0% |

**Length alone never reaches the threshold on a single word in 31,464.** C12's warning does not
apply here, and removing the length features costs only 0.4 points. What carries the decision is
word identity: dropping the lexical columns costs 3.5 of the 4.5 points, and dropping syntax
costs 1.0. Neither alone reaches the pair, so the two are complementary rather than redundant.

Read the precision column against the closure column before concluding that a smaller model is
better. `lexical only` is the most *precise* row in the table and closes a third less, because it
fires on half as many words. That is the trade closure exists to resolve and precision cannot.

**What was learned is largely a deletion lexicon.** 5,924 of the 6,136 columns are lemma
one-hots, so the model has substantially memorised which words this editor cuts. It is scored on
documents it never saw, so it generalises across documents in this corpus; whether it generalises
to another discipline's vocabulary is untested and is the obvious way for it to fail.

**The phrase vocabulary is genuinely closed, and flat.** Fitted on the training documents,
measured against what the held-out documents need:

| Written at least | Vocabulary | Held-out phrases covered |
|---:|---:|---:|
| 1x | 5,050 | 68.9% |
| 2x | 975 | 62.6% |
| 5x | 308 | 52.9% |
| 25x | 55 | 34.6% |
| 50x | 27 | 25.2% |

27 phrases reach a quarter of it and 5,050 reach two thirds, so the tail is long, thin, and not
worth buying. The 975-phrase figure independently reproduces C15's span-level 970, which is a
useful cross-check on two different derivations of the same set.

**Why it is a constraint.** C9 concluded that "the decision is contextual and every mechanism
tried has been type-level", and that was right. What it could not say, because nothing had been
fitted, is whether the contextual decision was *hard* or merely *unattempted*. It was
unattempted. Every negative result from C9 to C12 is a fact about a hand-crafted feature set,
which is exactly what this document warned might be true and could not check.

**Strategy.** Wire the token classifier into the engine as a rule that proposes deletions at a
band-set threshold, and measure real closure rather than projected. The threshold is the band
dial, so `lint/bands._THRESHOLDS` stops being hand-set numbers. Only then add the phrase head,
and only then an encoder.

**Experiments.**
1. ~~*Tag the corpus and fit the baseline.*~~ Built: `manage.py tag`.
2. ~~*Ablate the length features.*~~ Done, above. Length alone fires on nothing, and the lift is
   lexical first and syntactic second. C12's warning does not carry over.
3. ~~*Wire it in and measure real closure.*~~ Done, as **C17**. 0.9% held out against the 4.5%
   upper bound; the shortfall is what the shape priors and the guard cost.
4. *Then the encoder.* The plan staged CPU-frozen embeddings after the linear baseline precisely
   so this comparison would exist. It now does, and the baseline is the thing to beat. The
   ablation says where to aim it: syntax is the half a bag of one-hots represents worst.
5. *Test the lexicon on prose from another field.* The model is mostly lemma weights fitted on
   one thesis corpus, so the failure mode to look for is a vocabulary that does not transfer.

---

## C17. A confident word is not a deletable word, and closure alone would not have said so

**Evidence.** `rules/rule_tagged.py` puts C16's model into the engine as an ordinary rule. It
scores every word, groups neighbouring wanted words into one span, and proposes each span as a
deletion carrying the model's own probability as its confidence. Nothing else changed: selection,
the bands, realisation and the guard are untouched, and the band threshold is now a real dial
over a real probability rather than a hand-set number.

Measured on the 233 held-out paragraphs, against the shipped rule on the same paragraphs:

| Method | Closure | Reach | Accuracy | Fired | Attested | Changed | Defects |
|---|---:|---:|---:|---:|---:|---:|---:|
| `relative/all-gates`, shipped | 0.15% | 0.40% | 68.3% | 14 | 79% | 14 | 1 |
| **`tagged/deletions`** | **0.78%** | 1.89% | 70.6% | 114 | **87%** | 83 | 1 |

**Five times the closure of the shipped rule, at a higher attestation rate, for the same single
introduced defect.** On the whole corpus with both rules registered, closure goes from 0.4% to
**1.0%**, and the split that matters goes from 0.15% to **0.9%** against 1.0% on train. A gap of
0.1 points between documents the model was fitted on and documents it has never seen is the
strongest generalisation evidence in this project, and it retires C14's complaint that the
held-out side is too thin to referee anything: it now carries hundreds of edits, not fourteen.

**The first version was worth 1.13% and was not admissible.** Ungated, the model deletes the only
verb in a sentence. Three shape priors were written from the measured defects, and each was
registered as an ablation so it had to earn its place:

| Method | Closure | Fired | Defects | Cases |
|---|---:|---:|---:|---|
| `tagged/no-gates` | **1.13%** | 162 | 18 | 1/5 |
| `tagged/no-root-gate` | 0.97% | 145 | 12 | 4/5 |
| `tagged/no-modifier-gate` | 0.87% | 122 | 5 | 4/5 |
| `tagged/no-prep-gate` | 0.81% | 118 | 5 | 3/5 |
| `tagged/deletions` | 0.78% | 114 | **1** | **5/5** |

**Closure is monotonically *worse* as the rule gets safer, and the safest rule is the only
admissible one.** Ranked on the master metric alone, the ablation with 18 introduced defects
wins. This is `good.md` section 0 stated as a measurement rather than as a worry: closure charges
one word-operation for deleting a sentence's only verb, and a reader charges the whole paragraph.
The defect count and the case bank are what stop the metric picking the wrecking ball, and the
five cases are all observed failures, which is the kind that is worth keeping.

**Why it is a constraint.** Every learned proposer from here on will be confident about tokens
whose removal breaks the sentence, because a per-token model has no way to know that the word it
likes is the sentence's only predicate. The shape priors are not a patch on this model; they are
the standing cost of asking a per-token question, and any successor pays it too.

**And the parser hides one whole damage class.** `_orphaned_determiner` was first written the
obvious way, as a determiner whose head is not a noun. It scored zero on text that reads "told me
the in relation to speaking", because faced with a determiner that has lost its noun the parser
does not leave a broken dependency: it relabels the word a pronoun and makes it the direct
object. The tag stays `DT`; the dependency does not survive. Keyed on the tag, the detector finds
exactly the damage and the gate removes it, 3 to 0.

This is **C4 arriving from the other side**. C4 concluded that a statistical parser normalises
damage away and closed output-side validation as unreachable. It is reachable; what is
unreachable is the *dependency* layer, which is trained to produce a well-formed tree from
whatever it is given. The tag layer is not, and B5's point stands that C4 generalised one failure
into a closed question.

**Strategy.** The gap between 4.5% projected and 0.9% measured is now priced, and roughly three
quarters of it is the shape priors refusing runs. Refusing a whole run because one word in it is
the sentence root throws away the rest of the run, so trimming the run instead of dropping it is
the cheapest remaining move. After that, the phrase head: half these refusals are cases where
Opus deleted *and wrote something*, and DELETE without its phrase is only half the tag.

**Experiments.**
1. ~~*Wire it in and measure.*~~ Built: `rules/rule_tagged.py`, registered.
2. *Trim refused runs instead of dropping them.* Three quarters of the projected-to-measured gap
   is here. A run that contains the sentence root should lose the root, not the run.
3. *Raise the floor and re-measure.* Proposals start at 0.50 and the band admits at 0.70 or 0.80,
   so most of what the model proposes is never seen. Whether the low proposals cost anything at
   all is unmeasured.
4. *Set the band thresholds from the operating table.* `lint/bands._DEFAULT_THRESHOLD` currently
   gates this family by accident rather than by choice, and C16's table is the evidence for
   choosing.

---

## C18. The refused runs are one word long, so trimming them buys almost nothing

**Evidence.** Roadmap step 7 said three quarters of the gap between C16's 4.5% projected closure
and C17's 0.9% measured was a shape prior refusing a whole run because one word in it was
unsafe, and that trimming the run instead would recover most of it. The rule now holds the
offending word back and deletes the rest of the run around it. Counted over the same 233
held-out paragraphs:

| | runs | words |
|---|---:|---:|
| runs the model proposes | 2,213 | 2,681 |
| runs no prior objects to | 1,134 | |
| runs with a held-back word | 1,079 | |
| of those, one word long | **839** | |
| words trimming releases | 151 | **190** |

**Seventy-eight per cent of refused runs are a single word.** There is nothing beside the
offender to release, so the whole-run refusal was never where the gap was. What trimming
recovers is 190 words of 2,681, and after the band thresholds that is seven more edits:

| Method, 233 held-out paragraphs | Cases | Closure | Reach | Fired | Ceiling | Defects |
|---|---|---:|---:|---:|---:|---:|
| `tagged/drop-whole-run`, what shipped | 8/9 | 0.78% | 1.81% | 108 | 88% | 1 |
| **`tagged/deletions`**, trimmed | 9/9 | **0.85%** | 1.92% | 115 | 89% | 2 |
| `tagged/no-gates` | 1/9 | 1.13% | 2.62% | 162 | 85% | 21 |

**The step missed its target by fifteen times**: 0.9% to 2% was projected and 0.85% was
measured, corpus closure 1.0% either way with the held-out side moving from 0.9% to 1.0%. The
projected-to-measured gap is therefore not an arbitration failure. It is the priors refusing
single words the model is confident about, which means closing it needs a model that stops
wanting them rather than an engine that argues about the run.

**Trimming exposed two defects the refusal had been hiding.** Deleting around a held-back root
takes the words that hold the root up: "might be enabling" loses "be", and "there are" loses
"there". Neither is visible afterwards, because the parser rereads "might enabling" with
"enabling" as a well-formed root, which is C4 for the third time. Both are refused at proposal
time now rather than detected after it, by two priors written from the observed cases:

- `keep_verbs_supported`, holding back an auxiliary or a subject whose verb survives.
- `keep_verbs_complete`, holding back an object whose verb survives ("provided to articulate").

With both, the defect count is back to 2, one of which pre-dates this change and one of which is
a false positive: `subjectless_verb`, added here for the expletive shape the parser does still
show, fires on a 40-word sentence that reparsed with a relative clause as its root. A detector
this shallow costs one false positive per 233 paragraphs, which is the price of seeing the real
one at all.

**Two smaller things the run turned up.**

- **The preposition prior was keyed on the wrong attribute.** It found the surviving governor by
  `dep_ == "prep"`, so a coordinated preposition ("and in relation to", labelled `conj`) walked
  past it. Keyed on `pos_ == "ADP"` now. This was already true before trimming.
- **The modifier prior has gone quiet.** `tagged/no-modifier-gate` now scores identically to the
  shipped rule on every column and passes every case, because the object prior holds back the
  same words. It stays registered, and it is doing nothing measurable on this corpus.

**Strategy.** Trimming ships because it is free at worst and the case bank disqualifies dropping
the whole run, but it is not a route to reach. The gap C16 projected is in the single-word
refusals, and the ways to reach it are a better model rather than a better arbitration.

**Experiments.**
1. ~~*Trim refused runs instead of dropping them.*~~ Built, and measured at 0.07 closure points.
2. *Ask what the 839 single-word refusals are.* A prior that refuses 839 of 2,213 proposed runs
   is either catching a model that is wrong about those words or blocking a family of edits Opus
   does make. Which of the two is the question C16's operating table cannot answer and the
   attestation probe can.
3. *Retire or re-aim the modifier prior* once something distinguishes it from the object prior.

---

## C19. The shape priors know nothing about what Opus did, and that is what they are for

**Evidence.** C18 left one question: a prior that holds back 1,111 of the 2,584 words the model
wants is either catching a model that is wrong about them or blocking a family of edits Opus
makes. The gold tag for each word answers it directly, since `tagging/vocabulary.tags_for` already
labels every source word KEEP or DELETE from the alignment. Over the 233 held-out paragraphs:

| Words | Count | Opus deleted the same word | Inside a span Opus changed | Of those, rewritten rather than cut |
|---|---:|---:|---:|---:|
| fired | 1,473 | 828 (**56.2%**) | 50.3% | 62.3% |
| held back by a prior | 1,111 | 613 (**55.2%**) | 49.2% | 60.9% |

Per prior, the words held back and the share Opus also deleted: root 323 / 60.7%, preposition
333 / 55.9%, modifier 309 / 54.0%, support 299 / 51.8%, object 130 / 51.5%. Four of the five hold
back words at within four points of the rate for the words that fire, and **the root prior holds
back words Opus deleted more often than the ones the rule keeps**.

**Neither answer was right.** The priors carry no information about whether Opus touched the word.
They are not a precision filter and they are not blocking a family; they select on whether this
engine can take the word out without wrecking the sentence, which is a different axis entirely.
That is also why they cost so little closure while removing nineteen defects of twenty-one: they
are almost orthogonal to the gold.

**What it means for the remaining reach.** There are 613 held-out words that Opus deleted and the
priors refuse. They are not reachable by a better deletion licence, because the objection is not
about whether the word should go but about what the sentence looks like once it has. Opus deletes
a sentence root and rewrites the clause around it; the engine deletes a sentence root and leaves a
fragment. Roughly half of what C16's 4.5% projection assumed is therefore behind generation and
not behind arbitration, which is the second measurement in a row pointing at the phrase head
rather than at more licence work.

**Caveat on the denominator.** 56.2% is the share of fired *words* whose gold tag is DELETE, and
it sits below the 89% attestation ceiling and the 72% closure accuracy because all three count
different things: the word's own tag, whether Opus changed the text an edit covered, and whether
an edit moved the paragraph nearer the gold. Quote it against the held-back column and nowhere
else.

---

## C20. The band was inherited rather than chosen, and choosing it costs accuracy for reach

**Evidence.** `lint/bands.py` holds a threshold per family per band, and the `tagged` family had no
row, so it fell through to `_DEFAULT_THRESHOLD`: 0.95, 0.90, 0.80, 0.70. Those numbers were set
for hand-written rules whose confidences are hand-set constants, and the fitted model returns a
probability whose meaning is measured (C16). Each band now takes a row of that table, and the
rule's proposal floor moves up to the loosest of them:

| Band | Threshold | Precision at that row |
|---|---:|---:|
| clarity | 0.90 | 97.1% |
| light | 0.80 | 87.3% |
| firm | 0.70 | 74.9% |
| aggressive | 0.60 | 64.9%, where projected closure peaks |

Over the full corpus, before and after:

| | closure | held out | reach | accuracy | fired | attested | paragraphs changed |
|---|---:|---:|---:|---:|---:|---:|---:|
| inherited default | 1.0% | 1.0% | 2.3% | 72.1% | 690 | 89.9% | 583 (39.1%) |
| **chosen from the table** | **1.7%** | **1.5%** | 4.6% | 68.1% | 1,496 | 84.0% | 823 (55.2%) |

**This is the first increment here that spends accuracy to buy reach.** Four points of accuracy
and six points of attestation for 0.7 points of closure. The arithmetic supports it, since at
68.1% a point of reach is still worth 0.36 points of closure, and `plan.md` section 2 sets the
abandon line at 62%. It is also the change most likely to be wrong in the way this project cannot
yet see, because closure rewards agreement with one editor and the paragraph count changed from
39% to 55%. Step 9's hand-checked damage set is the referee, and it now has something specific to
referee.

**Reading the output found a defect no panel had.** At the new operating point the sample document
came back with "cases from the literature that demonstrate how" reduced to "cases from the
literature that how". The model scores `demonstrate` at 0.87, so this was never a threshold
question: it fired under the old ladder too, and no measurement had flagged it. The root prior
cannot see it, because a relative clause's verb is not the sentence's root. A sixth prior,
`keep_clause_heads`, holds back a verb whose own subject or object survives. It costs 0.2 closure
points on the train side and **nothing at all on held-out prose**, which is the shape a safety
gate should have.

On the 233 held-out paragraphs, with the priors as they now stand:

| Method | Cases | Closure | Reach | Accuracy | Fired | Ceiling | Defects |
|---|---|---:|---:|---:|---:|---:|---:|
| **`tagged/deletions`** | 10/10 | **1.32%** | 4.19% | 65.7% | 220 | 84% | 5 |
| `tagged/no-gates` | 2/10 | 2.72% | 8.04% | 66.9% | 473 | 79% | 49 |
| `tagged/no-prep-gate` | 8/10 | 1.52% | 4.54% | 66.7% | 246 | 82% | 12 |
| `tagged/no-support-gate` | 9/10 | 1.66% | 4.86% | 67.1% | 263 | 84% | 12 |
| `tagged/no-clause-gate` | 9/10 | 1.40% | 5.07% | 63.8% | 282 | 79% | 6 |
| `tagged/no-object-gate` | 8/10 | 1.44% | 5.11% | 64.0% | 285 | 80% | 7 |
| `tagged/no-root-gate` | 10/10 | 1.36% | 4.36% | 65.5% | 225 | 84% | 5 |
| `tagged/no-modifier-gate` | 10/10 | 1.32% | 4.19% | 65.7% | 220 | 84% | 5 |

**Two of the six priors are inert.** Dropping the root prior or the modifier prior changes no case,
no defect and at most 0.04 closure points, because the clause prior holds every root that has a
subject and the object prior holds every determiner-bearing noun that is an object. They are kept
for now on the argument that a root without a subject and a modified noun outside object position
both exist and neither is in this corpus, which is an argument and not a measurement.

**Experiments.**
1. ~~*Set the band thresholds from the operating table.*~~ Built, and it moved the headline.
2. *Turn the root and modifier priors off together and re-measure.* Each is inert alone; nothing
   says they are inert as a pair, and if they are, four priors ship instead of six.
3. *Read the output at the aggressive band on prose from another field.* The operating point was
   chosen from one corpus's precision curve, and the lexicon it rests on is that corpus's.

---

## C21. A reader finds damage in half the paragraphs the panel called clean

**Evidence.** `manage.py damage` lints the held-out documents, takes every paragraph it changed
in corpus order, and lays each edit out with the original, the linted text and Opus's version.
The first set is 100 paragraphs and 184 edits, judged one at a time against G1 to G3 in
`good.md` section 2, with the verdicts kept in `damage/verdicts.jsonl` so the number can be
recomputed and disputed.

| | Judged | Damaged |
|---|---:|---:|
| **paragraphs the linter changed** | **100** | **48 (48%)** |
| edits | 184 | 71 (39%) |

The panel that scored this same configuration reported **five** defects. `eval/grammatical.py`
looks for a sentence with no root predicate and finds one damaged edit in fourteen. Nothing else
in the harness was looking at all, so 48% was the standing state of the shipped rule and every
number in C16 to C20 was measured over it.

**Attestation does not protect the reader.** Of the 140 edits Opus and the foil both appear to
support, 50 damage the text: agreeing with the reference is agreement about *which words go*, and
the damage is in what the sentence becomes afterwards. The "attested by neither" class, which
step 9 was told to triage by, is the worst at 64% but holds only 14 edits, so triage would have
found a tenth of this.

**Three shapes account for four fifths of it, and all three are structural.**

| Shape | Damaged edits | Example |
|---|---:|---|
| the deleted word has a dependant that stays | 40 | "here to underline that people's ability" to "here to that people's ability" |
| a possessive marker deleted on its own | 17 | "people's screens" to "peoplescreens" |
| a correlative pair closes up | 5 | "as well as their appeal" to "as as their appeal" |

The first is the general case of three priors that had been found one at a time: the sentence
root, the modified noun, and the relative clause's verb are all words with a surviving dependant.
Replacing all three with `keep_words_with_dependants` makes the two priors C20 called inert into
one prior that is the largest single safety gate in the rule, and drops the count from six to
five. `keep_possessives` refuses a clitic, which is not a word the engine may take on its own.
`keep_joins_distinct` refuses a deletion that leaves the same word twice in a row, which is what
"as well as" and "refer to" become when the word between the pair goes; the pair is found in the
text rather than in a list of expressions, because the list would never end.

On the 233 held-out paragraphs, before and after, with the damage set re-judged on the new
output:

| | Cases | Closure | Reach | Accuracy | Fired | Ceiling | Paragraphs damaged |
|---|---|---:|---:|---:|---:|---:|---:|
| six priors, as C20 shipped them | 10/10 | **1.32%** | 4.19% | 65.7% | 220 | 84% | **48 of 100** |
| five priors, after the damage set | 13/13 | **0.89%** | 2.27% | 69.5% | 118 | 87% | **11 of 95** |

The second row changes 95 paragraphs rather than 100, which is every paragraph it changes at
all, and four of its edits carry no verdict because they exist only in that variant, so 11 is a
floor. **Damage cost 0.43 points of held-out closure and removed four fifths of itself.** That is the
trade `good.md` section 6 point 4 says to take, and this is the first time the project has had
the number on both sides of it. Every ablation of the five is now disqualified by a case, so
nothing here is inert: dropping the dependant prior alone scores 1.64% and damages 37 edits.

**What is left is not structural.** In the rule that ships today ten edits still damage: five are G3, and five are G1 of one
kind, a modifier whose removal changes what the sentence claims. "negatively affecting their
wellbeing" to "affecting their wellbeing", "the primary way" to "the way", "accessible
potentially anywhere" to "accessible anywhere". Nothing in a parse separates those from "nicely
illustrates", which is a sound cut, and closure cannot see them either, because Opus deleted
several of the same words in its own version. A hedge is a semantic class and this engine has no
semantic feature.

**The judge was Claude and not the author, and one judge is not a repeatability check.** The set,
the tool and the criteria exist; what does not exist is a second reading. `plan.md` step 9 says
the step fails if hand judgement cannot be made repeatably, and that half is unanswered rather
than passed.

**Experiments.**
1. ~~*Build the set and measure the rate.*~~ Built, and it moved the rule rather than the report.
2. *Have the author re-judge a sample of the set.* Two judges on the same 184 edits gives the
   agreement rate that decides whether 9% is a measurement or one reader's opinion.
3. *Find a feature that separates a hedge from an adverb.* The five remaining G1 edits are one
   class, and it is the only class left that structure cannot reach.
4. *Ask what the aggressive band is for.* Damage runs 13% there against 2% at firm, on a band
   that exists because C20 read it off the operating table.

---

## C22. Three defects that no measurement could have found, because nothing yet triggers them

**Evidence.** All three were read out of the code rather than measured, and all three are latent
exactly while one licensed family and no ranked family are registered.

**Selection compared a probability with an ordering.** `lint/select._best_set` ran one interval
schedule over every admissible proposal, scoring each as `confidence x (1 + words_saved)`. A
ranked proposal's confidence is an ordering inside its own rule and means nothing against a
threshold (C9 to C11), so a six-word adjunct guess at 0.40 weighed 2.80 and outweighed a licensed
relative-clause reduction at 0.92 weighing 2.76. Selection now schedules the licensed proposals on
their own and lets ranked guesses fill only what is left, which cannot be tuned wrong because it
is not a comparison.

**The budget dropped edits that were not causing the breach.** `_trim` removed the least confident
edit until the paragraph kept enough words. An edit that saves no words cannot move that
constraint, so the pass removed correct work and looped again with the breach untouched. It now
drops the edit that gives back the most words per unit of confidence given up, and never one that
gives back nothing.

**Reproducibility was claimed and not pinned.** `requirements.txt` pinned no version and
`en_core_web_sm` was fetched by `python -m spacy download`, while every prior in
`rules/rule_tagged.py` reads `dep_`, `tag_` and `pos_`. A parser bump silently changes every
number in these documents. The requirements are now pinned, the model version is pinned at 3.7.1,
and `manage.py install` reports a mismatch as a failure with the exact wheel to install.

**Target and result.** The step's stated target was **no closure movement**, which is what a
latent defect should produce, and a run that reproduces the headline byte for byte. Linting all
233 held-out paragraphs before and after gives the same SHA-256 over the concatenated output,
`8cb5fff2915f6c99`, under three different `PYTHONHASHSEED` values. The fix is therefore free
today and the defect is real tomorrow: the day a ranked family registers, the old selection
would have preferred its guesses.

---

## C23. The engine writes, and writing is worth a tenth of what the roadmap projected

**Evidence.** C15 said a closed vocabulary induced from the training documents reproduces Opus
exactly on 64.6% of rewriting spans, and step 11 was to build it. It is a table and not a model:
for every span the gold editor deleted, `tagging/phrases.py` counts what was written in its
place, and a span keeps an entry when one phrase was written at least twice and accounts for at
least 60% of what the editor did to that span. That is 348 entries. On held-out spans it has an
entry for, it fires 306 times and writes exactly what Opus wrote **249 times, 81.4%**.

The licence is not the table's. A span is only offered to it because the fitted keep-or-delete
model already wants those words gone and the five shape priors already allowed it, which is the
division C9 to C12 could not find: **allocation is learned per token, execution is a closed
lookup.** Nothing here can invent a word, so G8 holds by construction and the changelog reads
`'Firstly' becomes 'First'` rather than naming a model.

On the 233 held-out paragraphs:

| | Cases | Closure | Reach | Accuracy | SARI | add | Ceiling |
|---|---|---:|---:|---:|---:|---:|---:|
| `tagged/deletes-only` | 13/13 | 0.89% | 2.27% | 69.5% | 0.5574 | 0.0018 | 87% |
| **`tagged/deletes-and-writes`** | 13/13 | **0.98%** | 2.05% | **73.9%** | **0.5598** | **0.0074** | 86% |

Over the whole corpus the linter now closes **1.3%**, held out **1.1%**, at 73.2% accuracy, and
`tagged.write` fires 127 times against `tagged.delete`'s 693, attested 73.2% against 83.7%.
Writing is the less reliable half, as C15 predicted at 81.4% exact, and it still pays: accuracy
rises four points because replacing a word is right where deleting it was too much.

**The target was 2% to 4% and the result is 0.09 points. The target was wrong, and it was wrong
in a way worth keeping.** Reach *falls* when the table fires, from 2.27% to 2.05%, because a
replacement moves fewer words than a deletion. The phrase head cannot open a site: it only
changes what happens at a site the deletion model already licensed, and that model licenses 2.3%
of words. Step 11 was written as though writing were a reach mechanism. It is a precision
mechanism, and the reach the roadmap still needs is somewhere other than here. Steps 13 and 14
were where this constraint expected to find it, and C25 and C26 measured both and found nothing.

**One damage case is the table's own.** "In the specific case mentioned, Hannes shared..." became
"In the specific case said,...", because the table's entry for that span was induced where the
surrounding sentence was different. Purity is a per-span statistic and carries no context; that
is the whole of what a table can be wrong about, and 81.4% is the rate.

**Experiments.**
1. ~~*Induce the table and wire it in.*~~ Built. Closure 0.89% to 0.98% held out, and the first
   `add` column above noise.
2. *Sweep support and purity against the damage set rather than against agreement.* 81.4% exact
   is agreement with Opus; the question the damage set asks is how many of the other 18.6% are
   wrong English rather than different English.
3. *Let the table fire where the model does not.* Every entry is a span Opus rewrote, and the
   rule only ever offers it spans the deletion model already wanted. Offering the table every
   span it knows would be a second licence, and C9 is the reason to expect that to fail.

---

## C24. A frozen encoder cannot license on its own, and is worth a point as extra columns

**Evidence.** Step 12 asked whether the syntactic half of the keep-or-delete decision is better
represented by a pretrained encoder than by the lemma one-hot bag C16 fitted. `manage.py encoder`
fits the same decision three times over the same words, all on the training documents, all scored
on the held-out ones: the shipped feature set, the frozen encoder alone, and both together. The
encoder is `sentence-transformers/all-MiniLM-L6-v2`, run in eval mode on one thread over the whole
paragraph, giving every word the 384 numbers that describe it in context. There is no lemma column
in it anywhere.

174,231 training words, 31,464 held-out words, read at threshold 0.60:

| Features | Columns | Words fired on | Precision | Recall | Projected closure |
|---|---:|---:|---:|---:|---:|
| one-hot | 6,136 | 1,118 | 64.9% | 9.1% | 4.5% |
| encoder | 384 | 144 | **43.1%** | 0.8% | **-0.3%** |
| one-hot and encoder | 6,520 | 1,441 | 64.0% | 11.6% | **5.4%** |

**The encoder alone is not a licence.** It fires on 144 words and is wrong on more than half of
them, which is below the break-even line closure puts at 50% accuracy, so switching to it would
subtract. That is the answer to the ablation C18 raised: the one-hot bag is not a weak stand-in
for meaning, it is where nearly all of the signal is, and the reason is visible in the shapes.
The bag carries 6,136 columns fitted on 174,231 words; the encoder carries 384 columns that were
fitted on somebody else's corpus for somebody else's task, and nothing in this pipeline adapts
them.

**Added to the bag it buys recall, not precision.** Together the two sets fire on 29% more words
at the same precision, which is 0.9 projected points. That clears step 12's target, and the target
is worth reading carefully: projected closure is an upper bound that ignores repair and the guard,
and the last time the engine cashed one in, C16's projected 2.7% arrived as 1.3%. Half of 0.9
points is the honest expectation.

**What it would cost is the reason it is not wired in.** The engine imports spaCy and reads a
table of rounded weights; wiring these columns in puts `torch` and a downloaded encoder inside
`manage.py lint`, and every damage verdict in `damage/verdicts.jsonl` would have to be judged
again. That is a trade about what this tool is, not a measurement, so it is recorded here and
left to be decided rather than taken.

**Experiments.**
1. ~~*Fit the encoder against the one-hot bag on held-out documents.*~~ Done, above.
2. *Fine-tune the head rather than freezing it.* Every number here is a linear head on frozen
   vectors, which is the cheap end of the ladder `learning.md` sets out; the gate for climbing it
   is that prompting and features have demonstrably plateaued, and one measurement is not that.
3. *Ask the same question of the phrase table.* The encoder was tested on the deletion half only.
   C23's table is keyed on a span's literal text, which is exactly where a contextual vector has
   something a lookup cannot have.

---

## C25. Allocation is paragraph length, and the engine's own evidence makes it worse

**Evidence.** Step 13 was the roadmap's answer to reach: given a document and a reduction, choose
which paragraphs absorb it. `manage.py allocate` holds the size of the cut fixed at what Opus
actually removed from that document at that band, so only the split across paragraphs is judged.
15 document-and-band units, 3,301 removed words, held out.

| Method | Captured | Wasted | Error |
|---|---:|---:|---:|
| length-proportional | **84.6%** | 1.8% | 0.31 |
| equal share | 79.6% | 2.7% | 0.41 |
| model words | 62.6% | 0.6% | 0.75 |
| model mass | 62.2% | 0.6% | 0.76 |
| length and model mass, halved | 76.1% | 1.2% | 0.48 |
| gold allocation (anchor) | 100.0% | 0.0% | 0.00 |

`captured` is the share of Opus's cut that a paragraph's budget can pay for, counting the smaller
of the two, so nothing is earned by handing a paragraph more than was taken from it.

**Step 13 fails its target and the failure is informative twice over.** One: what the engine does
today, one band target applied to every paragraph, already captures 84.6%, so the whole of
document-level allocation is worth at most 15 points of budget placement and not the reach step 14
was waiting for. Opus spreads its cut close to proportionally, and a document where one paragraph
absorbs everything is not the document this corpus holds. Two: every variant that consults the
fitted model is *worse* than counting words, and the blend is worse than length alone. The model
knows which words it wants gone; summed over a paragraph that is a statement about how many
deletable-looking words the paragraph contains, which is not the same thing as how much the editor
chose to cut there, and C9's type-and-token distinction has now been demonstrated at a second
altitude.

**Experiments.**
1. ~~*Beat a length-proportional quota.*~~ Done, and nothing did.
2. *Ask whether the 15 points are reachable at all.* The anchor is a per-paragraph split; the
   question this does not answer is whether any feature of a paragraph, rather than of its words,
   predicts the residual after length.
3. *Read the same table on the train split.* 15 units is enough to separate 84.6% from 62.6% and
   not enough to separate 84.6% from 80%.

---

## C26. The largest family is the least predictable: a dropped sentence looks like a kept one

**Evidence.** `sentence` is the biggest thing in the corpus, 15.6 reach points at 18.1 words per
decision, and step 14 held it back for step 13 on the grounds that dropping a sentence is a
discourse decision. C25 removed that gate by failing it, so the question was asked directly:
given every source sentence of the 1,490 gold paragraphs, labelled by whether the aligner puts it
in a delete bead, can a fitted decision tell the dropped ones from the kept ones? 6,557 training
sentences, 1,236 held-out sentences, 68 of them dropped, over 29 columns in three groups: `size`,
`inside` (what the sentence is made of) and `discourse` (where it sits, how much of its vocabulary
repeats elsewhere in the paragraph, whether it opens with a connective).

Dropping every sentence would be right 5.5% of the time. The fitted decision never reaches 0.5 on
any held-out sentence at all, so read as a ranking instead:

| Sentences dropped | Opus dropped them too | Precision | Net words |
|---:|---:|---:|---:|
| 10 | 0 | 0.0% | -79 |
| 25 | 2 | 8.0% | -180 |
| 50 | 3 | 6.0% | -433 |
| 100 | 8 | 8.0% | -986 |

**Nothing here beats guessing.** 8% against a 5.5% base rate is a 1.5x lift, below C10's 1.88x and
C12's 1.24x, and the sentences the model is *most* confident about are the ten it gets entirely
wrong. Every threshold that fires at all loses words: the best row in the table is -2.6% closure
and the rest are zero because the model refuses to fire. Every ablation is identical, which is not
a finding about the features but the absence of one, since a model that never crosses the
threshold cannot be made to cross it by removing columns.

**The discourse features are there and they carry nothing.** `repeated` and `unique` measure how
much of a sentence's content vocabulary appears elsewhere in its paragraph, which is redundancy,
which is the textbook reason to cut a sentence. Removing the whole `discourse` group changes
nothing, because there was nothing to remove. What Opus drops is a sentence whose *content* the
document does not need, and no count of shared lemmas inside one paragraph is a measure of that.

**Read with C21.** This family is deletion at 18.1 words a time, and the damage set already shows
that at 8% precision an edit does not merely fail to close the gap, it damages the paragraph.
Wiring this in at any threshold would cost closure twice and would be the single largest source of
damage in the engine.

**Experiments.**
1. ~~*Fit the drop decision and score it held out.*~~ Done, and it does not beat the base rate.
2. *Ask the same question with the document, not the paragraph, in scope.* Every feature here is
   computed inside one paragraph because that is the only unit the corpus stores; a sentence that
   repeats what an earlier paragraph said is invisible to all of it, and that is the most likely
   place the signal actually is.
3. *Check the label.* A delete bead is the aligner's judgement, and `_split_out_deletions` is the
   heuristic that separates a drop from a merge. 68 held-out positives is few enough that a
   labelling error rate of a few per cent would matter.

---

## C27. `clause` and `voice` both refuse the probe, and one of them refuses absolutely

**Evidence.** Step 15 named two families the typology calls mostly deletion and nobody had ever
asked Opus about. Per step 3 and C13, the probe comes before the rule, so three probe-only
generators were written and registered under their own family names, where no experiment can pick
them up: `clause/adverbial` drops a whole adverbial clause, `clause/complement` drops a complement
clause, and `voice/probe` drops the passive auxiliary and any agent phrase after it. Measured on
the training documents, so the held-out split stays unspent.

| Probe | Attested | Declined | Rewritten or dropped | Rate |
|---|---:|---:|---:|---:|
| `clause/adverbial` | 0 | 368 | 1,172 | **0.0%** |
| `clause/complement` | 0 | 407 | 1,379 | **0.0%** |
| `voice/probe` | 7 | 274 | 1,444 | **2.5%** |

The gate C13 set is 20% of decidable candidates, and 2.5% is the highest of the three. All three
are refused, and no rule is built for either family.

**Zero is a result, not a broken probe.** The same machinery returns 7 attested for the voice
probe on the same corpus in the same run, so it can say yes; it says no 775 times for clause
dropping. Opus does drop clauses, 127 times by the typology's count, and it does not drop the ones
a parse can point at: an `advcl` is an adverbial clause by its label and a reason, a condition or a
time by its function, and removing it takes out a truth condition (G1) rather than a wordy
construction. `clause` is 781 instances of which 654 are predicate absorption, which is rewriting
and not this.

**Voice fails for the reason the typology predicted.** 2.5% is the rate for taking the passive
apart by deleting its auxiliary, and the seven attested cases are `being` and `were` inside spans
Opus was rewriting anyway. The typology says the real work in this family is recovering an agent
that is absent from the surface and deciding whether the change is wanted at all, which it calls a
discourse question. Deleting the auxiliary is the part that is easy to propose, and it is not the
part Opus performs.

**Together with C25 and C26 this closes the deterministic ladder.** Steps 13, 14 and 15 were the
roadmap's three remaining sources of reach that do not write words, and all three are now measured
and refused. What is left in `plan.md` is step 16, and step 16 generates.

**Experiments.**
1. ~~*Probe `clause` and `voice` before building either.*~~ Done, above, and both refused.
2. *Probe predicate absorption instead.* 654 of the 781 `clause` instances are a finite clause
   becoming a participial or appositive phrase, which is a rewriting operation with a closed shape
   and was never separated from clause dropping when the family was named.
3. *Probe `agent-restored` on its own.* 233 instances, and the only part of `voice` that adds
   words rather than removing them, so it is the one part of the family the phrase table's
   architecture cannot express at all.

---

## Where the queue lives

There is no queue here. This file records what each measurement established, in the order it was
established, and the roadmap that acts on it is section 4 of `plan.md`. Steps 1 to 6 there are
done and carry the constraint that closed them; steps 7 to 16 are open and each names the result
that would kill it.

C2 is not a task either. It is the rule for judging all of the above: report proposals generated,
not edits arbitrated.
