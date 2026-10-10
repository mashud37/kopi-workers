"""Call any server that accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, Ollama or vLLM, through OpenAI's own library."""
import shutil
import subprocess
from urllib.parse import urlparse

TEMPERATURE = 0.2
TIMEOUT_SECONDS = 600
RETRIES = 4
NO_KEY = "no-key"
CLOUD_RUN_HOST = ".run.app"


def cloud_run_headers(base_url):
    """Google's sign-in for a model on Cloud Run, which admits only your own account; nothing for any other server."""
    host = urlparse(base_url).hostname or ""
    if not host.endswith(CLOUD_RUN_HOST):
        return {}
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise ValueError("A model on Cloud Run needs the gcloud command, signed in with: gcloud auth login")
    made = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True)
    if made.returncode != 0:
        raise ValueError(f"gcloud could not sign in to Cloud Run: {made.stderr.strip()}")
    return {"X-Serverless-Authorization": f"Bearer {made.stdout.strip()}"}


def drop_thinking(text):
    """Remove the reasoning some open models write between think tags before their answer."""
    answer = text.strip()
    if answer.startswith("<think>") and "</think>" in answer:
        answer = answer.split("</think>", 1)[1]
    return answer.strip()


def complete(config: dict, system: str | None, user_message: str, max_tokens: int) -> dict:
    """Send one system and user message pair to the configured server and return the answer.

    Returns:
        dict with "text", the answer, and "truncated", True when it stopped at max_tokens.

    Raises:
        ValueError: the server address or model is missing, or the server failed or refused the request.
    """
    import openai

    llm = config.get("llm", {})
    base_url = llm.get("base_url", "")
    model = llm.get("server_model", "")
    if not base_url or not model:
        raise ValueError("The openai-compatible backend needs llm.base_url and llm.server_model in config.local.yaml, "
                         "or the KOPI_PRESENTER_LLM_BASE_URL and KOPI_PRESENTER_LLM_MODEL variables.")
    client = openai.OpenAI(
        base_url=base_url,
        api_key=config.get("api", {}).get("llm_key") or NO_KEY,
        timeout=TIMEOUT_SECONDS,
        max_retries=RETRIES,
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})
    try:
        reply = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            extra_headers=cloud_run_headers(base_url),
            temperature=TEMPERATURE,
        )
    except openai.APIError as error:
        raise ValueError(f"The model call failed at {base_url}: {error}") from None
    if reply.usage:
        print(f"       Tokens: input: {reply.usage.prompt_tokens:,}  output: {reply.usage.completion_tokens:,}  (billed by {base_url})")
    choice = reply.choices[0]
    return {
        "text": drop_thinking(choice.message.content or ""),
        "truncated": choice.finish_reason == "length",
    }
