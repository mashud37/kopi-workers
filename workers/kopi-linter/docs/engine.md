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
| `align.py` | Gale and Church (1993) bead alignment, run monolingually; beads relabelled 1-1 rewrite / 1-n split / n-1 merge / 1-0 cut | running | 1,490 paragraphs, 22,279 transformations |
| `align.py` | Needleman-Wunsch DP over the monotone grid, fanout capped at 3 | running | exact given the cost model |
| `align.py` | IDF-weighted content-lemma containment as the bead cost, replacing the character-length prior that is meaningless monolingually | running | cost model is a choice, not validated |
| `align.py` | `_split_out_deletions`: promotes a source sentence to a deletion when its content lemmas fail to survive, which Gale and Church cannot express | running | reclassified 23% of merge sources on a 400-edit probe |
| `align.py` | Sorted-order float summation to defeat Python hash randomisation flipping DP ties | running | identical output over 3 processes |
| `taxonomy.py` | Ordered cascade: dependency relations, WordNet derivational morphology, `wordfreq`, concreteness | running | no held-out accuracy figure |
| `taxonomy.py` | MIP (Pragglejaz) operationalised as a WordNet `physical_entity` concreteness test for dead metaphor | running | unvalidated |
| `editor_rules.py` | Coverage bridge to kopi-editor's 165 production rules | running | 44 of 22,279 transformations (0.2%) |
| `induce.py` | Rule confidence induced from the gold's own behaviour rather than asserted | running | light-verb base rate 20.2%, 1,006 observations |

## 2. Engine (`lint/`)

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `run.py` | Six stages: parse, propose, select, apply, realise, guard | running | 1,490 paragraphs |
| `registry.py` | Rules propose only; nothing applies until every proposal is seen, so output is independent of rule order | running | property holds by construction |
| `registry.py` | Failures surfaced, never swallowed | running | added after a broken rule looked identical to a quiet one |
| `select.py` | Weighted interval scheduling, exact DP with `bisect` predecessors, over conflicting proposals | running | exact; untested against a greedy baseline |
| `bands.py` | Per-family confidence thresholds over one rule set, not four rule sets | running | thresholds hand-set, not induced |
| `bands.py` | Family threshold read as a real probability, from the fitted tagger | running | one row per band from the operating table, 0.60 to 0.90 |
| `guard.py` | Citation set, number preservation, band floor, non-empty | running | all four passed on a known-broken output |
| `guard.py` | Quoted spans protected from rule proposals | running | did not protect against the realiser until 2026-07-26 |

## 2a. The hand-checked damage set (`damage/`)

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `sheet.py` | Every changed held-out paragraph laid out with its edits, the gold and the triage class | running | 95 paragraphs, 132 edits |
| `verdicts.py` | One hand verdict per edit id, kept in the tree so the rate can be recomputed | running | 9% of changed paragraphs damaged, one judge |
| `report.py` | Rate by criterion, by band, by who attests the edit, and by deleted word | running | aggressive 13%, firm 2%, clarity 0% |

## 3. Transformation families (`rules/`)

| Family | Status | Fired | Attestation |
|---|---|---|---|
| `tagged` deletion, fitted per token | running | 693 | **ceiling 83.7%** |
| `tagged` rewriting, closed phrase table | running | 127 | **ceiling 73.2%**, the first rule that writes |
| `relative-clause` reduction (whiz-deletion) | running | 114 | **ceiling 89%**, previously misreported as 100% |
| `support-verb` collapse | withdrawn | 2 | disagreed twice; 20% base rate did not support firing |
| `adjunct` PP-drop, structural licence | built, rejected | 647 | **2%** ceiling; over-fires, see constraints C9 |
| `adjunct` PP-drop, induced licence (3 variants) | built, rejected | 3 | cannot reach any band threshold, see C9 |
| `voice` auxiliary dropped, probe only | probed, refused | 1,725 proposed | **2.5%** attested of 281 decidable, see C27 |
| `clause` dropped, probe only, adverbial and complement | probed, refused | 3,332 proposed | **0%** attested of 775 decidable, see C27 |
| `sentence` dropped, fitted per sentence | fitted, refused | 0 above 0.5 | **8%** precision against a 5.5% base rate, see C26 |
| `voice` restoration | paper | | 1,156 / 2,988; the agent-restoring half is untouched |
| `nominalisation` to verb | paper | | |
| `sentence` merge and cut | paper | | 454 instances / 8,212 words, the largest by word budget |
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

## 6. Local execution tier (`execute/`)

Producers for `Edit.replacement`, which C1 found nothing ever fills. Measured at gold sites
only: the probe hands over the span and asks for the wording, so none of these has yet been
asked to decide where to fire.

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `oracle.py` | One task per gold span edit, scored as span-level closure against Opus's own target | running | 20,243 spans over 1,490 paragraphs |
| `oracle.py` | `keep` and `delete` carried as anchors in every table, so a degenerate measure shows itself | running | caught the near-match defect, C15 |
| `template.py` | Plain code: drop the span, or respell it | running | **0.2%** of the rewriting gap; refused |
| `ceiling.py` | Closed edit vocabulary induced from the training documents, plus generated inflection | running | ceiling **52.6%** rewriting closure, 970 phrases |
| `decoder.py` | Small instruct model, greedy at fixed seed, over the served vLLM or a local Ollama | built, unverified | **unmeasured**: no endpoint configured, no Ollama here |
| `backends.py` | One dict registry; a backend is `prepare` plus `execute`, no classes | running | |
| `cli/execute_cmd.py` | `--reproduce`: two passes, byte-identical, with a sampling control that must fail | built, unverified | control needs Ollama; free backends match |

The `ceiling.py` row reads the gold and is a ceiling, never a system score. It answers one question:
if every tag choice were correct, how much of what Opus wrote could a closed vocabulary spell?

## 7. Edit tagging (`tagging/`)

The licence and the execution asked as one question, per token.

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `vocabulary.py` | LaserTagger-shape tags: keep or delete each source word, plus a phrase written before it | running | 205,800 words, 0 paragraphs unalignable |
| `vocabulary.py` | Phrase vocabulary induced from training documents, coverage curve against held-out need | running | 975 phrases cover 62.6%; 27 cover 25.2% |
| `features.py` | 17 parse and frequency features per word, no embeddings | running | 6,136 columns after one-hot |
| `fit.py` | Logistic regression over keep-or-delete, scored on held-out documents | running | **64.9%** precision at 0.60, against 25.2% guessing |
| `fit.py` | Projected closure per threshold, so the operating point is chosen in the project's own metric | running | best 4.5%, an upper bound |
| `fit.py` | Feature-group ablation, each group removed and each on its own | running | length alone fires on 0 of 31,464 words |
| `model.py` | Weights written out as a generated module and scored with a dot product, so the engine reads no scikit-learn | running | 6,136 columns, round-trips exactly |
| `phrases.py` | Phrase head as a closed table keyed on the span's text, no model | running | 348 entries, 81.4% exact on held-out spans |
| `encoder.py` | A frozen sentence encoder giving every word its contextual vector, one thread, eval mode | measured, not wired | 384 columns, **43.1%** precision alone |
| `heads.py` | The same decision fitted on the one-hot bag, on the encoder, and on both | measured, not wired | projected closure 4.5%, -0.3% and **5.4%** |

## 7a. Document-level decisions (`document/`)

Both of these are measurements that shipped nothing. They are in the tree because the roadmap's
remaining reach rested on them and the result was negative, which is a thing the engine has to be
able to state.

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `allocate.py` | A document's reduction split across its paragraphs, five ways, against Opus's own split | measured, refused | length-proportional **84.6%**, every model variant below it |
| `sentences.py` | Whether the gold editor drops a sentence, fitted over size, discourse and internal features | measured, refused | never reaches 0.5; **8%** at the top of the ranking |
| `sentences.py` | The same decision read as a ranking, since the class is 5.5% of sentences | measured, refused | every depth loses words, -986 at 100 drops |

## 8. The tagger as a rule (`rules/rule_tagged.py`)

| Component | Technique | Status | Measured at |
|---|---|---|---|
| `rule_tagged.py` | Per-word score, neighbouring words grouped into one span, probability carried as the edit's confidence | running | 118 fired on 233 held-out paragraphs, 86% attested |
| `rule_tagged.py` | Five shape priors, each registered as an ablation and each measured | running | damage in **48% of changed paragraphs down to 12%**; no ablation survives its cases |
| `rule_tagged.py` | A prior holds one word back and the rest of the run is still deleted | running | dropping the whole run instead costs 0.13 closure points |
| `rule_tagged.py` | The phrase table writes where the model licensed the span | running | closure 0.89% to 0.98%, accuracy 69.5% to 73.9% |
| `grammatical.py` | `subjectless_verb`, for the shape a deleted expletive leaves | running | caught 1 real defect and 1 false positive on a reparsed long sentence |
| `grammatical.py` | `orphaned_determiner`, keyed on the fine tag because the dependency layer relabels the damage away | running | 3 to 0; see C17 |

## 9. Headline numbers, with their caveats

Corpus SARI over 1,490 gold paragraphs:

| System | SARI | add | keep | delete |
|---|---:|---:|---:|---:|
| do nothing | 0.2433 | 0.0000 | 0.7298 | 0.0000 |
| kopi-linter | 0.5489 | 0.0097 | 0.7349 | 0.9022 |
| served Qwen3-32B | 0.5125 | 0.2040 | 0.7111 | 0.6224 |

Read with section 5.4 of `good.md`: the linter changes **658 of 1,490 paragraphs (44.2%)** and
moves **1,061 words against Opus's 22,816**. It passes a 32B model on the composite while doing
under five percent of the work, which is the clearest possible argument for never reporting the
composite alone.

Closure by split, which is the number that says whether any of this generalises:

| Split | Paragraphs | Closure | Reach | Accuracy |
|---|---:|---:|---:|---:|
| train | 1,257 | 1.3% | 2.7% | 73.3% |
| test (held out) | 233 | **1.1%** | 2.5% | 73.0% |

The tagger is fitted on the train documents and scores the same on documents it never saw, which
is the point of the row. It also answers C14: the held-out side used to rest on 14 edits and
could not separate 68% from 77%, and it now carries hundreds.

The `add` column moved for the first time, from 0.0052 to 0.0097, and it is still where the gap
is: Qwen scores 0.2040 there. The phrase table can only write at a site the deletion model
already licensed, so the rest of that column is behind allocation and sentence dropping rather
than behind more writing (`constraints.md` C23).
