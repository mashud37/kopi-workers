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

Every tool keeps its files in one project folder, `kopi-workers` in your home folder. A document
dropped on any tool's page lands in its `documents` folder, which every tool reads, so a chapter
added for the editor is ready for the presenter too. Each tool writes its results into its own
folder, one dated folder per run. **Copy to documents**, on a result's page, hands that result to
the other tools.

## Keys

Editing and building slides call a language model, chosen on the **Models** page; diagnosing and
proofreading do not. Claude and other hosted services need a key: add it once on the **Keys** page
and every tool that needs it gets it. Commands that call a paid model ask before they run.

## A first run

1. Open **kopi-editor** and drop a `.docx` on the page.
2. Run **analyze**: it reports how readable the document is and how many words could go, without
   changing anything.
3. Run **proof**: it applies the safe fixes that need no model and writes the edited text.
4. Open the newest folder under **Results**. The side-by-side file shows each paragraph before and
   after.

## The tools

| Tool | What it does |
|---|---|
| [kopi-editor](kopi-editor.md) | Diagnoses, proofreads and edits a Word manuscript |
| [kopi-presenter](kopi-presenter.md) | Turns a manuscript or outline into a slide deck and a PDF |

Each tool also runs on its own as a command of the same name, `kopi-editor` for example, which
opens its menu.
