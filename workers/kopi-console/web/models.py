"""Keep which model and server each app uses, and hand the choices to its jobs as environment variables.
Apps left on their own settings keep reading their own file.
"""
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

import yaml

from registry import data_folder, get_app
from settings import SETTINGS
from web import keys

MODELS_FILE_NAME = "models.json"
EDITOR_SETTINGS_FILE = "env.yaml"
LIST_TIMEOUT_SECONDS = 8
CLOUD_RUN_HOST = ".run.app"
BLANK_GENERATION = {
    "route": "",
    "base_url": "",
    "model": "",
}

# Where a model runs, as the page offers it; every route but Claude is an OpenAI-compatible server.
ROUTES = {
    "claude": {"label": "Claude", "backend": "anthropic", "detail": "Anthropic's models, with a key"},
    "service": {"label": "Another service", "backend": "openai-compatible", "detail": "DeepSeek, Kimi, Qwen and others, with a key"},
    "computer": {"label": "This computer", "backend": "openai-compatible", "detail": "Ollama, LM Studio, vLLM or llama.cpp"},
    "cloud": {"label": "Your own cloud", "backend": "openai-compatible", "detail": "The server kopi-editor's deploy put on Cloud Run"},
}

# Prices are list prices in US dollars per million tokens, input then output.
CLAUDE_MODELS = [
    {"value": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "detail": "Fastest and cheapest · $1 in, $5 out"},
    {"value": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "detail": "Better writing · $2 in, $10 out"},
    {"value": "claude-opus-5-5", "label": "Claude Opus 5.5", "detail": "Strongest · $4 in, $20 out"},
]

# Each app's model slot: what it does, the app's own Claude default (none for the editor, so
# every edit's cost is chosen on purpose), and the variable the choice arrives in for Claude
# and for an OpenAI-compatible server.
GENERATION = {
    "kopi-editor": {
        "backend": "KOPI_BACKEND",
        "base_url": "KOPI_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model", "help": "Edits every paragraph.", "default": "", "anthropic": "KOPI_ANTHROPIC_MODEL", "openai-compatible": "KOPI_LLM_MODEL"},
        ],
    },
    "kopi-presenter": {
        "backend": "KOPI_PRESENTER_BACKEND",
        "base_url": "KOPI_PRESENTER_LLM_BASE_URL",
        "slots": [
            {"setting": "model", "label": "Model", "help": "Plans the slides and repairs the plan.", "default": "claude-haiku-4-5-20251001", "anthropic": "KOPI_PRESENTER_MODEL", "openai-compatible": "KOPI_PRESENTER_LLM_MODEL"},
        ],
    },
}

# Addresses offered for each route; any other address works the same way.
ADDRESSES = {
    "service": [
        {"value": "https://api.deepseek.com/v1", "label": "DeepSeek"},
        {"value": "https://api.moonshot.ai/v1", "label": "Kimi (Moonshot)"},
        {"value": "https://api.moonshot.cn/v1", "label": "Kimi (Moonshot, mainland China)"},
        {"value": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "label": "Qwen (Alibaba Model Studio)"},
        {"value": "https://dashscope.aliyuncs.com/compatible-mode/v1", "label": "Qwen (Alibaba Model Studio, mainland China)"},
        {"value": "https://open.bigmodel.cn/api/paas/v4", "label": "GLM (Zhipu)"},
        {"value": "https://api.mistral.ai/v1", "label": "Mistral"},
        {"value": "https://router.huggingface.co/v1", "label": "Hugging Face Inference Providers"},
        {"value": "https://openrouter.ai/api/v1", "label": "OpenRouter"},
        {"value": "https://api.openai.com/v1", "label": "OpenAI"},
        {"value": "https://generativelanguage.googleapis.com/v1beta/openai", "label": "Gemini"},
    ],
    "computer": [
        {"value": "http://localhost:11434/v1", "label": "Ollama"},
        {"value": "http://localhost:1234/v1", "label": "LM Studio"},
        {"value": "http://localhost:8000/v1", "label": "vLLM"},
        {"value": "http://localhost:8080/v1", "label": "llama.cpp server"},
    ],
}

SERVER_KEY_VARIABLE = "KOPI_LLM_API_KEY"


# ---- The store ----

def store_file():
    """Where the model choices are kept: beside the key store, outside the workspace."""
    return SETTINGS["store_folder"] / MODELS_FILE_NAME


def load_store():
    """Every choice made on the Models page, with a blank entry for anything not chosen yet."""
    data = {"generation": {}}
    if store_file().exists():
        data = json.loads(store_file().read_text(encoding="utf-8"))
    generation = {}
    for app_name in GENERATION:
        saved = data.get("generation", {}).get(app_name, {})
        generation[app_name] = dict(BLANK_GENERATION)
        for setting in BLANK_GENERATION:
            generation[app_name][setting] = saved.get(setting, "")
    return {"generation": generation}


def save_store(store):
    """Write the store through a temporary file, so a crash never leaves half a file behind."""
    path = store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ---- The server kopi-editor deployed ----

def deployed_servers():
    """The Cloud Run server kopi-editor's deploy recorded in its settings file, with its address, model and key."""
    settings_file = data_folder(get_app("kopi-editor")) / EDITOR_SETTINGS_FILE
    if not settings_file.exists():
        return []
    recorded = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
    if not recorded.get("BASE_URL") or not recorded.get("JOB_TOKEN"):
        return []
    return [{
        "name": recorded.get("SERVICE") or "kopi-editor",
        "address": recorded["BASE_URL"].rstrip("/") + "/v1",
        "model": recorded.get("MODEL") or "",
        "key": recorded["JOB_TOKEN"],
    }]


def server_at(base_url):
    """The deployed server at this address, or None for any other server."""
    for server in deployed_servers():
        if server["address"].rstrip("/") == base_url.rstrip("/"):
            return server
    return None


# ---- Saving the page ----

def check_server(base_url, model, what):
    """Refuse an OpenAI-compatible choice without a web address and a model name.

    Raises:
        ValueError: the address is missing or not a web address, or the model is missing.
    """
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"{what}: the server address must start with http:// or https://.")
    if not model:
        raise ValueError(f"{what}: name the model the server should use.")


def save_choices(form):
    """Check and store the Models page form, whose fields are named `app|setting`.

    Raises:
        ValueError: an unknown route, or a server choice without address or model.
    """
    store = {"generation": {}}
    for app_name, app in GENERATION.items():
        route = form.get(f"{app_name}|route", "").strip()
        if route and route not in ROUTES:
            raise ValueError(f"{app_name} has no route called {route}.")
        field_kind = "claude" if route == "claude" else "server"
        chosen = dict(BLANK_GENERATION)
        chosen["route"] = route
        if route and route != "claude":
            chosen["base_url"] = form.get(f"{app_name}|base_url", "").strip()
        for slot in app["slots"]:
            chosen[slot["setting"]] = form.get(f"{app_name}|{slot['setting']}|{field_kind}", "").strip()
        server = server_at(chosen["base_url"]) if route == "cloud" else None
        if server and not chosen["model"]:
            chosen["model"] = server["model"]
        if route and route != "claude":
            check_server(chosen["base_url"], chosen["model"], app_name)
        if server:
            keys.use_server_key(app_name, f"kopi-cloud-{server['name']}", server["key"])
        store["generation"][app_name] = chosen
    save_store(store)


# ---- Listing a server's models ----

def server_key(app_name):
    """The key a server lookup sends for this app: the console's environment first, then the key store."""
    if os.environ.get(SERVER_KEY_VARIABLE):
        return os.environ[SERVER_KEY_VARIABLE]
    return keys.environment_for(app_name).get(SERVER_KEY_VARIABLE, "")


def cloud_run_token():
    """Your Google sign-in from gcloud, which a model on Cloud Run asks for before anything else.

    Raises:
        ValueError: gcloud is missing or not signed in.
    """
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise ValueError("A model on Cloud Run needs the gcloud command, signed in with: gcloud auth login")
    made = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True)
    if made.returncode != 0:
        raise ValueError("gcloud is not signed in. Run: gcloud auth login")
    return made.stdout.strip()


def list_models(app_name, base_url):
    """The model names an OpenAI-compatible server offers, asked from its /models address.

    Raises:
        ValueError: the address is not a web address, or the server refused or did not answer.
    """
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Enter the server address first; it starts with http:// or https://.")
    headers = {}
    key = server_key(app_name)
    server = server_at(base_url)
    if server:
        key = server["key"]
    if key:
        headers["Authorization"] = f"Bearer {key}"
    host = urllib.parse.urlparse(base_url).hostname or ""
    if host.endswith(CLOUD_RUN_HOST):
        headers["X-Serverless-Authorization"] = f"Bearer {cloud_run_token()}"
    request = urllib.request.Request(base_url.rstrip("/") + "/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=LIST_TIMEOUT_SECONDS) as reply:
            data = json.loads(reply.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError(f"The server refused the key. Add it on the Keys page as {SERVER_KEY_VARIABLE}.")
        raise ValueError(f"The server answered with error {error.code}.")
    except (urllib.error.URLError, OSError, ValueError):
        raise ValueError("No answer from that address. Is the server running?")
    names = [entry.get("id", "") for entry in data.get("data", [])]
    return sorted(name for name in names if name)


# ---- What a job receives ----

def generation_variables(app_name, chosen):
    """The variables one app's generation choice sets: its backend, its address, and a model per slot."""
    app = GENERATION[app_name]
    backend = ROUTES[chosen["route"]]["backend"]
    wanted = {app["backend"]: backend}
    if backend == "openai-compatible":
        wanted[app["base_url"]] = chosen["base_url"]
    for slot in app["slots"]:
        if chosen[slot["setting"]]:
            wanted[slot[backend]] = chosen[slot["setting"]]
    return wanted


def environment_for(app_name):
    """The model variables a job of this app receives. A variable already set in the console's
    own environment wins, and an app left on its own settings receives nothing."""
    store = load_store()
    wanted = {}
    if app_name in GENERATION and store["generation"][app_name]["route"]:
        wanted.update(generation_variables(app_name, store["generation"][app_name]))

    environment = {}
    for variable, value in wanted.items():
        if value and not os.environ.get(variable):
            environment[variable] = value
    return environment


def page_view():
    """Everything the Models page shows."""
    store = load_store()
    apps = []
    for app_name, app in GENERATION.items():
        apps.append({
            "name": app_name,
            "chosen": store["generation"][app_name],
            "slots": app["slots"],
        })
    addresses = dict(ADDRESSES)
    addresses["cloud"] = []
    for server in deployed_servers():
        addresses["cloud"].append({"value": server["address"], "label": f"{server['name']} · {server['model']}"})
    return {
        "apps": apps,
        "routes": ROUTES,
        "claude_models": CLAUDE_MODELS,
        "addresses": addresses,
        "file": str(store_file()),
    }
