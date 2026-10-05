"""Send one prompt to the configured Claude model and return its JSON answer, printing tokens and list-price cost.
Planning, revising and repairing a deck all call complete_json()."""

import json
import re

from slides.config import KEY_PLACEHOLDER, MODEL_PRICES

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 16000
OPENING_FENCE = re.compile(r"^```(?:json)?\s*\n?", flags=re.MULTILINE)
CLOSING_FENCE = re.compile(r"\n?```\s*$", flags=re.MULTILINE)


def complete_json(config: dict, system: str | None, user_message: str) -> dict:
    """One Messages API call whose answer is a JSON object.

    Args:
        config: the loaded configuration, for the key, model and output cap.
        system: the system prompt, or None for none.
        user_message: the request.

    Raises:
        ValueError: no key is set, the call failed, the answer was cut off at the output cap, or it is not valid JSON.
    """
    import anthropic

    api_key = config.get("api", {}).get("anthropic_key", "")
    if not api_key or api_key == KEY_PLACEHOLDER:
        raise ValueError("Anthropic API key not set. Add it to config.local.yaml (api.anthropic_key) or set the ANTHROPIC_API_KEY environment variable.")
    model = config.get("llm", {}).get("model", DEFAULT_MODEL)
    max_tokens = config.get("llm", {}).get("max_tokens", DEFAULT_MAX_TOKENS)

    request = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_message}],
    }
    if system:
        request["system"] = system
    try:
        response = anthropic.Anthropic(api_key=api_key).messages.create(**request)
    except anthropic.APIError as error:
        raise ValueError(f"The model call failed: {error}") from None
    print(f"       {cost_line(model, response.usage)}")

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"The model hit the {max_tokens:,}-token output limit and the slide JSON was truncated. "
            "Raise llm.max_tokens in config.local.yaml or ask for fewer slides, then re-run."
        )
    parts = [block.text for block in response.content if block.type == "text"]
    raw = "".join(parts).strip()
    raw = OPENING_FENCE.sub("", raw)
    raw = CLOSING_FENCE.sub("", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"Model did not return valid JSON ({error}). Last 200 chars received:\n...{raw[-200:]}") from error


def cost_line(model: str, usage) -> str:
    """The call's token counts and its cost at list price, or a note when the model has no price here."""
    counts = f"Tokens: input: {usage.input_tokens:,}  output: {usage.output_tokens:,}"
    rates = MODEL_PRICES.get(model)
    if rates is None:
        return f"{counts}  (cost n/a: no price for {model})"
    dollars = (usage.input_tokens * rates[0] + usage.output_tokens * rates[1]) / 1_000_000
    return f"{counts}  (est. cost: ${dollars:.4f})"
