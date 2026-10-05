from kopi.quote_guard import word_count


def run(state: dict) -> dict:
    count = word_count(state["text"], state["qmap"])
    state["counts"]["step1"] = count
    state["log"].append({
        "step": "Step 1: Count",
        "detail": f"{count} words (target: {state['target']})",
        "para": None,
    })
    return state
