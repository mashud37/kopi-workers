"""The gold teacher: sends production's exact chat messages to Anthropic
Opus and returns its edit as `chosen`. The identical system prompt is
marked cacheable to cut cost across a run.
"""
import editor
from cli import config

_MAX_TOKENS = 4096

# USD per 1M tokens (input, output); cached 2026-10, mirrors kopi-editor/cli/api.py.
_PRICING = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def client():
    try:
        import anthropic
    except ImportError:
        raise SystemExit("anthropic SDK not installed, run: pip install -r requirements.txt")
    if not config.anthropic_api_key():
        raise SystemExit("no Anthropic API key, set it in secrets.yaml or $ANTHROPIC_API_KEY.")
    return anthropic.Anthropic(api_key=config.anthropic_api_key())


def edit(cl, unit: dict) -> dict:
    """Opus's edit of one unit, plus the call's token usage."""
    msgs = editor.build_messages(
        unit["text"], unit.get("instructions"), config.lang(), unit["mode"], unit.get("floor"))
    system, user = msgs[0]["content"], msgs[1]["content"]
    resp = cl.messages.create(
        model=config.opus_model(),
        max_tokens=_MAX_TOKENS,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    out = "".join(b.text for b in resp.content if b.type == "text").strip()
    u = resp.usage
    usage = {
        "input": getattr(u, "input_tokens", 0) or 0,
        "output": getattr(u, "output_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
    return {"text": out, "usage": usage}


def build_request(custom_id: str, unit: dict):
    """One Batch API request for a unit. Same prompt as the online path, with a
    cacheable system block so batch caching stacks on the 50% batch discount."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    msgs = editor.build_messages(
        unit["text"], unit.get("instructions"), config.lang(), unit["mode"], unit.get("floor"))
    system, user = msgs[0]["content"], msgs[1]["content"]
    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            model=config.opus_model(),
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        ),
    )


def submit_batch(cl, requests: list):
    return cl.messages.batches.create(requests=requests)


def batch_status(cl, batch_id: str):
    return cl.messages.batches.retrieve(batch_id)


def batch_results(cl, batch_id: str):
    return cl.messages.batches.results(batch_id)


def cost(totals: dict) -> float | None:
    rates = _PRICING.get(config.opus_model())
    if not rates:
        return None
    in_rate, out_rate = rates
    return (
        totals["input"] * in_rate
        + totals["cache_write"] * in_rate * 1.25
        + totals["cache_read"] * in_rate * 0.10
        + totals["output"] * out_rate
    ) / 1_000_000
