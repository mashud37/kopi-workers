"""Apply only safe mechanical fixes (filler/padding removal, cliche and
long-word substitution, LanguageTool grammar) with no LLM judgement. Sentence
removal and restructuring are excluded; quotations are protected by `quote_guard`.
"""
from kopi import step_fillers, step_plain, step_proofing, step_reduce
from kopi.quote_guard import word_count


def proof(state: dict) -> dict:
    real_target = state.get("target", 0)
    state = {**state, "target": 0}  # force step_reduce to apply all fillers + tails

    state = step_fillers.run(state)   # detect filler phrases -> state["fillers"]
    state = step_reduce.run(state)    # apply all fillers + padding tails (no sentence removal)
    state = step_plain.run(state)     # clichés + long->short word substitutions
    state = step_proofing.run(state)  # grammar / spelling (skips quoted spans itself)

    state = {**state, "target": real_target}
    state["counts"]["final"] = word_count(state["text"], state["qmap"])
    return state
