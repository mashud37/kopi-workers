# Models

kopi-editor's **edit** command and kopi-presenter's **slides** command call a language model.
Everything else runs on your computer without one.

## Where the model runs

The **Models** page has one card per tool, each with the same choices:

| Choice | What it means | Needs |
|---|---|---|
| Claude | Anthropic's models | An Anthropic key on **Keys**, and a model |
| Another service | DeepSeek, Kimi, Qwen, Mistral, OpenRouter and other providers | The provider's address, a model name, and its key on **Keys** as `KOPI_LLM_API_KEY` |
| This computer | A model served by Ollama, LM Studio, vLLM or llama.cpp | The program running, with a model downloaded |
| Your own cloud | A Qwen server of your own on Google Cloud Run, which scales to zero when idle | `kopi-editor deploy`; its key is filled in by itself |
| Its own settings | Whatever the tool's settings file says | nothing |

**Choose** lists known addresses for each choice, and **Show models** asks the server which models
it offers. Only the text sent to the model leaves the computer, and with your own cloud or a model
on this computer it goes nowhere you do not control.

## Claude models

The Claude choice offers Claude Haiku 4.5, Sonnet 5.5 and Opus 5.5, cheapest to strongest, each
with its price per million tokens. kopi-editor has no default Claude model, so every paid edit is
a deliberate choice. Every run prints what it cost, at list price.

## Your own cloud

`kopi-editor deploy` builds a Qwen server on Google Cloud Run with a GPU, in your own project, and
`kopi-editor deploy-status --wait` finishes it. It needs the `gcloud` command signed in to that
project. The server costs nothing while idle and bills by the second while it works. Once it is
deployed, **Your own cloud** offers it under **Choose**.
