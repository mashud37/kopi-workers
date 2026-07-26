# Typology of lint issues

What a deterministic plain-language linter for academic prose actually has to do, derived
from measurement rather than intuition.

**Source.** 1,523 paragraphs edited by Opus across 25 documents and four intensity bands,
mined from kopi-learner. Aligned into 7,355 sentence beads and 22,631 span-level
transformations by `evidence/`. Regenerate with `python manage.py evidence --role opus`;
the full report is `output/evidence_opus.md`.

**Scope note.** One teacher, one author, one discipline. The counts describe this editing
task accurately and are not a general account of English prose.

---

## 1. The three findings that set the agenda

### 1.1 The existing rule set is not a partial solution

kopi-editor ships 165 deterministic rules: 103 filler phrases, 19 clichés, 19 word
substitutions, 24 padding-tail patterns. Across 22,631 gold transformations they account
for **44**.

| | |
|---|---:|
| Transformations Opus made | 22,631 |
| Reachable by the current rule tables | 44 |
| Coverage | **0.2%** |

The conclusion is not that rules are hopeless. It is that *phrase-substitution tables* are
the wrong instrument, and every previous deterministic attempt in this workspace reached
for that instrument. Fixed-string substitution addresses a rounding error. The work is
structural.

### 1.2 Frequency and impact rank the problem differently

Counting instances puts lexical work first. Counting the words a family actually moves puts
structural work first, and the two orderings barely agree.

| Family | Instances | Share | Words moved | Words per instance |
|---|---:|---:|---:|---:|
| `sentence` (dropping) | 457 | 2.0% | **8,255** | 18.1 |
| `phrase` (paraphrase) | 6,026 | 26.6% | 7,176 | 1.2 |
| `adjunct` | 1,958 | 8.7% | 6,374 | 3.3 |
| `clause` | 781 | 3.5% | 3,208 | 4.1 |
| `voice` | 1,176 | 5.2% | 3,032 | 2.6 |
| `support-verb` | 1,206 | 5.3% | 2,600 | 2.2 |
| `realisation` | 3,843 | 17.0% | 2,286 | 0.6 |
| `relative-clause` | 196 | 0.9% | 1,043 | 5.3 |
| `stance` | 628 | 2.8% | 883 | 1.4 |
| `lexical` | 2,870 | 12.7% | 862 | 0.3 |
| `modifier` | 456 | 2.0% | 608 | 1.3 |
| `punctuation` | 1,627 | 7.2% | 369 | 0.2 |
| `figurative` | 70 | 0.3% | 336 | 4.8 |
| `nominalisation` | 176 | 0.8% | 333 | 1.9 |
| `connective` | 729 | 3.2% | 98 | 0.1 |
| `filler` | 44 | 0.2% | 86 | 2.0 |
| `intensifier` | 70 | 0.3% | 71 | 1.0 |
| `morphology` | 318 | 1.4% | 2 | 0.0 |

Total words moved across all families: 37,622.

This settles a design question that would otherwise be argued about. kopi-editor's product
contract is a **word budget** ("remove about 1,000 words"), so the linter must be built
around the high-impact structural families. Lexical substitution is 12.7% of the activity
and 2.3% of the words: it makes prose plainer, it does not make it shorter. The two goals
need different machinery and the band system already distinguishes them.

### 1.3 Intensity re-weights the same families, it does not change them

Every band draws on the same repertoire. What moves is the mix.

| Family | clarity | light | firm | aggressive | Direction |
|---|---:|---:|---:|---:|---|
| `adjunct` | 7.1% | 5.6% | 8.9% | 9.6% | rises |
| `support-verb` | 4.3% | 3.0% | 5.3% | 6.2% | rises |
| `clause` | 2.8% | 2.8% | 3.5% | 3.8% | rises |
| `modifier` | 1.4% | 1.6% | 2.0% | 2.4% | rises |
| `sentence` | 1.7% | 0.8% | 2.1% | 2.3% | rises |
| `lexical` | 14.2% | 18.1% | 12.4% | 11.6% | falls |
| `voice` | 6.3% | 6.7% | 5.1% | 4.6% | falls |
| `connective` | 4.0% | 4.2% | 3.3% | 2.6% | falls |
| `stance` | 3.2% | 3.5% | 2.5% | 2.8% | falls |

No family appears only in the aggressive band and none disappears in clarity. That means
intensity is a **re-ranking of one constraint set**, not four rule sets, which is a strong
architectural constraint on anything built next, and an unusually direct piece of evidence
for the ranked-constraint approach in [approaches.md](approaches.md) section 3.3.

### 1.4 The gap between the cheap model and the gold is restraint and repair, not vocabulary

The corpus holds the served Qwen's edit of the *same* paragraph at the *same* band for
almost every gold edit. Running the identical analysis over both (`--role qwen`,
`output/evidence_qwen.md`) isolates what the expensive editor supplies.

Sentence operations, as a share of beads:

| Operation | Opus | Qwen | |
|---|---:|---:|---|
| `rewrite` | 71.4% | 61.3% | |
| `keep` | 12.5% | 8.4% | Qwen leaves a third fewer sentences alone |
| `merge` | 7.2% | 6.0% | |
| `delete` | 6.2% | **14.5%** | Qwen cuts whole sentences 2.3 times as often |
| `split` | 2.6% | **9.8%** | Qwen splits 3.8 times as often |

Span families, Qwen's share relative to Opus's:

| Qwen does markedly less | ratio | Qwen does markedly more | ratio |
|---|---:|---|---:|
| `connective` | 0.57x | `sentence` (dropping) | 2.07x |
| `nominalisation` | 0.58x | `figurative` | 1.62x |
| `punctuation` | 0.72x | `intensifier` | 1.36x |
| `realisation` | 0.74x | `support-verb` | 1.32x |
| `voice` | 0.78x | `relative-clause` | 1.31x |
| `clause` | 0.83x | `phrase` (paraphrase) | 1.19x |

Read together: Qwen reaches for the blunt instruments (drop the sentence, split the
sentence, paraphrase freely) and neglects the careful ones (repair the function words,
manage the connectives, recover the agent, unpack the nominalisation). It edits more, 26,092
transformations against 22,631, and edits worse.

This is the most encouraging result in the analysis, because the deficit is not where a
rule-based system is weak. **Restraint, repair and flow management are precisely what
deterministic machinery does well**, and free paraphrase, the one thing rules genuinely
cannot do, is something Opus does *less* of than the cheap model, not more. The gap the
linter has to close is not "understand the argument". It is "know when to stop, and clean
up after yourself".

---

## 2. Sentence-level operations

What happens to a sentence as a whole, over 7,355 aligned beads.

| Operation | Count | Share | Meaning |
|---|---:|---:|---|
| `rewrite` | 5,251 | 71.4% | rewritten in place |
| `keep` | 923 | 12.5% | returned untouched |
| `merge` | 530 | 7.2% | absorbed into a neighbour |
| `delete` | 457 | 6.2% | cut outright |
| `split` | 194 | 2.6% | became several sentences |

**L1. Restraint.** One sentence in eight comes back untouched. Deciding *not* to edit is a
first-class operation and the one a linter is structurally worst at, since a rule that
matches fires. In the clarity band restraint is most of the job.

**L2. Merge, and the split assumption.** Opus merges 530 times and splits 194: absorption
outnumbers division **2.7 to 1**. kopi-editor's diagnosis raises a `long-sentence` tag
whenever mean sentence length exceeds 40 words and instructs the model to split. The gold
data says splitting is the rarer move, and that plain language here is achieved mostly by
subordination and absorption. The existing tag is not wrong, but it is aimed at the minority
case and it has no counterpart aimed at the majority one.

Merge subtypes worth separate rules: coordinate merge; relative-clause absorption;
participial absorption ("They spoke on X" becoming ", showing X"); appositive absorption
("in the form of a randomly chosen name" becoming ", a randomly chosen name").

**L3. Deletion.** 457 sentences dropped, moving 8,255 words, the single largest source of
reduction in the corpus. Band-gated and the highest-risk operation in the system.

> This figure was wrong on the first pass. A monotone aligner cannot distinguish "two
> sentences became one" from "one was cut and its neighbour kept", so deletions were
> initially reported as merges and `delete` read as 1. `_split_out_deletions` in
> `evidence/align.py` corrects it by promoting a source sentence whose content lemmas fail
> to survive; on a 400-edit probe that reclassified 23% of merge-bead sources.

**L4. Split.** Rare, and worth a real licence condition rather than a length threshold.

---

## 3. Span-level families

Ordered by words moved, since that is what the product contract measures.

### 3.1 `sentence`: dropping a whole sentence
457 instances, 8,255 words, 18.1 words each. Band-gated: 1.7% of clarity activity, 2.3% of
aggressive. Requires a redundancy or nuclearity judgement plus a guarantee that no
proposition is lost. kopi-editor already has the redundancy half (IDF-weighted overlap and
MMR selection); it has nothing for the "marginal but not repeated" case.

### 3.2 `phrase`: paraphrase
6,026 instances, 7,176 words. The irreducible core, and the honest problem.

| Subtype | n | What it is |
|---|---:|---|
| `paraphrase-compression` | 1,996 | shorter rewrite, head changed |
| `paraphrase-rewrite` | 1,232 | same length, different words |
| `recategorised-compression` | 793 | derivationally related head, different category |
| `material-introduced` | 705 | two or more new content lemmas |
| `material-inserted` | 622 | new function-bearing material |
| `phrase-dropped` | 461 | multiword span cut |
| `phrase-reordered` | 141 | same lemmas, new order |
| `head-preserved-compression` | 76 | target lemmas a subset of source |

`recategorised-compression`, `phrase-reordered` and `head-preserved-compression` (1,010
instances) are parse-reachable. `paraphrase-compression` and `paraphrase-rewrite` (3,228
instances, 14.3% of all transformations) are not: "would have been transcribed as" becoming
"became" requires knowing what the sentence means. That 14.3% is the number the project has
to beat, work around, or route.

### 3.3 `adjunct`: prepositional phrases
1,958 instances, 6,374 words, and the largest *tractable* family by impact.

| Subtype | n |
|---|---:|
| `prepositional-phrase-dropped` | 1,802 |
| `prepositional-phrase-to-deictic` | 129 |
| `prepositional-phrase-to-adverb` | 18 |
| `of-phrase-to-genitive` | 9 |

Dropping a PP is structurally trivial to *propose* and hard to *licence*: adjuncts are
removable, arguments are not, and the parse distinguishes them imperfectly. This family is
where the highest-value early experiment sits.

### 3.4 `clause`: predicate absorption and clause dropping
781 instances, 3,208 words. `predicate-absorbed` (654) turns a finite clause into a
participial or appositive; `clause-dropped` (127) removes it.

### 3.5 `voice`: passive to active
1,176 instances, 3,032 words. `passive-auxiliary-dropped` 483, `passive-to-active` 460,
`agent-restored` 233. Three distinct sub-problems: detecting the passive (easy), recovering
an agent that is usually absent from the surface (hard), and deciding whether the change is
desirable at all (hardest, and a discourse question rather than a syntactic one). Note the
band gradient runs *downward*: voice work is a clarity-band activity.

### 3.6 `support-verb`: light-verb constructions
1,206 instances, 2,600 words. "make use of" to "use", "referred to X by name" to "named X",
"is supportive of" to "supports". Rises with intensity.

> **Correction, from building the rule.** This family is over-stated, and the label is
> misleading. `verb-phrase-to-verb` (1,145 of the 1,206) is a mixed bag of verb-phrase
> paraphrase that happens to end in a single verb, not the classic light-verb construction;
> the genuine article is `light-verb-to-lexical-verb`, 61 instances, 0.3%. Measuring
> directly (`manage.py induce`) found 1,006 light-verb constructions in the originals of
> which the gold editor resolved away 203, a **20% base rate**, and that is an upper bound
> since a noun also disappears when the sentence was rewritten for other reasons. A rule
> built on this family fired twice across the whole corpus after its confidence was
> calibrated to that evidence, and disagreed with Opus both times. It is withdrawn.
> Classification by target shape over-attributes to whichever family the target resembles;
> the other families' counts should be read with the same suspicion.

### 3.7 `realisation`: repairs forced by other edits
3,843 instances, 17.0% of all transformations. Function words dropped (1,719), swapped
(1,437) and inserted (687): articles, prepositions, agreement, case.

Not a lint issue in itself, and that is exactly why it matters. It is the second-largest
category in the corpus, it is a pure consequence of the other families, and skipping it is
the standard reason rule-based rewriters produce ungrammatical output. It must be its own
architectural layer rather than a detail inside each rule.

### 3.8 `relative-clause`
196 instances, 1,043 words, 5.3 words each, the highest per-instance yield of any span
family. Whiz-deletion ("which were collected" to "collected") is safe and mechanical.
Under-used relative to its payoff.

### 3.9 `stance`: hedging and sentence adverbs
628 instances, 883 words. The most dangerous family in the typology: empty hedging must go,
load-bearing hedging is the author's theoretical commitment and must stay, and the two are
indistinguishable by surface form. kopi-editor's prompt devotes a hard rule to protecting
"may, might, suggests, arguably". A linter needs that protection to be structural.

### 3.10 `lexical`: word-level substitution
2,870 instances but only 862 words. `long-to-plain` 1,454, `word-dropped` 810,
`synonym-swap` 504, `derivational-swap` 102. High frequency, low word impact, high
visibility. The blocking sub-problem is not candidate generation but **term-of-art
protection**: an academic text is full of long Latinate words that must not be simplified.

### 3.11 `modifier`, `intensifier`, `determiner`
526 instances, 679 words. Adjectival and adverbial adjuncts, degree adverbs. Mechanical.

### 3.12 `figurative`
70 instances, 336 words, 4.8 words each. Dead spatial and bodily metaphor: "through the
lens of", "a window opening up onto", "at the forefront of". Rare, high yield per instance,
and the kind of thing the current cliché table gestures at with 19 entries.

### 3.13 `nominalisation`
176 instances, 333 words. "Data anonymisation consisted of" becoming "We anonymised the
data". The textbook plain-language transformation, and notably *rarer* in practice than its
prominence in style guides suggests. Flat across bands.

### 3.14 `connective` and `morphology`
1,047 instances, 100 words. Connective swaps ("Therefore" to "So", "Firstly" to "First") and
inflection changes. Nearly free in word terms; they are what makes an edit read naturally
rather than shorter, and `connective-inserted` (316) is largely the cost of merging.

### 3.15 `filler`
44 instances. The solved case. Kept in the typology only to keep its size visible.

---

## 4. Discourse-level issues

Above the paragraph, not directly measurable by span alignment, and each one a way a
locally correct edit can be globally wrong.

- **D1 Redundancy across sentences.** Already implemented in kopi-editor via IDF-weighted
  overlap and marginal-novelty selection. Reusable as-is.
- **D2 Topic continuity.** A passive often exists to keep the topic in subject position.
  Flipping it to active can break the theme chain even though the sentence improves in
  isolation. The most likely cause of a linter that is right sentence by sentence and wrong
  paragraph by paragraph.
- **D3 Connective coherence.** Dropping or merging a sentence can strand "Therefore" or
  "However" with nothing to point back to.
- **D4 Anaphora integrity.** A pronoun whose antecedent was deleted or absorbed.
- **D5 Terminology consistency.** A term of art simplified in one paragraph and not the
  next is worse than not simplifying it at all.
- **D6 Budget allocation.** Which paragraphs absorb a requested document-level cut. Currently
  a per-paragraph floor plus a top-up pass; properly a global allocation problem.

---

## 5. Invariants the linter must never break

Carried over from kopi-editor's guard, plus what the evidence adds.

| | Invariant | Status |
|---|---|---|
| G1 | Citations `(Author, Year)` preserved exactly | implemented in kopi-editor |
| G2 | Numbers preserved | implemented |
| G3 | Quotations never edited | implemented |
| G4 | Genuine hedging preserved | prompt-level only, needs a structural test |
| G5 | Terms of art preserved | prompt-level only, needs a keyness test |
| G6 | British spelling preserved | implemented |
| G7 | Content preserved within the band's tolerance | **needs recalibration, see below** |
| G8 | No new content invented | free for a rule-based system, and a real advantage |

**G7 needs recalibration.** Median content-lemma loss per rewritten sentence, measured:

| Band | Median content loss | Sentences |
|---|---:|---:|
| clarity | 8.3% | 1,769 |
| light | 7.1% | 309 |
| firm | 14.3% | 2,087 |
| aggressive | 18.2% | 1,810 |

A clarity pass, which is defined as "not a reduction", still loses about 8% of content
lemmas. Content preservation is not a threshold to hold at zero; it is a band-dependent
budget, and these are the numbers to set it from.

G8 is worth stating plainly because it inverts the usual trade-off. A deterministic
rewriter cannot hallucinate. The guard's job stops being "did the model drift?" and becomes
"is this transformation licensed?", which is a decidable question rather than a similarity
threshold.

---

## 6. What this typology tells the build order

1. **`realisation` is a layer, not a rule.** 17% of transformations, forced by the others.
   Nothing else can be built safely first.
2. **Structural families carry the word budget.** `sentence`, `adjunct`, `clause`, `voice`,
   `support-verb`, `relative-clause`: 5,774 instances, 24,512 words, 65% of everything moved.
3. **Lexical work is a separate product.** High frequency, low word impact, blocked on
   term-of-art protection rather than on candidate generation.
4. **Restraint needs its own mechanism.** 12.6% of sentences are correctly left alone and
   nothing in a rule-firing architecture produces that by default.
5. **Merge before split.** Absorption outnumbers division 2.7 to 1 and the current design
   has a rule only for the minority case.
6. **14.3% is the honest ceiling for parse-driven rules**, and section 6 of
   [approaches.md](approaches.md) says what to do about it before conceding it.
