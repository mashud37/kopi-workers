# What good looks like

This memo defines success before any method is proposed, because the project has already been
burned once by the alternative. A rule was built, scored against a check that could only return
"pass", and reported at 100% agreement. The number was structurally guaranteed and meant nothing.

Everything here is written so that a method can **fail** it. A criterion that no input can
violate is not a criterion, and it does not belong in this file.

---

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
| `the resource **that people can** use creatively` | deleting the span destroys the modal | fixed, `_deletes_only_copula` |
| `practices **that are increasingly** personalised` | deleting the span destroys the adverb and with it a claim | fixed, same gate |
| `the theory **that is** central` | bare adjective cannot follow the noun | fixed, complement required |
| `the data **which we** collected` | relativiser is the object, not the subject; deleting it strands the verb | fixed, `_SUBJECT_DEPS` gate |
| `the claim, **which is** false, was repeated` | non-restrictive; reduction changes the clause's relation to the head | untested |

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

No single number. A method is reported on all of these, and a gain on one that costs another is
a finding to state, not a win to report.

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
moved. The linter's current 12.4% and 298 words against 23,047 is the real headline, and it is
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

## 7. Rules for the evaluator itself

- **A check that cannot return false is a bug.** For every check, state the input that fails it,
  and assert that it does.
- **Never adjust a metric because it disagreed with the system under test.** Change it only on an
  independently stated defect, and record the change and its effect on every previously reported
  number.
- **Report the panel, not the best cell of it.**
