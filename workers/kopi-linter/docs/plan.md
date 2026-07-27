# Plan and agenda

The one-line objective: **reproduce Opus's copy-editing deterministically, locally, and without a
model.** Everything below is scored against that and nothing else.

The measure is **closure**, defined in `good.md` §0: the per cent of the word-level distance from
the original text to Opus's edit that the linter has closed. Doing nothing is 0%, reproducing the
gold is 100%, and damage is negative. It is the only number this plan is written in.

---

## 1. Where we are

Measured over all 1,523 gold paragraphs (`manage.py evaluate`):

| System | closure | reach | accuracy |
|---|---:|---:|---:|
| do-nothing | 0.0% | 0.0% | n/a |
| **kopi-linter** | **0.3%** | 0.7% | 76.1% |
| served Qwen3-32B | -9.5% | 135.9% | 46.5% |

184 of 52,749 word-edits closed, 352 attempted.

**We are 0.3% of the way to Opus.** Corpus SARI says 0.5208 against a do-nothing 0.2439 and reads
like halfway. SARI pays for correct keeping, so a linter that touches 10% of paragraphs collects
most of its score for the 90% it left alone.

**Accuracy is fine and reach is the entire problem.** Three edits in four land on something Opus
also changed. That mechanism is applied to 0.7% of the work.

**Qwen is below the break-even line**, changing more than Opus did at under 50% accuracy, so its
output sits further from Opus's version than the untouched original. One honest caveat: closure
measures agreement with Opus, not quality, and a model that paraphrases well in its own voice is
punished for wording the same improvement differently. Quote that row as a reference point, never
as a verdict on Qwen.

## 2. The arithmetic that sets the strategy

Closure decomposes exactly:

    closure = reach x (2 x accuracy - 1)

At 50% accuracy closure is zero however much is attempted, which is the wrecking-ball result of
C11 restated as arithmetic. At today's 76.1%, **every point of reach is worth 0.52 points of
closure**. Hold accuracy above roughly 75% and buy reach; below 62% a point of reach is worth
under a quarter of a point, which is where a family stops being worth shipping.

**Watch the marginal accuracy, not the average.** The Phase 1 extension came in at 72.3% on its
new work against a 78.1% base. That is still well above break-even, but a family whose marginal
accuracy keeps sliding toward 50% is a family approaching its own ceiling, and the average will
hide that for a long time.

## 3. What each family is worth

Corrected 2026-07-26 (C1). Word movement is split by whether the target span is empty, per
finding, rather than by classifying whole families. Closure is denominated in **edit operations**,
of which the corpus holds 52,749; deleting a word costs one, so a family's reach ceiling is its
dropped words over 52,749. The linter's own run confirms the conversion, spending 352 operations
to remove 349 words.

| Family | dropped | rewritten | reach if fully covered | closure at 76% | words per decision |
|---|---:|---:|---:|---:|---:|
| `sentence` | 8,255 | 0 | 15.6% | 8.1 | 18.1 |
| `adjunct` | 5,640 | 734 | 10.7% | 5.6 | 3.3 |
| `clause` | 3,000 | 208 | 5.7% | 3.0 | 4.1 |
| `realisation` | 2,052 | 234 | 3.9% | 2.0 | 1.3 |
| `voice` | 1,895 | 1,137 | 3.6% | 1.9 | 4.1 |
| `phrase` | 1,215 | 5,961 | 2.3% | 1.2 | 2.9 |
| `relative-clause` | 1,001 | 42 | 1.9% | 1.0 | 5.4 |
| `stance` | 860 | 23 | 1.6% | 0.8 | 1.4 |
| `lexical` | 821 | 41 | 1.6% | 0.8 | 1.1 |
| `modifier` | 580 | 28 | 1.1% | 0.6 | 1.3 |
| **all deletion** | **25,930** | | **49.2%** | **25.6** | |
| **all rewriting** | | **11,692** | **22.2%** | **11.5** | |

Three things follow, and all three changed the plan.

**Deletion reaches 49.2 points, not 26.** `clause` at 94% deletion and `voice` at 62% were both
counted as generation families and are mostly Opus cutting. Only `phrase`, `support-verb` and
`nominalisation` genuinely need words written. The generation spine is further deferrable than
`constraints.md` claimed.

**Words per decision is the column to build against.** Every decision is a licence risk paid for
in accuracy, so a precision-limited engine should prefer families that move the most words per
risk taken. `sentence` moves 18.1 words per decision against `adjunct`'s 3.3, a 5.5x difference,
and `adjunct` is the family this project has spent most of its cycles on.

**The table cannot sum to 100%.** Deletion and rewriting together account for 71.4% of the
measured edit distance. The remaining 28.6% is reordering and insertion that the evidence layer
does not classify into families at all, and no family-by-family plan reaches it.

## 4. Phases

Each phase names the closure it should buy and the condition that makes it fail. A phase that
misses its number is a finding for `constraints.md`, not a target to relax.

**Phase 1, harvest what is built.** *Done, and smaller than forecast.* Closure 0.2% to **0.3%**.
The impure-span fix shipped at 72.3% marginal accuracy and probes at 41%; the three-times-larger
lexical-verb extension was refused at 0.6%, declined by Opus 169 times to 1 (C13). The family is
close to exhausted, because 96% of its gold word movement is Opus dropping the clause rather than
reducing it. The forecast of 1.5-3% was wrong for a reason worth keeping: it read a family's
*size* off the evidence table without asking what transformation those words belonged to.

**Phase 2, `sentence` dropping with a document-level allocator.** Promoted past `adjunct`. The
biggest family, pure deletion, and by far the best words-per-decision ratio. Dropping a sentence
is a discourse decision a paragraph cannot make alone, so it needs the C12b allocator, and that
is the work rather than the licence.
Target **4% to 8%**. Fails if allocation cannot beat a length-proportional quota, in which case
the ceiling is wherever Phase 3 lands.

**Phase 3, the adjunct licence.** The second-largest deletion family. C9 to C12 established what
does not work: a per-category drop rate cannot license, ranking is 1.88x random but only orders,
and a per-paragraph budget forces uniform cutting.
Target **3% to 5%**. Fails if accuracy on adjuncts cannot clear 70%, in which case the family is
recorded as unreachable.

**Phase 4, `clause` and `voice` deletion.** Both newly reclassified as mostly-deletion by C1, and
neither has been probed. Attestation probe first, per C13.
Target **2% to 4%**, taking the running total to roughly 10% to 17%.

**Phase 5, the generation spine.** 22.2% of the gap needs words written rather than chosen. Build
and test in isolation on gold triples before any family depends on it.
At 65% accuracy it buys 6.7 points, at 80% it buys 13.3.

**Terminal estimate: 30% to 50% closure**, dominated by whether generation accuracy clears 70%
and whether deletion accuracy holds near 80% as coverage grows. Basis: the family table above
with per-phase accuracy assumptions stated; estimates only. The residual is the 28.6% of edit
distance no family accounts for, the head-changing paraphrase core, and the fact that Opus is one
sample of a stochastic editor, so 100% is not available to anyone including Opus on a second pass.

## 5. Agenda

Ordered. Each item states what it should move, so it can fail.

1. ~~**Phase 1 harvest.**~~ Done. 0.2% to 0.3%.
2. ~~**Attestation probe as a subcommand**~~ (C13). Built: `manage.py probe <generator>`.
3. **Retro-probe section 3** before scheduling anything from it. Cheap, one parse pass per
   family, and C13 says to expect at least one more family to die the way the lexical-verb
   reduction did. Do this before Phase 2, not after.
4. **C5, the hand-checked damage set.** ~100 paragraphs judged against G1 to G3 by hand.
   **Blocking**, because closure rewards agreement with one editor and a rule that is right about
   Opus and wrong about English raises it. The three available precision readings for the shipped
   rule are 86% (ceiling), 76.1% (closure) and 41% (probe); they measure different things, and
   only a hand check says which is nearest to damage.
5. **C12b, document-level allocation.** Given a document and a requested reduction, choose which
   paragraphs absorb it. Prerequisite for Phase 2 and the first thing here that cannot be decided
   one paragraph at a time.
6. **Phase 2, sentence dropping.**
7. **C12a**, the high-precision restraint gate, folded into Phase 3 where it belongs.
8. **Phase 4 probes**, then **Phase 5** if the probes justify it.

## 6. How this plan fails

Stated in advance so it is recognisable when it happens.

- **Accuracy collapses as reach grows.** The likeliest failure, and Phase 1 already showed the
  shape: marginal 72.3% against an average of 78.1%. If marginal accuracy tracks toward 50% the
  approach caps out near where it is now.
- **Closure and quality come apart.** Closure rewards agreement with one editor. If the linter
  starts matching Opus's idiosyncrasies rather than improving prose, the hand-checked damage set
  is what catches it, which is why item 3 is blocking.
- **Family sizes keep overstating opportunity.** Phase 1's forecast was wrong by 5x because the
  evidence table names the construction involved, not the transformation applied. C13 is the
  general form of that error and the attestation probe is the general fix. Expect at least one
  more queued family to die the way the lexical-verb reduction did.
- **The unclassified 28.6% turns out to be where the work is.** Nothing in this plan addresses
  reordering and insertion, and no measurement has yet asked what is in there.

## 7. Standing rules

- `method.md` governs every increment: analyse, plan, build, evaluate, then analyse again.
- **Probe attestation before building a family.** Linguistic validity does not predict it (C13).
- Report closure with reach and accuracy beside it. The composite alone hides which half is broken.
- Never quote SARI as the headline. It is diagnostic, kept for the `add`/`keep`/`delete` split.
- A number that moves for a reason nobody can name is a defect, not a result.
