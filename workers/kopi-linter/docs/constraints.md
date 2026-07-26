# Constraints

`typology.md` says what has to be solved, derived from the corpus before anything was built.
`approaches.md` catalogues techniques, also written before anything was built. This document is
the third kind: **the constraints that only became visible by building the engine and running
it against real prose.** They are not restatements of the typology. Each one is a limit on the
approach itself, established by a measurement, and each blocks something specific.

Measured 2026-07-26 on 18 real body paragraphs (reference lists excluded), and on the full
1,523-paragraph gold corpus where stated.

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

**How far deletion alone can go.** Deletion-reachable word counts from `typology.md` section
1.2, assuming a family is reachable when its dominant subtype removes rather than rewrites:

| Family | Words moved | Deletion-reachable |
|---|---:|---:|
| `sentence` dropping | 8,255 | 8,255 |
| `adjunct` (92% is PP-dropped) | 6,374 | ~5,865 |
| `relative-clause` | 1,043 | 1,043 |
| `stance` | 883 | 883 |
| `modifier` / `intensifier` / `filler` | 765 | 765 |
| `clause` (16% is clause-dropped) | 3,208 | ~513 |
| **Total** | | **~17,300 of 37,622 (46%)** |

So a purely deleting linter tops out near **half** of Opus's word reduction, and only if every
one of those families is built and licensed perfectly. This is the single most important number
in the document: it sets the ceiling of the current architecture and says that a generation
spine is not optional, only deferrable.

**Strategy.** Defer generation, but stop pretending it is a family. Build it once as shared
infrastructure: `lemminflect` for inflection, the parse for agreement features, and a
surface-realisation step that takes a target lemma plus a syntactic slot and returns the correct
form. Then voice, nominalisation, connective and lexical all become licence problems rather than
engineering problems.

**Experiments.**
1. *Feasibility floor.* Build the ~46% deletion ceiling into the harness as a reference line, so
   any deletion family's contribution is reported against what deletion can ever achieve.
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

## C8. The irreducible core, restated with the build's evidence

`typology.md` puts free paraphrase at 14.3% of transformations and calls it the honest problem.
Nothing in the build changed that estimate, but C1 sharpens what surrounds it: the reachable
portion is smaller than the typology implies, because reaching it needs a generation spine that
does not exist. The ordering is therefore generation spine, then licences, then paraphrase, and
paraphrase stays last.

---

## Ordering

Derived from the constraints rather than from the family sizes, which is the change from
`typology.md` section 6.

**Done.**

1. ~~**C6**, scope the repair layer.~~ Resolved. Worth +0.067 SARI and +0.20 delete precision on
   its own, purely by making the linter stop editing text no rule had asked to change.
2. ~~**C4**, verify the grammaticality check.~~ Closed as unreachable. Both attempts failed and
   the reason generalises: the parser normalises the evidence away.
3. ~~**C3**, the licence-model comparison on `adjunct`.~~ Answered, as **C9**: neither structural
   nor induced per-category licensing works, and the reason is architectural.

4. ~~**C9**, band as budget rather than threshold.~~ Built and measured, as **C11**: the budget
   half works, the licence half is untouched, and a ranked family without a licence is a
   better-ordered wrecking ball. No adjunct method is registered.
5. ~~**C5**, multi-reference agreement.~~ Corrected and much reduced. There is no three-way
   agreement involving Opus anywhere in the corpus; the only second reference is the weaker
   model. Usable for triage, not for scoring.

**Next.**

6. **C11a**, calibrate the ranked budget to the band's *measured median* reduction rather than its
   compression ceiling. Cheap, and the current run cannot be read as a fair test of ranking until
   it is done.
7. **C11b**, an argument-versus-adjunct licence induced distributionally: how often does this
   governor lemma occur with this preposition against how often it occurs without any, so that a
   near-obligatory preposition reads as an argument. Neither a hand-written verb lexicon nor a
   per-category drop rate, and the corpus can answer it. Without this, `adjunct` stays unregistered
   and the 46% deletion ceiling in C1 stays out of reach.
7. **C5**, the hand-checked damage set, now the only route to measuring precision rather than
   bounding it. Triage the candidates with the "attested by neither editor" class first.
8. **C1**, the generation spine, tested in isolation before any family depends on it.
9. **C7**, restraint, once there is enough coverage for it to matter.

C2 is not a task. It is the rule for judging all of the above: report proposals generated, not
edits arbitrated.
