"""Conservative deterministic proofing — the LLM-free editing route.

Applies only the safe, mechanical transforms and nothing that needs a model's
judgement:

* filler-phrase replacement and padding-tail removal (`step_fillers` + `step_reduce`),
* cliché and long→short word substitutions (`step_plain`),
* LanguageTool grammar/spelling corrections (`step_proofing`).

Sentence removal and syntax restructuring are deliberately excluded (they risk
meaning loss without a model). Quotations are protected by `quote_guard`.

Implementation note: `step_reduce` is target-gated (it stops once the word target
is reached). Proofing has no word target, so we run it with ``target = 0`` to make
it apply *every* filler and padding tail, then restore the real target for the
final check.
"""
from kopi.quote_guard import word_count
from kopi import step_fillers, step_reduce, step_plain, step_proofing


def proof(state: dict) -> dict:
    real_target = state.get("target", 0)
    state["target"] = 0  # force step_reduce to apply all fillers + tails

    step_fillers.run(state)     # detect filler phrases -> state["fillers"]
    step_reduce.run(state)      # apply all fillers + padding tails (no sentence removal)
    step_plain.run(state)       # clichés + long->short word substitutions
    step_proofing.run(state)    # grammar / spelling (skips quoted spans itself)

    state["target"] = real_target
    state["counts"]["final"] = word_count(state["text"], state["qmap"])
    return state
