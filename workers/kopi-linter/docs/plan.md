# Plan and agenda

The one-line objective: **reproduce Opus's copy-editing deterministically, locally, and without a
model.** Everything below is scored against that and nothing else.

The measure is **closure**, defined in `good.md` §0: the per cent of the word-level distance from
the original text to Opus's edit that the linter has closed. Doing nothing is 0%, reproducing the
gold is 100%, and damage is negative. It is the only number this plan is written in.

---

## 1. Where we are

Measured 2026-07-26 over all 1,523 gold paragraphs (`manage.py evaluate`):

| System | closure | reach | accuracy |
|---|---:|---:|---:|
| do-nothing | 0.0% | 0.0% | n/a |
| **kopi-linter** | **0.2%** | 0.4% | 78.1% |
| served Qwen3-32B | -9.5% | 135.9% | 46.5% |

130 of 52,749 word-edits closed, 231 attempted.

Read those three columns together, because separately each one misleads.

**We are 0.2% of the way to Opus.** Corpus SARI says 0.5250 against a do-nothing 0.2439 and reads
like halfway. It is not halfway. SARI pays for correct keeping, so a linter that touches 7% of
paragraphs collects most of its score for the 93% it left alone. Closure removes that subsidy.

**Accuracy is already good and reach is the entire problem.** At 78.1%, near four edits in five
land on something Opus also changed. That is a working licence mechanism. It is applied to 0.4% of
the work.

**Qwen is below the break-even line.** 135.9% reach means it changes *more* than Opus did, at 46.5%
accuracy, which is under the 50% at which edits cancel out. Its output is further from Opus's
version than the untouched original. This needs one honest caveat: closure measures agreement with
Opus, not quality, and a generative model that paraphrases well in its own voice is punished for
wording the same improvement differently. Qwen at -9.5% does not mean Qwen writes worse English.
It means Qwen does not reconstruct Opus, which for this project is the objective and for Qwen is
not. Quote the Qwen row as a reference point, never as a verdict on Qwen.

## 2. The arithmetic that sets the strategy

Closure decomposes exactly:

    closure = reach x (2 x accuracy - 1)

At 50% accuracy closure is zero however much is attempted, which is the wrecking-ball result of C11
restated as arithmetic. At today's 78.1%, **every point of reach is worth 0.56 points of closure.**

So the plan has one shape. Hold accuracy above roughly 75% and buy reach. Trading accuracy for
reach is only worth it while `2a - 1` falls slower than reach rises, and below 62% accuracy a point
of reach is worth less than a quarter of a point, which is where a family stops being worth
shipping.

## 3. What each family is worth

From `output/evidence_opus.md`, 37,622 words moved by Opus across 22,631 transformations. Family
share of words moved is the best available proxy for reach share. The closure column applies the
0.56 multiplier at today's accuracy; it is a projection, not a measurement, and the conversion
from words moved to edit operations averages 1.40 and will vary by family.

| Family | words moved | share | reachable by deleting | closure if fully covered |
|---|---:|---:|---|---:|
| `sentence` | 8255 | 21.9% | yes, with a discourse licence | 12.3 |
| `phrase` | 7176 | 19.1% | no, needs generation | 10.7 |
| `adjunct` | 6374 | 16.9% | yes | 9.5 |
| `clause` | 3208 | 8.5% | no | 4.8 |
| `voice` | 3032 | 8.1% | no | 4.5 |
| `support-verb` | 2600 | 6.9% | no | 3.9 |
| `realisation` | 2286 | 6.1% | no, but it is forced by other edits | 3.4 |
| `relative-clause` | 1043 | 2.8% | yes, **built** | 1.6 |
| `stance` | 883 | 2.3% | partly | 1.3 |
| `lexical` | 862 | 2.3% | no | 1.3 |
| everything else | 1903 | 5.1% | mixed | 2.8 |

Two facts jump out of this table.

**The family we have already built is only a fifth harvested.** Relative-clause reduction is worth
1.6 closure points and has returned 0.2. The rule fires on 114 of 196 gold instances but moves 229
of 1,043 words, so it is catching the small instances and missing the large ones. Finishing a built
family is cheaper than opening a new one and it is the first thing to do.

**Deletion tops out at 26 points.** The deletion-reachable families sum to 17,418 words, 46.3% of
the total, which is C1 restated. At today's accuracy that ceiling is 26.0 closure points; at 90%
accuracy it is 37.0. Everything beyond that requires generating words, not choosing which to cut.

## 4. Phases

Each phase names the closure it should buy and the condition that makes it fail. A phase that
misses its number is a finding to write into `constraints.md`, not a target to relax.

**Phase 1, harvest what is built.** Extend relative-clause reduction to the instances it currently
declines, and add the deletion families with no licence problem: `intensifier`, `filler`,
`modifier`, hedge-side `stance`. Small, safe, mechanical.
Target **1.5% to 3%**. Fails if accuracy drops below 75%, which would mean the current 78% depends
on firing only on easy instances.

**Phase 2, solve the licence problem on adjuncts.** The largest deletion family that a parser can
reach. C9 to C12 established what does not work: a per-category drop rate cannot license, ranking
is 1.88x random but only orders, and a per-paragraph budget forces uniform cutting. What is left is
a real licence, which is the central research question of this project.
Target **6% to 10%**. Fails if accuracy on adjuncts cannot clear 70%, in which case the family is
recorded as unreachable and Phase 3 starts early.

**Phase 3, sentence-dropping with a document-level allocator.** The single biggest family at 21.9%.
Dropping a whole sentence is a discourse decision that a paragraph cannot make alone, which C12
proved rather than assumed. Requires the allocator from C12b.
Target **10% to 14%**, taking the running total to roughly 20% to 25%. Fails if allocation cannot
beat a length-proportional quota, which would put the ceiling at Phase 2's number.

**Phase 4, the generation spine.** Everything above stops at 46% reach. `phrase`, `support-verb`,
`voice`, `clause` and `realisation` are 48.6% of the words and all need words written, not chosen.
Build and test in isolation on gold triples before any family depends on it (C1).
Target depends entirely on generation accuracy, which is unmeasured. At 65% it buys 15 points, at
80% it buys 29.

**Terminal estimate: 40% to 60% closure**, dominated by whether generation accuracy clears 70%.
Basis: the family table above with per-phase accuracy assumptions stated; estimates only. The
residual is the ~14.3% head-changing paraphrase core that no parse-driven rule reaches, plus the
fact that Opus is one sample of a stochastic editor, so 100% is not available to anyone including
Opus on a second pass.

## 5. Agenda

Ordered. Each item states what it should move and by how much, so it can fail.

1. **Phase 1 harvest.** Relative-clause instances currently declined, then the four small deletion
   families. Expect closure 0.2% to 1.5-3%.
2. **C12a, the high-precision allocation gate.** Fire only where a strong candidate exists (0.755
   precision against a 0.609 base, on 47% of paragraphs). Cheap, result already in hand. Expect
   accuracy to hold while adjunct reach becomes usable for the first time.
3. **C5, the hand-checked damage set.** ~100 paragraphs judged against G1 to G3 by hand. Closure
   accuracy (78.1%) and the attestation ceiling (88.9%) disagree by ten points and only a hand
   check can say which is nearer the truth. Blocking for Phase 2, because a licence cannot be
   designed against a metric that cannot see damage.
4. **C12b, document-level allocation.** Given a document and a requested reduction, choose which
   paragraphs absorb it. The first thing here that cannot be decided one paragraph at a time.
5. **Phase 2 licence experiments**, several methods compared in one command per `method.md`.
6. **C1, the generation spine**, tested in isolation on gold `derivational-swap` triples first.

## 6. How this plan fails

Stated in advance so it is recognisable when it happens.

- **Accuracy collapses as reach grows.** The likeliest failure. 78.1% is measured on 231 word-edits
  and a sample that small from a single family cannot be extrapolated. If accuracy tracks reach
  downward toward 50%, the whole approach caps out near where it is now.
- **Closure and quality come apart.** Closure rewards agreement with one editor. If the linter
  starts scoring by matching Opus's idiosyncrasies rather than by improving prose, the hand-checked
  damage set is what catches it, which is why item 3 is blocking and not optional.
- **The generation spine does not reach 70%.** Then the project is a deletion tool with a 26 to 37
  point ceiling, and that should be said plainly rather than discovered slowly.

## 7. Standing rules

- `method.md` governs every increment: analyse, plan, build, evaluate, then analyse again.
- Report closure with reach and accuracy beside it. The composite alone hides which half is broken.
- Never quote SARI as the headline. It is diagnostic, kept for the `add`/`keep`/`delete` split.
- A number that moves for a reason nobody can name is a defect, not a result.
