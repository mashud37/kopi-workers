"""Post an edit request to the served Qwen `/tighten` endpoint using only
stdlib HTTP, so this module runs unchanged on the laptop and inside the
featherweight CPU eval job container.
"""
import json
import urllib.error
import urllib.request

TIMEOUT = 300


def post_edit(req: dict, base_url: str, token: str, model: str | None) -> str:
    """One edit from the served model via the production prompt.

    Args:
        req: A record carrying the prebuilt `messages` plus `original`/`instructions`
            (the latter feed the service's token guard).
        base_url: The served vLLM service URL.
        token: The service JOB_TOKEN.
        model: None for the prompt-only base; a module name (e.g. 'kopi') selects the
            baked LoRA tune.

    Returns:
        The edited paragraph text.
    """
    url = f"{base_url.rstrip('/')}/tighten?token={token}"
    # Greedy + fixed seed: the eval must be reproducible so a re-run (or a base-vs-tune
    # delta) reflects the adapter, not sampling noise: production keeps its own 0.1 default.
    payload = {
        "messages": req["messages"],
        "paragraph": req["original"],
        "instructions": req.get("instructions"),
        "temperature": 0,
        "seed": 0,
    }
    if model:
        payload["model"] = model
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())["edited"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()
        if e.code == 400 and model and "unknown model" in detail:
            raise SystemExit(
                f"the served editor has no '{model}' module - it was deployed base-only. "
                f"Redeploy kopi-editor with the adapter staged (deploy_vllm.ps1, which bakes "
                f"data/adapters/sft as '{model}') before evaluating.") from None
        raise SystemExit(f"/tighten returned HTTP {e.code}: {detail}") from None
