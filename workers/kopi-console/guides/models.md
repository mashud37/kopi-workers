# Models

kopi-editor's **edit** command and kopi-presenter's **slides** command call a language model.
Everything else runs on your computer without one.

## Who edits

kopi-editor's Settings card offers four choices:

| Choice | What it means | Needs |
|---|---|---|
| Claude, through the Anthropic API | Anthropic's models edit each paragraph | An Anthropic key on **Keys**, and a **Claude model** |
| Your Qwen server on Google Cloud | A Qwen model on a GPU server of your own, which scales to zero when idle | A Google Cloud project and `kopi-editor deploy` |
| Ollama on this computer | A model served by Ollama on the same machine | Ollama running, with a model pulled |
| No model: rules only | **edit** applies the same fixes as **proof** | nothing |

Only the paragraphs sent for editing leave the computer, and with your own server or Ollama they
go nowhere you do not control.

## Claude models

The **Claude model** setting offers Claude Haiku 4.5, Sonnet 5.5 and Opus 5.5, cheapest to
strongest, each with its price per million tokens. Every run prints what it cost, at list price.

## Your own server

`kopi-editor deploy` builds a Qwen server on Google Cloud Run with a GPU, in your own project, and
`kopi-editor deploy-status --wait` finishes it. It needs the `gcloud` command signed in to that
project. The server costs nothing while idle and bills by the second while it edits.
