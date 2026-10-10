"""Route one prompt to Claude or to any server that accepts OpenAI's chat format, and return its JSON answer.
Planning, revising and repairing a deck all call complete_json()."""

import json
import re

DEFAULT_MAX_TOKENS = 16000
OPENING_FENCE = re.compile(r"^```(?:json)?\s*\n?", flags=re.MULTILINE)
CLOSING_FENCE = re.compile(r"\n?```\s*$", flags=re.MULTILINE)


def complete_json(config: dict, system: str | None, user_message: str) -> dict:
    """One model call whose answer is a JSON object.

    Args:
        config: the loaded configuration, for the backend, key, model and output cap.
        system: the system prompt, or None for none.
        user_message: the request.

    Raises:
        ValueError: the call failed, the answer was cut off at the output cap, or it is not valid JSON.
    """
    max_tokens = config.get("llm", {}).get("max_tokens", DEFAULT_MAX_TOKENS)
    if config.get("llm", {}).get("backend") == "openai-compatible":
        from backends import openai_client
        reply = openai_client.complete(config, system, user_message, max_tokens)
    else:
        from backends import anthropic_client
        reply = anthropic_client.complete(config, system, user_message, max_tokens)

    if reply["truncated"]:
        raise ValueError(
            f"The model hit the {max_tokens:,}-token output limit and the slide JSON was truncated. "
            "Raise llm.max_tokens in config.local.yaml or ask for fewer slides, then re-run."
        )
    raw = OPENING_FENCE.sub("", reply["text"])
    raw = CLOSING_FENCE.sub("", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"Model did not return valid JSON ({error}). Last 200 chars received:\n...{raw[-200:]}") from error
