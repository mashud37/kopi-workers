# kopi-workers <img src="docs/logo.png" align="right" height="120" alt="" />

Copy-editing and presentation tools for academic prose. kopi-editor copy-edits a Word manuscript
into plainer prose without touching its argument, citations or quotations, and kopi-presenter turns
a paper into a slide deck and a PDF. kopi-console is one local web page over both: drop a file, run
a command, watch the log. Only the text sent to a model leaves the machine, and that can go to a
model on this computer or a private endpoint of your own.

## The tools

| Tool | What it does |
|---|---|
| kopi-editor | Diagnoses a `.docx`, applies safe local fixes, and edits with a model; a guard rejects any edit that changes the meaning, a citation or a number |
| kopi-presenter | Turns a manuscript or outline into a styled `.pptx` and a PDF |
| kopi-console | Runs both in the browser, with one documents folder they share and a page for choosing each tool's model |

## Getting started

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). On Windows,
   tick **Add python.exe to PATH** on the installer's first screen.
2. Open PowerShell (a terminal on macOS or Linux) and run:

```powershell
pip install kopi-workers
kopi-console
```

The console opens in the browser at `http://127.0.0.1:5191`. Its pages take the API key and the
documents each tool works on. Each tool also runs on its own as a command of the same name,
`kopi-editor` for example, which opens its menu. `pip install --upgrade kopi-workers` updates
every tool. The guide is at <https://mashud37.github.io/kopi-workers/>.
