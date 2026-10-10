"""Call any server that accepts OpenAI's chat format, such as DeepSeek, Kimi, Qwen, Ollama or vLLM, through OpenAI's own library."""
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

import openai

from cli import config

TEMPERATURE = 0.1
TIMEOUT_SECONDS = 600
RETRIES = 4
NO_KEY = "no-key"
CLOUD_RUN_HOST = ".run.app"
SIGN_IN_SECONDS = 1800

_lock = threading.Lock()
_clients = {}
_sign_in = {"token": "", "fetched": 0.0}


def make_client(connection):
    """One client per server and key, shared by every thread so they share its connections."""
    key = connection["api_key"] or NO_KEY
    with _lock:
        if (connection["base_url"], key) not in _clients:
            _clients[(connection["base_url"], key)] = openai.OpenAI(
                base_url=connection["base_url"],
                api_key=key,
                timeout=TIMEOUT_SECONDS,
                max_retries=RETRIES,
            )
        return _clients[(connection["base_url"], key)]


def cloud_run_headers(base_url):
    """Google's sign-in for a model on Cloud Run, which admits only your own account; nothing for any other server.
    The token comes from gcloud and is reused for half an hour, half its lifetime, since fetching one takes seconds."""
    host = urlparse(base_url).hostname or ""
    if not host.endswith(CLOUD_RUN_HOST):
        return {}
    with _lock:
        expired = time.monotonic() - _sign_in["fetched"] > SIGN_IN_SECONDS
        if not _sign_in["token"] or expired:
            gcloud = shutil.which("gcloud")
            if gcloud is None:
                raise SystemExit("A model on Cloud Run needs the gcloud command, signed in with: gcloud auth login")
            made = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True)
            if made.returncode != 0:
                raise SystemExit(f"gcloud could not sign in to Cloud Run: {made.stderr.strip()}")
            _sign_in["token"] = made.stdout.strip()
            _sign_in["fetched"] = time.monotonic()
        return {"X-Serverless-Authorization": f"Bearer {_sign_in['token']}"}


def drop_thinking(text):
    """Remove the reasoning some open models write between think tags before their answer."""
    answer = text.strip()
    if answer.startswith("<think>") and "</think>" in answer:
        answer = answer.split("</think>", 1)[1]
    return answer.strip()


def complete(system, prompt, max_tokens):
    """Send one system and user message pair and return the answer.

    Raises:
        RuntimeError: the server stayed busy or unreachable; the paragraph keeps its original wording.
        SystemExit: the server refused the request, for example a wrong key or model name.
    """
    connection = config.llm_connection()
    client = make_client(connection)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    try:
        reply = client.chat.completions.create(
            model=connection["model"],
            messages=messages,
            max_tokens=max_tokens,
            extra_headers=cloud_run_headers(connection["base_url"]),
            temperature=TEMPERATURE,
        )
    except (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError) as error:
        raise RuntimeError(f"LLM server unavailable at {connection['base_url']}: {error}")
    except openai.APIStatusError as error:
        raise SystemExit(f"LLM server error {error.status_code}: {error}")
    return drop_thinking(reply.choices[0].message.content or "")
