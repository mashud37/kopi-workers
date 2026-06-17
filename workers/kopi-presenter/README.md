# kopi-presenter — automated slide decks (PPTX + PDF)

Turn a manuscript or outline into a finished, presentation-ready **PowerPoint
deck** (`.pptx`) and a **PDF**, in one command:

```bash
python run.py input/manuscript.docx
```

An LLM distils your text into a structured slide plan; deterministic Python then
builds a styled `.pptx` (editable in PowerPoint) and exports a PDF.

## How it works

```
parse (.docx/.txt)  →  LLM slide JSON  →  lint  →  house rules  →  build .pptx  →  export PDF
```

- **LLM** (`slides/llm.py`) returns a strict JSON plan (sections, slides, layouts, evidence).
- **House rules** (`slides/rules.py`) enforce integrity deterministically: quotes only
  on Findings slides, every content slide has bullets, a single merged Conclusions slide.
- **Builder** (`slides/emitter_pptx.py`) renders the deck with `python-pptx`:
  breadcrumb nav, claim titles + accent rule, bold/colour key terms, stat callouts,
  quote/note boxes, two-column cards, matrix, stepflow, circle motif, emoji/icon row.
- **Renderer** (`slides/renderer_pptx.py`) exports PDF via PowerPoint (best fidelity),
  falling back to LibreOffice.

## Repo layout

```
run.py              pipeline entry point
config.yaml         config template (no secrets)
config.local.yaml   your local config + API key (gitignored)
requirements.txt
slides/
  parser.py         .docx/.txt -> text
  llm.py            text -> slide JSON (Claude)
  linter.py         validate + auto-repair the JSON
  rules.py          deterministic house rules
  emitter_pptx.py   slide JSON -> .pptx (python-pptx)
  renderer_pptx.py  .pptx -> .pdf (PowerPoint / LibreOffice)
  icons.py          Segoe Fluent Icons + emoji mapping
input/              drop manuscripts (.docx) / outlines (.txt) here
output/             generated .json / .pptx / .pdf land here
```

## Setup

```bash
pip install -r requirements.txt          # anthropic, python-pptx, python-docx, pyyaml

cp config.yaml config.local.yaml         # then set api.anthropic_key, or:
#   set ANTHROPIC_API_KEY=sk-ant-...      (env var overrides the file)
```

PDF export needs **PowerPoint** (Windows, used by default) or **LibreOffice**
(auto-detected fallback). The `.pptx` itself needs neither.

## Usage

```bash
python run.py input/manuscript.docx --venue "ICA 2026, Cape Town, South Africa"
python run.py input/outline.txt
python run.py input/paper.docx --review          # review the plan, give plain-language feedback, LLM revises
python run.py input/paper.docx --emoji           # colour emoji instead of Fluent icons
python run.py input/paper.docx --dry-run         # print the JSON plan only
python run.py input/paper.docx --plan output/paper.json   # rebuild from JSON (no LLM)
python run.py input/paper.docx --no-pdf          # .pptx only
python run.py input/paper.docx --condense        # trim long paragraphs (cheaper, less rich)
```

Outputs land in `output/` (override with `-o DIR`):

| File | Description |
|------|-------------|
| `stem.json` | Slide plan — reuse with `--plan` to skip the LLM |
| `stem.pptx` | **Editable PowerPoint deck** |
| `stem.pdf`  | **Primary handout/print output** |

## Configuration (`config.local.yaml`)

```yaml
llm:
  model: "claude-sonnet-4-6"   # or claude-haiku-4-5-20251001 / claude-opus-4-7
  max_tokens: 8192
defaults:
  author: "Your Name"
  affiliation: "Your Institution"
  email: "you@example.com"
render:
  icons: "fluent"              # "fluent" (default) or "emoji"
linter:
  auto_repair: true
```

By default the **full manuscript** is sent to the LLM for the richest result
(use `--condense` to trim long paragraphs and save tokens).

## Design system

- **Layouts:** `bullets`, `split` (bullets + side evidence), `cards`, `matrix`,
  `stepflow`, `iconrow`, `boxes`, `circle` (centre word + orbiting keywords).
- **Evidence (side content):** `stats` (2–3 big numbers), `stat`, `quote-dark`
  (verbatim, Findings only), `note` (synthesised, no quote marks), `figure`.
- **Icons:** Segoe Fluent Icons (vector, recoloured to the palette) by name; colour
  emoji via `--emoji`. Body text auto-sizes to fit; bullets are top-aligned.
- **Palette:** Office-style — consistent blue chrome (nav, title rule, key terms)
  plus a categorical set (blue/orange/green/gold/purple/red) for stats, cards,
  matrix cells and columns.

## Models & cost (full 10k-word manuscript ≈ 13k input tokens)

| Model | ~Cost/deck | Notes |
|-------|-----------|-------|
| Haiku 4.5 | ~$0.03 | cheapest; good for outlines / clear papers |
| Sonnet 4.6 | ~$0.10 | balanced; strong argument selection (default) |
| Opus 4.7 | ~$0.30–0.50 | richest distillation of dense papers |

## Notes

- Segoe Fluent Icon glyphs render via **PowerPoint** (the default PDF path). The
  **LibreOffice** fallback may show blanks for them — install/keep PowerPoint for
  icon fidelity, or use `--emoji`.
- `config.local.yaml` holds your API key and is gitignored — never commit it.
