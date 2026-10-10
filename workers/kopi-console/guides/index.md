# Getting started

kopi is a set of tools for academic prose. kopi-editor copy-edits a Word manuscript into plainer
prose without touching its argument, citations or quotations, and kopi-presenter turns a paper into
a slide deck and a PDF. kopi-console is one local web page over both.

## Install

With Python 3.10 or newer installed, open PowerShell (a terminal on macOS or Linux) and run:

```
pip install kopi-workers
kopi-console
```

The console opens in your browser at `http://127.0.0.1:5191`. Closing the PowerShell window stops
it, and `kopi-console` starts it again. `pip install --upgrade kopi-workers` updates every tool.

## Where your files live

Every tool keeps its files in one project folder, `kopi-workers` in your home folder. Each tool has its own folder inside it, with an `input` folder for
the documents it works on and an `output` folder for what it writes.

## Keys

Editing with Claude and building slides call a language model and need an Anthropic API key;
diagnosing and proofreading do not. Add a key once on the **Keys** page and every tool that needs
it gets it. Commands that call a paid model ask before they run.

## A first run

1. Open **kopi-editor** and drop a `.docx` on the page.
2. Run **analyze**: it reports how readable the document is and how many words could go, without
   changing anything.
3. Run **proof**: it applies the safe fixes that need no model and writes the edited text.
4. Open the newest folder under **Output**. The side-by-side file shows each paragraph before and
   after.

## The tools

| Tool | What it does |
|---|---|
| [kopi-editor](kopi-editor.md) | Diagnoses, proofreads and edits a Word manuscript |
| [kopi-presenter](kopi-presenter.md) | Turns a manuscript or outline into a slide deck and a PDF |

Each tool also runs on its own as a command of the same name, `kopi-editor` for example, which
opens its menu.
