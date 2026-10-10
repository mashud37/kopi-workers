"""Send one prompt to the configured Claude model and return its answer, printing tokens and list-price cost."""

from slides.config import KEY_PLACEHOLDER, MODEL_PRICES

DEFAULT_MODEL = "claude-haiku-4-5"


def complete(config: dict, system: str | None, user_message: str, max_tokens: int) -> dict:
    """One Messages API call.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at max_tokens.

    Raises:
        ValueError: no key is set, or the call failed.
    """
    import anthropic

    api_key = config.get("api", {}).get("anthropic_key", "")
    if not api_key or api_key == KEY_PLACEHOLDER:
        raise ValueError("Anthropic API key not set. Add it to config.local.yaml (api.anthropic_key) or set the ANTHROPIC_API_KEY environment variable.")
    model = config.get("llm", {}).get("model", DEFAULT_MODEL)

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
    parts = [block.text for block in response.content if block.type == "text"]
    return {
        "text": "".join(parts).strip(),
        "truncated": response.stop_reason == "max_tokens",
    }


def cost_line(model: str, usage) -> str:
    """The call's token counts and its cost at list price, or a note when the model has no price here."""
    counts = f"Tokens: input: {usage.input_tokens:,}  output: {usage.output_tokens:,}"
    rates = MODEL_PRICES.get(model)
    if rates is None:
        return f"{counts}  (cost n/a: no price for {model})"
    dollars = (usage.input_tokens * rates[0] + usage.output_tokens * rates[1]) / 1_000_000
    return f"{counts}  (est. cost: ${dollars:.4f})"
