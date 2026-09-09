# What good looks like

This memo defines success before any method is proposed, because the project has already been
burned once by the alternative. A rule was built, scored against a check that could only return
"pass", and reported at 100% agreement. The number was structurally guaranteed and meant nothing.

Everything here is written so that a method can **fail** it. A criterion that no input can
violate is not a criterion, and it does not belong in this file.

---

## 0. The master number

One number tracks progress, in per cent, and it is the one to quote:

> **Closure.** How much of the word-level distance from the original text to Opus's edit has been
> closed?

With `d` the word-level Levenshtein distance over whitespace tokens (unit cost for insert, delete
and substitute, which is speech recognition's word error rate put to another use):

    closure = 1 - d(output, gold) / d(original, gold)

Pooled across the corpus, never averaged per paragraph, for the reason SARI is pooled: paragraphs
Opus left alone have a zero denominator and whichever convention is chosen for them decides the
verdict. Implemented in `eval/closure.py`, reported first by `manage.py evaluate`.

**Why this rather than SARI as the headline.**

- **Doing nothing scores exactly 0**, not 0.2433. SARI pays for correct *keeping*, so a linter that
  touches 7% of paragraphs collects most of its score for the 93% it never looked at, and reads as
  halfway to Opus while having moved 1% of the words.
- **Damage scores below 0.** An edit Opus did not make moves the text away from the gold. The
  band-as-budget wrecking ball of C11 scored a respectable-looking 0.41 on SARI; on closure a
  system that cuts wrongly is visibly worse than one that sleeps. This is the property that makes
  the metric able to fail, per §7.
- **100% is reproducing the gold**, so the scale has a real ceiling rather than an asymptote.

**It decomposes, and the decomposition sets the strategy.** With `work = d(original, output)` and
`gain = d(original, gold) - d(output, gold)`:

    reach    = work / d(original, gold)      how much of Opus's work was attempted
    accuracy = (1 + gain / work) / 2         how much of what was attempted landed
    closure  = reach x (2 x accuracy - 1)

Both factors are bounded in [0, 1] by the triangle inequality, with no clamping. **At 50% accuracy
closure is zero however much is attempted.** Always report all three: the composite alone hides
which of the two is broken, and they break for opposite reasons.

**The one caveat, stated every time.** Closure measures agreement with Opus, not quality. A system
that improves a sentence in its own wording is scored as damage. That is acceptable here because
reconstructing Opus *is* this project's objective, but it means closure cannot referee a
generative model, and it cannot see an edit that is wrong in a way Opus also got wrong. §5.5 does
not become optional because §0 exists.

## 1. The object being judged

One paragraph, one intensity band, one output. The reference is Opus's edit of the same
paragraph at the same band, from the kopi-learner corpus.

Opus is a reference, not a ground truth. An edit Opus did not make is **unattested**, which is
weaker than wrong: Opus spends a limited budget per paragraph and often improves one clause
while leaving an equally weak one alone. Any metric that treats unattested as wrong will punish
correct work, and any metric that treats it as right will pass anything.

The consequence for scoring is that no single number decides. Section 5 sets out the panel.

## 2. What a correct edit is

An edit is correct when all five hold. They are listed in the order a violation is cheapest to
detect.

**G1. It preserves truth conditions.** The edited sentence entails the original and the original
entails the edited. Hedges, modals, negation, quantifiers and comparatives are part of the truth
conditions, not decoration. `may shape` is not `shapes`. `only limited understanding` is not
`understands`.

**G2. It preserves attribution.** Who claims what, and on whose authority, survives intact.
Citations, quoted spans, participant names and reporting verbs are untouchable unless a rule
explicitly and demonstrably handles them.

**G3. It is grammatical.** The output parses as a well-formed sentence of English. This is the
criterion the relative-clause rule broke on it-clefts, and it is not implied by G1: destroying
the cleft pivot in `It is X that is key` leaves the truth conditions inferable but the sentence
malformed.

**G4. It is an improvement on some stated dimension.** Words removed, dependency distance
reduced, a Latinate word replaced by a plain one, an agent restored. The dimension is named by
the rule and is measurable. "Reads better" is not a dimension.

**G5. It respects the band.** The band sets a floor on retained length and a threshold on the
confidence a family needs to fire. A clarity-band edit that rewrites voice has violated the
brief even if the sentence is better.

## 3. Negative cases

These are the cases that must be written as tests **before** a family is claimed. Each is a real
failure observed in this repo or a near neighbour of one. A method that handles the family
without handling its negative cases has not handled the family.

### 3.1 Relative-clause reduction

| Must not fire | Why | Status |
|---|---|---|
| `It is X **that is** key to my thesis` | it-cleft; the pivot is not a relative clause and the sentence loses its predicate | **observed breaking** |
| `the resource **that people can** use creatively` | deleting the span destroys the modal | fixed, `_survivor` refuses on `MD` |
| `a conversation **that has** recently shaped a relationship` | active perfect, not passive; reducing it yields a main clause asserting something nobody claimed | fixed, be-terminal chain |
| `the theory **that is** central` | bare adjective cannot follow the noun | fixed, complement required |
| `the data **which we** collected` | relativiser is the object, not the subject; deleting it strands the verb | fixed, `_SUBJECT_DEPS` gate |
| `the claim, **which is** false, was repeated` | non-restrictive; reduction changes the clause's relation to the head | untested |

Must fire, and stop in the right place:

| Must fire | Why it was refused before | Status |
|---|---|---|
| `practices **that are** increasingly personalised` | the adverb was inside the deleted span, so the rule refused rather than moving the boundary | fixed, `survives="increasingly"` |
| `participants **who had been** using TikTok` | the chain holds `had`, which the old purity test rejected although the reduction is sound | fixed, `survives="using"` |

**The change of verdict on the adverb case is recorded here deliberately**, per §7. It was a
`refuse` case whose stated reason was "deleting the span destroys the adverb". The span no longer
contains the adverb, so the reason had become false of the output and the case was testing an
implementation detail rather than a licence condition. It is now a `fire` case that additionally
asserts the adverb survives. The `survives` field exists because of it: `span` matches by
containment, so a case asking for `that are` to go is passed by a rule that deletes
`that are increasingly` and eats the adverb with it, which is precisely the §3.4 defect class.

### 3.2 Surface realisation

| Must not fire | Why | Status |
|---|---|---|
| `U.S. **p**olitics` | initialism, not a sentence end | **observed breaking** |
| `less surprising ... **b**ut still weird` | ellipsis, not a sentence end | **observed breaking** |
| `cf. **b**oyd, 2010` | abbreviation, and the name is genuinely lower case | fixed, `_ABBREVIATIONS` |
| anything inside `"..."` or `'...'` | quoted material is evidence; normalising it edits a source | patched, unverified |

### 3.3 Light-verb collapse (withdrawn family)

| Must not fire | Why | Status |
|---|---|---|
| `make **sense** of` | idiom; means *understand*, not *sense* | rule withdrawn |
| `offers only **limited** understanding of` | the collapse span swallows the modifier and reverses the claim | fixed, `_carries_modifiers` |
| `make **commercially-oriented** decisions` | same, with a compound modifier | fixed, same gate |

### 3.4 Cross-cutting

Every deleting rule must prove the span holds **only** what it intends to delete. This is the
single defect class behind most of the table above. A rule that computes a start and an end
offset and does not inspect what lies between them will eventually eat a modal, an adverb, a
modifier or a negation.

## 4. Invariants the guard enforces

Checked after application; failure returns the paragraph unchanged, never a partial edit.

- The citation set is identical.
- Every number in the original appears in the output.
- Retained length is at or above the band's floor.
- The output is non-empty.

These are necessary and nowhere near sufficient. All four passed on the broken cleft.

## 5. The scoring panel

§0 tracks *progress*: one number, quoted everywhere, comparable across months. This panel decides
whether a *method joins the registry*, which is a different question that one number cannot answer.
Closure can be raised by a rule that is right about Opus and wrong about English, and the panel is
what catches that. A gain on one cell that costs another is a finding to state, not a win to report.

**5.1 Corpus SARI** against the gold, pooled across the test set rather than averaged per
paragraph. The per-paragraph average is sensitive to the empty-denominator convention, and
choosing that convention changed which system won. Report `add`, `keep` and `delete` separately:
the composite hides that this linter scores almost entirely on `delete`.

**5.2 Attestation, per rule.** Of the edits a rule made, how many did Opus also make? The test
must be shaped to what the rule deletes:

- deletes content words: compare content lemmas
- deletes only function words: compare the surface span, anchored on the following token, because
  the content-lemma set is empty and the lemma test degenerates to a constant

Attestation is a **ceiling on precision**, not precision. When Opus rewrote the sentence wholesale
the anchored span is absent and the edit counts as attested by default. Report it as a ceiling.

**5.3 Grammaticality.** An independent check that the output parses cleanly: no orphaned
dependency, no sentence without a root predicate. This is what would have caught the cleft, and
it is currently missing.

**5.4 Coverage.** Paragraphs changed, edits per paragraph, words moved against the words Opus
moved. The linter's current 10.3% and 347 words against 22,816 is the real headline, and it is
not visible in SARI at all.

**5.5 Damage rate.** Of the paragraphs changed, how many contain an edit that violates G1 to G3?
Requires a held-out hand-checked set. It does not exist yet and nothing substitutes for it.

## 6. The bar a method has to clear

To join `lint/registry.py`:

1. Its negative cases from section 3 are written as tests and pass.
2. It beats the do-nothing baseline on corpus SARI.
3. Its attestation ceiling is reported, with the test shape justified.
4. It does not reduce grammaticality.
5. It is compared against at least one alternative method for the same family, because a method
   with no alternative has not been evaluated, only measured.

Point 5 is what `experiments/` exists to make cheap. Until several approaches to a family can be
run and scored in one command, "we tried X" means "we shipped X".

**Point 4 outranks the master metric, and this is not hypothetical.** Ranked on closure alone,
the best variant of the fitted deletion rule is the one with no shape priors at all: it scores
1.13% against the gated rule's 0.78% and introduces **eighteen** grammatical defects against
one (C17). Closure charges one word-operation for deleting a sentence's only verb and a reader
charges the whole paragraph, so the ordering it produces is wrong and the defect count and the
case bank are what correct it. Where the closure column and the defect column disagree, the
defect column decides.

**A backend that writes a replacement clears a different bar**, because it is scored at a site
somebody else chose. It must beat the `delete` anchor's span closure on the family it claims,
since dropping the span is free and already implemented, and it must be byte-reproducible under
section 8. Both are reported by `manage.py execute`; neither says anything about whether the
backend can decide where to fire, which is the licence question and is measured separately.

## 7. Rules for the evaluator itself

- **A check that cannot return false is a bug.** For every check, state the input that fails it,
  and assert that it does.
- **Never adjust a metric because it disagreed with the system under test.** Change it only on an
  independently stated defect, and record the change and its effect on every previously reported
  number.
- **Carry the do-nothing anchor inside every table, not in a footnote.** It is what makes the
  previous two rules operate on their own. The span-level probe was specified with a near-match
  measure, landing within one word of the gold; the `keep` anchor scored **39.1%** on it in the
  first run, because a one-word replacement is one word from its own source. The measure was
  dropped before any backend was judged on it, and no previously reported number used it.
- **Report the panel, not the best cell of it.**

## 8. The determinism contract

The README promises two things: nothing leaves the machine, and the same input gives the same
output. Neither requires the absence of a neural network, and treating them as if they did is
what capped this project at hand-written rules. A fixed-weight model decoded greedily satisfies
both. What it needs is a check.

- Model artefacts are pinned and verified by `manage.py install`, which reports and provisions
  nothing, as it already does for the spaCy model.
- A decoder runs at temperature 0, `top_k` 1, a fixed seed, a capped prediction length and a
  fixed context window. An encoder runs in eval mode at a pinned thread count, and any threshold
  is taken on a rounded score, because BLAS reduction order genuinely varies with thread count.
- What is asserted is the identity of the **output text**, not of the logits. The first is the
  property that matters and the second cannot be guaranteed.
- `manage.py execute --reproduce` runs two passes over the same spans and compares a SHA-256 of
  every replacement. It ships with the input that makes it fail: a decoder with sampling on,
  which must differ across runs or the check proves nothing.

Unproven as of C15: the control needs a local model server and there is none on this machine, so
the failing half of the check has not been exercised. The thread-count axis arrives with the
first encoder and not before, because nothing in the tier currently multiplies a matrix.

**A fitted model is now in the shipped lint path** (C17), so the second promise stopped being
free. `rules/rule_tagged.py` sums a weight per matching column, and float addition is
order-dependent, so the guarantee rests on the iteration order of two dictionaries: the feature
dictionary, whose keys are written in one place in source order, and `tagging/weights.py`, a dict
literal. Both are insertion-ordered in CPython and neither is built from a set or a hash-ordered
sequence, which is the mistake `evidence/align.py` already had to fix once. Checked rather than
argued: linting 60 held-out paragraphs under three values of `PYTHONHASHSEED` gives one SHA-256.

Scikit-learn is a fitting dependency, not a runtime one. `manage.py tag` writes plain numbers and
the engine reads them, so the linter's output does not move when the library version does.
