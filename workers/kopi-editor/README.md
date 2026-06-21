# kopi-editor

Plain-language copy editor for academic prose in the humanities and social sciences. Following
plain-language editing principles — prefer short words to long, cut wordiness, replace clichés with
direct statement — it makes scholarly writing more accessible while preserving the author's argument,
voice, citations, and quotations. How hard it cuts scales with the reduction you ask for: ask for
nothing and it edits only for clarity; ask for a major cut and it concedes whole redundant sentences.

It takes a `.docx` and offers three routes:

- **analyze** — a diagnostic report: how many unnecessary words and redundant sentences could go, and
  what each paragraph needs. No edits, no files written.
- **proof** — conservative, deterministic editing with no LLM: removes fillers and padding, swaps
  long words for short, fixes grammar. Fully local and free.
- **edit** — a full plain-language edit via an LLM. The deterministic layer **diagnoses each
  paragraph and hands the model targeted instructions**, so a cheaper-than-Opus model edits well.

Single-user and local-first: diagnosis and proofing run entirely on your machine; the LLM `edit`
route runs on **your own** private Cloud Run GPU service, the Anthropic API, or a local Ollama.
Targets British English by default.

## LLM backends (for the `edit` route)

Diagnosis and proofing are always local; this choice only affects the `edit` route. There is **no
default model** — you choose one in `settings`, so the cost is always deliberate.

| Backend (`LLM`) | Where the model runs | Cost reported as |
|---|---|---|
| `cloud` | Your private Cloud Run **GPU service** (e.g. qwen2.5:7b on an L4) | estimated $ from L4 runtime |
| `api` | **Anthropic API** (Haiku / Sonnet / Opus) — no GPU, no cold start | $ from token usage |
| `local` | Ollama on your machine | — (self-hosted) |
| `skip` | — (no LLM edit) | — |

## Layout

```
manage.py             entrypoint — no args = menu; subcommands also available
env.yaml.example      config template; copy to env.yaml (gitignored)
deploy.ps1 / deploy.sh  build + deploy the GPU service (.ps1 is the Windows default)
requirements.txt
cli/                  command modules (analyze, proof, edit, cloud, api, deploy, settings, …)
kopi/                 diagnose (shared core), proof, llm, step_* helpers, signals, output
cloud/                serve.py — the GPU service
input/                source .docx files (gitignored, kept with .gitkeep)
output/               generated .md files (gitignored)
docs/  data/  tests/  reference docs, bundled datasets, pytest suite
```

## Setup

Requires Python 3.10+.

```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python manage.py install      # creates env.yaml, checks deps
python manage.py settings     # choose LLM backend + model (+ language)
python manage.py              # launch the interactive menu
```

`install` is idempotent. For the `cloud` backend, `python manage.py deploy` builds the model into a
container image, deploys a warm L4-GPU Cloud Run service, and writes `BASE_URL` + `JOB_TOKEN` into
`env.yaml`. For the `api` backend, paste your Anthropic key in `settings`.

First-run downloads: **sentence-transformers** (`all-MiniLM-L6-v2`, ~40 MB, for the meaning guard)
and, for `proof`, **LanguageTool** (~200 MB Java engine, then offline).

## Menu

```
1) Analyze     2) Proof          3) Full edit     4) Settings    5) Show config
6) Deploy      7) Cloud smoke    8) Update        9) Install
```

Each of Analyze / Proof / Full edit lists the `.docx` files in `input/` to pick from.

## Direct subcommands (scriptable)

```
python manage.py analyze <file.docx>
python manage.py proof   <file.docx> [--lang {british|american}]
python manage.py edit    <file.docx> [words_to_remove] [--llm {cloud|api|local|skip}] [--lang …]
python manage.py settings | config | deploy | install | update
python manage.py cloud-test [<n>] [--source <file>]   # dev smoke for the GPU service
```

`<file.docx>` — a bare name resolves against `input/`. For `edit`, `words_to_remove` **sets the
editing intensity**, not just a figure in the report. The ratio of words asked to document length
picks a band:

| `words_to_remove` | band | what the editor does | max cut / paragraph |
|---|---|---|---|
| omitted / `0` | **clarity** | plain words, active voice; keeps every sentence; length barely moves | ~6% |
| small (≲ 5% of the text) | **light** | cuts fillers, tightens wording; keeps every sentence | ~18% |
| moderate (≈ 5–12%) | **firm** | tightens wordy passages markedly (15–30%); may merge a weak follow-on | ~35% |
| large (≳ 12%) | **aggressive** | compresses hard and **may drop redundant or marginal sentences** | ~55% |

Because it is a ratio, the same number means more on a short paper than a long thesis. If one pass
falls short of the request, the wordiest remaining paragraphs are re-edited **once more** to approach
the target. The guard never lets a paragraph cut past its band's ceiling, so a clarity pass can't
quietly gut a manuscript, and claims, citations, and numbers are always preserved.

```
python manage.py analyze "chapter 1.docx"          # report only
python manage.py proof   "chapter 1.docx"          # deterministic edit, no LLM
python manage.py edit    "chapter 1.docx"          # full plain-language edit (backend from settings)
python manage.py edit    "chapter 1.docx" 1000     # ... aggressively, aiming to shed ~1000 words
```

## How it works

All three routes share one deterministic **diagnosis** ([kopi/diagnose.py](kopi/diagnose.py)): it
parses the document once and produces document-level estimates (unnecessary words, redundant
sentences, readability) plus, per paragraph, a small set of categorical editing instructions
(always *plain language*; plus *wordiness*, *redundancy*, *passive voice*, or *long sentences* when
detected).

- **analyze** writes `output/<name>_analysis.md`: readability gauges, the editable levers, key
  terms (TF-IDF), and a **paragraph-by-paragraph worksheet** — every paragraph with its scores and
  the exact edit guidance, for editing by hand.
- **proof** applies only the safe, mechanical fixes — filler/padding removal, cliché and long→short
  word substitution, and LanguageTool grammar — and writes the edited text. It never removes
  sentences or restructures syntax.
- **edit** sends every eligible paragraph to the LLM backend with its instructions as *editor's
  notes*, at the **intensity set by the reduction request** ([kopi/intensity.py](kopi/intensity.py)):
  the requested band picks the prompt stance (how hard to cut, whether sentences may go) and a
  per-paragraph length target, and a meaning guard runs on the client — a cosine-similarity check
  (≥ 0.85) rejects drift, the band's **compression ceiling** rejects an over-deep cut, and every
  citation `(Author, Year)` and number is verified preserved. On a recoverable rejection
  (over-compression, a changed citation, …) the paragraph is re-prompted **once** with a
  softer/corrective note rather than silently kept; if the whole document still falls short of the
  requested reduction, one **top-up pass** re-edits the wordiest remaining paragraphs.

Each `edit`/`proof` run writes its bundle into its own `output/<name> <YYYY-MM-DD HHMMSS>/` folder,
so repeated runs and multiple documents never overwrite or interleave. The bundle: `<name>_edited.md`
(clean text), `<name>.diff` (standard **unified diff** for any diff viewer), `<name>_review.md`
(repeated proofing suggestions), and a single report — `<name>_report.md` after `edit` (before/after
gauges across the same measures, whether the original's key terms still surface, the models used, and
the paragraph-referenced change log all in one file) or `<name>_changelog.md` after `proof` (the
change log alone).

> Quoted text (`"…"`, `'…'`, and indented block quotations) is **never** edited by any route.

## The GPU service (`cloud` backend)

`manage.py deploy` builds a container with the model baked in (`ollama serve` + a small Flask
wrapper, [cloud/serve.py](cloud/serve.py)) and deploys it as a Cloud Run service:

- **GPU + warm model** → a few seconds per paragraph once the instance is up (qwen2.5:7b on an L4).
- **Scale-to-zero** (`--min-instances 0`) → no cost when idle; the first request of a session loads
  the model (~30–90s cold), then every paragraph is fast.
- The client sends paragraphs **in parallel** (4 at a time) over HTTPS, guarded by the `JOB_TOKEN`;
  the meaning guard runs locally. Only paragraphs sent for editing ever leave the machine.

> **GPU required:** the service uses an NVIDIA **L4**. Ensure your region (default `europe-west1`)
> has L4 availability and `nvidia_l4` quota. Switch models with `MODEL` in `settings` + re-`deploy`.

## Cost reporting

Both LLM backends report the cost of a run:

- **api** — actual token usage priced by model (Haiku $1/$5, Sonnet $3/$15, Opus $5/$25 per 1M
  in/out); the shared system prompt is cached, cutting input cost on multi-paragraph runs.
- **cloud** — an estimate from active L4 service time (GPU + 4 vCPU + 16 GiB, per-second list price).

> Estimates only; verify current Anthropic and Cloud Run GPU pricing.

## Development

```
python -m pytest tests/ -q     # unit + integration tests (no Ollama/model/API needed)
```

## Dependencies and academic precedents

| Package | Purpose | Reference |
|---------|---------|-----------|
| spaCy + en_core_web_sm | Parse, sentence features, quotation detection | — |
| sentence-transformers | Redundancy detection; LLM meaning guard | — |
| language-tool-python | British/American English proofing (`proof`) | languagetool.org |
| textstat | Flesch readability (document + paragraph) | — |
| anthropic / ollama | LLM plain-language editing (`edit`) | — |

The redundancy test uses IDF-weighted overlap and marginal-novelty (MMR) selection from the IR
literature.
