# Why this tune clears the gate

The learning policy gates fine-tuning behind four preconditions ([learning.md](../../00_policies/learning.md) §3.1)
and requires recording *why* the gate was opened. This is that record.

| Precondition | Status |
|---|---|
| **1. Narrow, stable, well-specified task** | ✓ Plain-language copy-editing of one academic paragraph at a requested intensity: a fixed transform with a fixed prompt contract (`kopi-editor/kopi/llm.py`). Not a moving target. |
| **2. Prompting + few-shot + RAG demonstrably plateaued** | ✓ for the *capability* gap, not just asserted. The prompt was iterated to the banded-intensity design; the residual failure is **semantic editorial judgement** (over-/under-cutting, gutting meaning) where the served Qwen3 trails Opus. That is a capability ceiling of the 32B, not a wording fix: prompting a 32B does not install Opus's comprehension. RAG is irrelevant (the task needs skill, not facts). The `evaluate` command exists precisely to *demonstrate* this against a base baseline, not assume it. |
| **3. Clean labelled data + held-out eval** | ✓ Primary data is **mined from existing Opus/Qwen edit bundles** (your own curated runs); Opus is the gold labeller; `distil/dataset.py` splits **by document** before emit; `eval/baseline.py` is the held-out test the tune must beat. |
| **4. Volume repays the effort** | ✓ The editor runs over whole manuscripts repeatedly; a standing per-paragraph quality lift on the cheap served model amortises a one-off LoRA. |

**Rungs deliberately rejected below fine-tune:**
- *Bigger served tier* (Qwen3-235B / route to Opus at volume): rejected on cost + the single-GPU serving constraint ([gcloud-model-serving.md](../../00_policies/gcloud-model-serving.md)); the point is to lift the *cheap* served model.
- *Prompt-only*: kept as the mandatory baseline the tune must beat (`evaluate`). If it doesn't beat the prompt on held-out data, we stay on the prompt.

**Method (policy §3.3–§3.6):** QLoRA (4-bit frozen base), never full fine-tune; trained on the *exact* served chat template; SFT first, DPO only if SFT is well-formed-but-suboptimal on the eval; adapters merged for vLLM serving; training stays self-hosted; corpus, checkpoints, and adapters are gitignored.

**Honest ceiling:** this distils Opus's *decisions on academic prose* into the 32B: better restraint and concision, closer to Opus's choices on this distribution. It does **not** give the 32B Opus-level comprehension of a novel hard argument; the genuinely subtle documents remain a route-to-Opus case.
