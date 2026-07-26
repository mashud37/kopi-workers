# Experimental approaches

One catalogue entry per lint issue in [typology.md](typology.md), listing the local
techniques worth trying against it. Each entry names candidate methods, what each needs,
and how it would be falsified. Nothing here is settled: this is the experiment queue.

Techniques are labelled by expected difficulty and by whether they are established
practice or a deliberate import from another field:

- **[S]** standard, known to work for this task
- **[A]** adaptation of a method built for a neighbouring task
- **[X]** experimental import from another discipline, unproven here

---

## 0. The thesis

kopi-learner distils Opus into **weights**. kopi-linter distils the same teacher into a
**grammar**.

That is the whole idea, and it changes what "deterministic" has to mean. Every previous
attempt in this workspace hand-authored rules and then discovered that hand-authored rules
capture almost nothing (0.3% of the corpus, see [typology.md](typology.md)). The corpus of
1,523 Opus edits is not just an evaluation set. It is a **rule source**. Syntax-based
statistical machine translation solved the equivalent problem in the 2000s: given aligned
tree pairs, extract the transformation grammar automatically. Nobody has pointed that
machinery at monolingual copy-editing with a frontier model as the teacher, because since
2020 the answer to everything has been to train weights instead.

So the architecture is:

```
parse -> propose (grammar) -> score (objective) -> select (search) -> realise -> guard
```

Five layers, each with its own literature, each independently testable. The rest of this
document is the technique catalogue per layer and per lint family.

---

## 1. Rule induction: getting the grammar without writing it

The highest-leverage bet in the project. If this works, the rule count goes from 165
hand-written entries to tens of thousands of corpus-attested transformations, and the
"comprehensive thesaurus for sentences" the project is reaching for exists.

### 1.1 GHKM rule extraction [X, high leverage]

Galley, Hopkins, Knight and Marcu (2004) extract minimal tree-to-string transformation
rules from aligned parse pairs. Given an alignment between an original tree and an edited
tree, the algorithm computes the **frontier set**: nodes whose spans do not cross the
alignment, then reads off the minimal rules rooted at each. Applied here, "participants
were given an alias" aligned with "we gave each participant an alias" yields a rule of the
form

```
(VP (auxpass be) (VBN GIVE) nsubjpass:X dobj:Y)  ->  (VP nsubj:AGENT (VBD GIVE) iobj:X dobj:Y)
```

with the lexical items abstracted to variables. That is a *general* passive-to-active rule
induced from one example, and it generalises to every verb the corpus attests.

- Needs: tree-to-tree alignment (see 1.2), a parse of both sides, variable abstraction.
- Falsified if: extracted rules are almost all fully lexicalised (no variables), meaning
  the corpus has no reusable structure. Test on a held-out document: what fraction of its
  edits are covered by rules induced from the others?

### 1.2 Tree edit distance for the alignment [S]

Zhang and Shasha (1989) give the classic O(n^2 m^2) ordered tree edit distance with an
explicit node mapping. That mapping is the input GHKM needs. Cheaper alternatives: leaf
alignment by lemma and then bottom-up projection, or the monotone bead alignment already
implemented in `evidence/align.py` extended to the token level.

### 1.3 Synchronous Tree Substitution Grammar [A]

STSG (and Smith and Eisner's 2006 quasi-synchronous grammar, which relaxes the strict
isomorphism assumption that real editing violates) is the formal object an induced rule
set actually is. Worth adopting the formalism explicitly rather than inventing a bespoke
rule format, because it comes with known parsing and composition algorithms.

### 1.4 Monolingual phrase tables [A]

Specia (2010) and Wubben, van den Bosch and Krahmer (2012) did text simplification as
phrase-based SMT. A phrase table mined from the Opus corpus is directly the "thesaurus
that swaps difficult sentences for simpler sentences" in the project brief. Store as
(source pattern, target pattern, count, precision, band distribution).

### 1.5 Bayesian rule confidence [S]

Every induced rule gets a Beta-binomial posterior over "when this pattern was available,
how often did Opus fire it". Rules apply only above a band-dependent posterior threshold,
so the clarity band fires only near-certain rules and the aggressive band fires the tail.
This is how the intensity bands become a property of the *rule set* rather than a prompt
string.

### 1.6 Confluence and termination checking [X]

Knuth-Bendix completion, from automated theorem proving. A rewrite system whose output
depends on rule application order is a latent bug, and no style linter checks for this.
Detect critical pairs (two rules whose left-hand sides overlap), and either order them
explicitly or add the joining rule. Cheap insurance that makes "deterministic" true rather
than aspirational.

---

## 2. The objective function: what counts as better

Flesch is the wrong objective. It sees only syllables per word and words per sentence, so
it is maximised by chopping prose into staccato fragments, which is exactly the failure
mode the kopi-editor prompt spends a whole rule forbidding. Replace it.

### 2.1 Dependency distance minimisation [X, strong candidate]

Gibson's Dependency Locality Theory (1998) and the cross-linguistic work of Futrell, Mahowald
and Gibson (2015) establish that summed dependency length predicts processing difficulty.
It is computable exactly from a parse, it is not gameable by chopping (a short sentence with
a long dependency still scores badly), and it directly rewards the transformations Opus
actually makes: moving a modifier next to its head, converting a nominalisation into a verb
adjacent to its arguments, absorbing a follow-on clause. Candidate primary objective.

### 2.2 Surprisal and Uniform Information Density [X]

Levy and Jaeger (2007): well-formed prose spreads information evenly. A token whose
surprisal under a local language model is near zero carries no information and is a
deletion candidate. This **derives** the filler list rather than hardcoding it, and it
generalises to the filler phrases nobody wrote down. Local model options: a KenLM 5-gram
trained on the author's own corpus (fast, tiny, fully deterministic), or a small masked LM
for pseudo-log-likelihood (better, slower, still local and still deterministic at fixed
weights).

### 2.3 Minimum description length [X]

The formal statement of the whole task: minimise the description length of the text subject
to preserving its proposition set. Useful mainly as a framing device that makes the
trade-off between compression and content explicit, and as a tie-breaker between candidate
rewrites of equal semantic coverage.

### 2.4 Classic complexity metrics as features [S]

Yngve depth, Frazier score, parse tree depth, mean clause length, subordination ratio,
nominalisation density, passive ratio, type-token ratio. Individually weak, collectively a
decent feature vector.

### 2.5 A learned linear scorer [S]

A structured perceptron or logistic regression over the features above, trained to rank
Opus's edit above the original and above the Qwen edit on the same paragraph. The corpus
has exactly the contrastive triples needed (1,490 paragraphs with both models' output).
Linear and fixed at inference, so the linter stays deterministic and inspectable.

---

## 3. Search: choosing which edits to make

Rules propose. Something has to decide which proposals survive, since they conflict: you
cannot both reduce a relative clause and de-nominalise its head.

### 3.1 Weighted interval scheduling [S]

Non-overlapping span selection maximising total score is the classic DP, exact and
O(n log n). Sufficient whenever proposals are span-local.

### 3.2 ILP sentence compression [A, strong candidate]

Clarke and Lapata (2008) formulate compression as integer linear programming over token
deletion variables, with grammaticality enforced by constraints derived from the dependency
tree (keep a head if you keep its dependent, keep both arguments of a preserved verb, and
so on). This fits the existing product contract exactly: the requested word reduction
becomes a budget constraint, and the band's compression ceiling becomes a second one. The
band system stops being a prompt stance and becomes a constraint set. Solvable with `pulp`,
`mip`, or by Lagrangian relaxation when speed matters.

### 3.3 Optimality Theory tableaux [X]

From phonology (Prince and Smolensky). Style constraints are **violable and ranked**, not
absolute: prefer the active voice, but not when it breaks topic continuity; prefer short
words, but not for a term of art. OT is the formalism built for exactly this shape of
problem, and the band system is naturally a **re-ranking** of the same constraint set
rather than four different rule sets. Genuinely untried in this domain as far as I know.

### 3.4 Beam search over rewrite sequences [S]

When edits interact non-locally (a merge changes what the next sentence's subject should
be), the DP formulation breaks. Beam over sequences of rule applications, scored by section 2.

### 3.5 Simulated annealing [A]

Fallback for the same case, cheaper to implement than a correct beam, and a useful oracle:
if annealing finds much better rewrites than the beam, the beam is too narrow.

---

## 4. Per-family technique catalogue

### 4.1 Voice (passive to active)

The hard part is not detection, it is **agent recovery**: "these were transcribed" has no
agent on the surface.

- **Agent from the `by`-phrase** [S]. Trivial, and rare in this corpus.
- **Agent from discourse antecedent** [A]. The previous sentence's subject, when the verb's
  semantic type accepts it.
- **Agent from the document's authorial voice** [X]. Estimate the author's self-reference
  ("we" vs "I" vs impersonal) from the document's own pronoun distribution, then supply it.
  This is provably what Opus does in the corpus (see the `voice/agent-restored` examples)
  and it is fully derivable locally with no model at all.
- **Licence gate: Centering Theory** [X, important]. Grosz, Joshi and Weinstein (1995).
  A passive is often the *right* choice because it keeps the backward-looking center in
  subject position. Compute the centering transition (CONTINUE, RETAIN, SMOOTH-SHIFT,
  ROUGH-SHIFT) for the candidate rewrite and reject the voice change when it degrades the
  transition. This is the missing intelligence in every naive style checker that flags
  every passive, and it is what makes the difference between a linter and a nag.
- **Realisation** [S]: subject-verb agreement, case on the inserted pronoun, verb inflection
  via `lemminflect`.

### 4.2 Nominalisation to verb

- **WordNet derivational links** [S]. `derivationally_related_forms` maps "anonymisation"
  to "anonymise". Already working in `evidence/taxonomy.py`.
- **NOMLEX** [A]. Macleod et al. (1998), a hand-built lexicon of nominalisations *with their
  argument mappings*: it records that the subject of "analyse" surfaces as the `by`-phrase
  or the possessive of "analysis". That mapping is precisely what is needed to rewrite
  "the analysis of X by Y" as "Y analysed X", and no amount of WordNet gives it. Freely
  available, unfashionable, and exactly right.
- **Corpus-mined argument mapping** [X]. Where NOMLEX is silent, induce the mapping from the
  Opus corpus itself: align nominal arguments to verbal arguments across the 1,523 pairs.

### 4.3 Support-verb and light-verb constructions

- **Structural detection** [S]: a semantically light verb (be, make, take, give, have,
  perform, conduct, provide) with an eventive noun object whose WordNet derivation is a verb.
  No keyword list needed beyond the closed light-verb class, which genuinely is closed.
- **Corpus-mined table** [S] from the induced grammar as a fallback for the idiomatic tail.

### 4.4 Lexical simplification

The classic three-stage pipeline, all local:

- **Candidate generation** [S]: WordNet synonyms (synonyms only, not hyponyms, which drift),
  plus the Opus-mined substitution table, plus PPDB if a local copy is acceptable.
- **Ranking** [S]: Zipf frequency (`wordfreq`), syllable count, and character length.
- **Context fit** [A]: does the substitute fit the sentence? Masked-LM pseudo-log-likelihood
  with a small local model, or a KenLM n-gram score, or a selectional-preference check via
  WordNet hypernyms of the verb's attested objects.
- **Term-of-art protection** [X, important]: a word is a term of art when its frequency in
  the document or discipline corpus vastly exceeds its frequency in general English. That is
  **log-likelihood keyness** (Dunning 1993), the standard corpus-linguistics instrument,
  used here as a safety gate. It replaces the impossible task of listing every discipline's
  vocabulary with a two-corpus statistic. Requires a reference corpus, which `wordfreq`
  effectively provides.

### 4.5 Figurative language

- **MIP operationalised** [X]. The Pragglejaz Group's Metaphor Identification Procedure
  compares a word's basic (concrete, bodily) sense with its contextual sense. Operationalise
  with the Brysbaert, Warriner and Kuperman (2014) concreteness norms, a free 40,000-word
  list: a concrete noun governing an abstract complement ("through the lens of an argument",
  "at the heart of the debate") is a dead metaphor. A crude WordNet `physical_entity`
  version is already prototyped in `evidence/taxonomy.py`.
- **Selectional preference violation** [A]: the verb's object is outside the distribution of
  objects that verb takes in a reference corpus.
- **Replacement** [S]: from the corpus-mined table, since the target of a metaphor removal
  is idiosyncratic ("through the lens of" becomes nothing at all, not a paraphrase).

### 4.6 Clause reduction and relative clauses

- **Whiz-deletion** [S]: "which were collected" becomes "collected". Purely structural,
  already partly in kopi-editor, and safe.
- **Finite clause to participial** [A]: "They spoke on X" absorbed as ", showing X".
  Template plus inflection; the licence condition is subject identity with the host clause.
- **Appositive reduction** [S]: "in the form of a randomly chosen name" becomes ", a randomly
  chosen name".

### 4.7 Sentence merge (the surprise finding)

Opus merges roughly eight times more often than it splits. The linter needs a real merge
capability, and the existing "split long sentences" instruction is close to backwards.

- **Detection** [S]: a short follow-on sentence whose subject is an anaphor (this, it, they,
  these) with an antecedent in the previous sentence, or which opens with an additive
  connective.
- **Licence** [X]: Centering again. Merge when the two sentences share a center.
- **Realisation** [A]: choose the connective by the discourse relation, which PDTB-style
  explicit connective classification can supply; then inflect and repunctuate.

### 4.8 Sentence dropping

Band-gated, and the highest-risk operation in the system.

- **Redundancy** [S]: already solved in kopi-editor with IDF-weighted overlap and MMR.
- **RST nuclearity** [A]: satellites are droppable, nuclei are not. A full local RST parser
  is heavy; the cheap proxy is explicit-connective classification plus a lexical-chain
  novelty score.
- **Proposition coverage** [X]: extract predicate-argument tuples from the parse, and permit
  a drop only when every tuple in the dropped sentence is subsumed by a retained one.
  This turns the guard from a similarity threshold into something closer to a proof.

### 4.9 Realisation and repair (15.6% of all transformations)

Not a lint family in itself. It is the layer that makes every other family safe, and the
evidence says it is the second-largest category of change in the corpus. Skipping it is why
naive rewriters produce ungrammatical output.

- Article selection (a/an by phonology; definiteness by discourse givenness) [S]
- Subject-verb agreement after a voice or number change [S]
- Verb inflection via `lemminflect` or `pyinflect` [S]
- Preposition repair after a head change [A]
- Capitalisation and terminal punctuation after a merge or split [S]
- Comma placement around a reduced clause [S]

### 4.10 Stance and hedging

The single most dangerous confusion in the domain: empty hedging must go, load-bearing
hedging must stay, and they look identical to a regex.

- **Structural separation** [A]: a stance adverb attached to the sentence root versus an
  epistemic modal inside the predicate. The first is usually removable, the second is
  usually the author's theoretical commitment.
- **Scope test** [X]: does removing the marker change the proposition's truth conditions?
  Approximate by asking whether the marker sits inside the scope of a reporting verb or a
  citation. "Miller (2011) suggests X" cannot lose "suggests".
- **Corpus evidence** [S]: the Opus corpus directly attests which markers were removed and
  which were kept, per band. Learn the distinction rather than legislate it.

---

## 5. Evaluation

Without this the project cannot tell success from self-deception.

- **SARI** [S] (Xu et al. 2016), the standard simplification metric, computed against Opus
  as the reference on kopi-learner's held-out split. Rewards correct keeps, adds and
  deletes separately, which is exactly the failure profile that matters here.
- **Word-delta to Opus** [S], the direct read on over- and under-cutting, already used by
  kopi-learner's `evaluate`.
- **Content-lemma retention** [S], already measured by the evidence miner.
- **Guard pass rate** [S], reusing kopi-editor's guard so numbers are comparable.
- **Band conformance** [S]: does the clarity band actually stay near zero reduction.
- **Per-rule precision** [S]: for each induced rule, how often did Opus make that edit when
  the pattern was available. This is the report that turns the rule set into science, and it
  is what tells you which rules to ship in which band.
- **Family ablation** [S]: disable one family, measure the SARI drop. Says where the value
  actually is, and therefore what to build next.

Baselines to beat, in order: the untouched original, kopi-editor's `proof` route (the
current deterministic state of the art here), and the served Qwen. Beating `proof` is the
minimum bar for the project to have earned its existence; beating Qwen is the real target.

---

## 6. Known hard core

Around one transformation in eight is a head-changing paraphrase: "would have been
transcribed as" becomes "became". No parse-driven rule reaches that, and the induced phrase
table will cover only the instances it has literally seen.

Three honest responses, in preference order:

1. **Measure it before conceding it.** The 13% figure is a count of *instances*, not of
   *value*. The ablation in section 5 will say how much SARI those instances actually carry.
   It may be much less than their frequency suggests.
2. **Mine it.** A phrase table from 1,523 edits is small, but the corpus can grow: every
   future kopi-editor run adds pairs at zero cost, and kopi-learner's `generate` route can
   expand it deliberately. The coverage curve over corpus size is itself the experiment.
3. **Route it.** A deterministic linter that handles the other seven eighths and flags the
   residual is already a large win, and it makes the LLM call smaller and cheaper rather
   than removing it. That is a fallback, not the goal, and it should not be reached for
   until 1 and 2 have been measured.
