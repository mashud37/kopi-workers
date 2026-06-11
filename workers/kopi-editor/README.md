# kopi-editor

Academic copyeditor for humanities and social sciences. Targets British English by default. Runs locally with no cloud API calls.

## What it does

Takes a `.docx` file and a word-reduction target, then runs the text through a 12-step pipeline:

| Step | Name | What it does |
|------|------|-------------|
| 1 | Count | Baseline word count |
| 2 | Filler scan | Removes academic idioms and wordiness phrases |
| 3 | Proselint | Flags redundancy, clichés, and weasel words |
| 4 | Syntax transforms | Removes intensifiers; reduces relative clauses |
| 5 | Redundancy scan | Flags semantically similar sentences for author review |
| 6 | Sentence merge | Combines short follow-on sentences |
| 7 | Reduce | Applies all flagged edits from earlier steps |
| 8 | Plain language | Substitutes latinate vocabulary; removes clichés |
| 9 | Proofing | LanguageTool British English grammar check |
| 10 | Concision | Ollama LLM — paragraph-level tightening |
| 11 | Evaluate | Mu & Lim 2022 benchmark (optional) |
| 12 | Final check | Flags, readability, dep-depth delta |

Quoted text (`"..."`, `'...'`, and indented block quotations) is never edited.

**Sentence removal only happens in Step 10.** All earlier steps edit words and phrases within sentences. The LLM sees the full paragraph so it can preserve cross-sentence references (the former, the latter, this, these).

## Folders

```
input/    # put source .docx files here
output/   # generated .md files are written here
docs/     # reference docs (e.g. the original agent prompt spec)
data/     # bundled datasets (Mu & Lim sample)
kopi/     # pipeline package
tests/    # pytest suite
```

A bare filename is resolved against `input/` automatically, so `python run.py "chapter 1.docx" 1000` finds `input/chapter 1.docx`. An explicit or absolute path still works. Both folders are kept in the repo via `.gitkeep`; their contents (manuscripts and generated artifacts) are git-ignored.

## Output

Four files are written to `output/`:

- `<name>_edited.md` — clean edited text
- `<name>_changelog.md` — paragraph-referenced change log with rule citations
- `<name>_diff.md` — unified diff of all changes (open in VS Code diff viewer)
- `<name>_review.md` — proofing suggestions that appeared multiple times; decide once and apply globally *(only created when applicable)*

## Installation

Requires Python 3.10 or later.

```
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

All Python dependencies (including proselint and language-tool-python) are in `requirements.txt`. Notes on first-run downloads:

- **sentence-transformers** (`all-MiniLM-L6-v2`, ~40 MB) — downloads automatically
- **LanguageTool** (~200 MB Java engine) — downloads on first proofing run, then works offline

### Ollama (Step 10 — LLM concision, local model)

```
# Install from https://ollama.com, then pull your preferred model tier:
ollama pull gemma3:4b        # lightweight — fast, CPU-viable
ollama pull mistral-small    # standard (default)
ollama pull qwen3.5:27b      # high-tier
```

The LLM processes paragraphs, not sentences. It is given explicit instructions to preserve cross-sentence references and is rejected if the edited paragraph drifts more than 15% in meaning (cosine similarity guard). No data leaves the machine.

## Usage

```
python run.py <file.docx> <words_to_remove> [options]
```

| Argument | Description |
|----------|-------------|
| `file.docx` | Input document — a bare name is resolved against `input/` |
| `words_to_remove` | Number of words to remove (not target length) |
| `--lang american` | Use American English (default: British) |
| `--no-llm` | Skip LLM step — deterministic edits only |
| `--llm local` / `--llm cloud` | Run the LLM phase non-interactively (no `[l/c/N]` prompt). Use this when stdin isn't an interactive terminal |
| `--rules-only` | Steps 1–8 only — no proofing or LLM |
| `--no-second-pass` | Disable the automatic second LLM pass when the first undershoots target |
| `--evaluate` | Run Mu & Lim 2022 benchmark after editing |
| `--cloud-job` | Full pipeline inside a Cloud Run container (reads/writes via GCS) |

### Interactive flow

The pipeline runs in two phases:

**Phase 1 — Deterministic** (always local, fast)

1. Pipeline runs steps 1–9
2. Repeated proofing suggestions are presented one at a time: `'personalization' -> 'personalisation' (5x at P2, P5...) — Apply everywhere? [y/N/q]`
3. Outputs are written: `_edited.md`, `_changelog.md`, `_diff.md`
4. Flags are printed: word count gap, hard paragraphs by label, redundant sentences for author review

**Phase 2 — LLM tightening** (only flagged paragraphs)

```
52 paragraph(s) flagged for LLM tightening.
  [l] Local Ollama
  [c] Cloud Run
  [N] Skip
Choice:
```

- **l**: Ollama must be running locally (`ollama serve`)
- **c**: Only the flagged paragraphs are uploaded to GCS; a Cloud Run job processes them with Ollama and returns results — the full document never leaves your machine for this path
- **N**: Keep phase 1 outputs as-is

### Examples

```
# Standard run:
python run.py paper.docx 1000

# Fast pass — no Java or Ollama required:
python run.py paper.docx 1000 --rules-only

# Deterministic edits + proofing, no LLM:
python run.py paper.docx 1000 --no-llm
```

## Benchmark evaluation

The `--evaluate` flag runs a 50-sentence sample from the Mu & Lim (2022) Revision-for-Concision dataset and reports:

- Mean TER (Translation Edit Rate) against human reference revisions
- Mean cosine similarity to human references (via sentence-transformers)
- Count of sentences shortened

```
# See data/revision_for_concision/ for the 50-pair sample
# Full dataset: https://github.com/sutdcse/concision
```

## Cloud Run setup

The LLM runs inside the Cloud Run container via Ollama — no external model API is used at any point.

Run the interactive setup script to provision everything in one go:

```
python cloud/setup_cloud.py
```

It walks you through project selection, model choice, and creates the Artifact Registry repo, GCS bucket, Docker image (via Cloud Build), service account, and Cloud Run job. The steps below document what it does, for reference.

### Prerequisites

1. **Google Cloud project** with billing enabled
2. **gcloud CLI** installed and authenticated (`gcloud auth login`)
3. **APIs enabled** in your project:
   ```bash
   gcloud services enable run.googleapis.com \
     cloudbuild.googleapis.com \
     storage.googleapis.com \
     artifactregistry.googleapis.com
   ```
4. **Artifact Registry repository** to store the Docker image:
   ```bash
   gcloud artifacts repositories create kopi \
     --repository-format docker \
     --location europe-west1
   ```
5. **GCS bucket** for passing paragraphs between the local script and the cloud job:
   ```bash
   gsutil mb -l europe-west1 gs://YOUR_BUCKET_NAME
   ```

### Build and push the image

The easiest way is to run the interactive setup script, which handles everything:

```bash
python cloud/setup_cloud.py
```

Or manually via `cloudbuild.yaml` (the model is baked into the image at build time):

```bash
IMAGE=europe-west1-docker.pkg.dev/YOUR_PROJECT/kopi/kopi-editor

# Build with the standard model (mistral-small):
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions _KOPI_MODEL=mistral-small,_IMAGE=$IMAGE
```

Building bakes the model into the image, so the container starts immediately without a download. Build times:

| Model | Image size | Build time |
|-------|-----------|------------|
| gemma3:4b | ~4 GB | ~10 min |
| mistral-small | ~14 GB | ~20 min |
| qwen3.5:27b | ~18 GB | ~25 min |

### Create the LLM paragraph job

This is what the interactive `[c]` option uses. Only the flagged paragraphs (not the full document) are uploaded to GCS.

```bash
IMAGE=europe-west1-docker.pkg.dev/YOUR_PROJECT/kopi/kopi-editor

# Resource requirements depend on model:
#   gemma3:4b     -> 2 CPU, 4Gi
#   mistral-small -> 4 CPU, 16Gi
#   qwen3.5:27b   -> 4 CPU, 16Gi

gcloud run jobs create kopi-editor-llm \
  --image $IMAGE \
  --command "./entrypoint_llm.sh" \
  --region europe-west1 \
  --cpu 4 --memory 16Gi \
  --max-retries 0 --task-timeout 20m
```

### Service account permissions

The Cloud Run job needs read/write access to your GCS bucket:

```bash
PROJECT=$(gcloud config get-value project)
SA=kopi-runner@${PROJECT}.iam.gserviceaccount.com

gcloud iam service-accounts create kopi-runner \
  --display-name "kopi-editor Cloud Run"

gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:$SA" \
  --role roles/storage.objectAdmin

gcloud run jobs update kopi-editor-llm \
  --service-account $SA \
  --region europe-west1
```

### Local environment variables

```bash
export KOPI_BUCKET=YOUR_BUCKET_NAME
export KOPI_REGION=europe-west1       # default
export KOPI_LLM_JOB=kopi-editor-llm  # default
```

Add these to your shell profile (`~/.zshrc`, `~/.bashrc`, or `$PROFILE` on Windows) so they persist between sessions.

### Run

```bash
python run.py chapter.docx 1000
# ... deterministic phase runs locally ...
# Select [c] at the LLM prompt, then choose model
```

Cost estimates per chapter (~6 000 words, 50 paragraphs):

| Model | Speed | Est. cost |
|-------|-------|----------|
| gemma3:4b | fast | < $0.03 |
| mistral-small | medium | < $0.05 |
| qwen3.5:27b | slow | < $0.08 |

### Option B — Full pipeline in Cloud Run (non-interactive)

For batch or CI workflows where the full pipeline runs unattended in the cloud:

```bash
gcloud run jobs create kopi-editor \
  --image $IMAGE \
  --region europe-west1 \
  --cpu 4 --memory 8Gi \
  --max-retries 0 --task-timeout 30m \
  --service-account $SA

gcloud run jobs execute kopi-editor \
  --region europe-west1 \
  --args="gs://YOUR_BUCKET/chapter.docx,1000"
```

## Development

```
python -m pytest tests/ -q     # unit + integration tests (no Ollama/model needed)
python calibrate.py            # summarise the Step 10 calibration log for tuning routing
```

Step 10 routing flags the wordiest paragraphs (a composite "fat-index" in `kopi/signals.py`) up to the word target, logs per-paragraph compression to `~/.kopi/calibration.jsonl` (override with `KOPI_CALIBRATION_LOG`), and runs an automatic second LLM pass if the first undershoots (disable with `--no-second-pass`). `calibrate.py` summarises that log so you can hand-tune the routing constants.

## Dependencies and academic precedents

| Package | Purpose | Reference |
|---------|---------|-----------|
| spaCy + en_core_web_sm | Parse, NER, DependencyMatcher | — |
| sentence-transformers | Redundancy detection; LLM similarity guard | — |
| proselint | Redundancy, clichés, weasel words | Pacer & Suchow, SciPy 2016 |
| language-tool-python | British English proofing | languagetool.org |
| textstat | Flesch readability (document + paragraph) | — |
| ollama | Local LLM concision | Mu & Lim, TSAR-EMNLP 2022 |

Syntactic transforms in Step 4 follow the DEPSYM/PSET tradition (Sikka & Mago 2021; Carroll et al. 1999; Chandrasekar & Srinivas 1997). The dependency depth proxy for voice preservation follows Lu (2010).

## Design constraints

- Steps 1–9 are word/phrase edits only — no sentence is removed by any deterministic rule
- Sentence removal only happens in Step 10 (LLM), which sees the full paragraph
- The LLM processes paragraphs, not sentences — it can reason about cross-sentence references
- Cosine similarity guard (≥ 0.85) ensures the edited paragraph preserves the original meaning
- All citation patterns (`(Author, Year)`) and numeric tokens are verified preserved before accepting LLM edits
- Maximum compression per paragraph: 40%
- Flags in the change log are advisory — the author decides whether to act on them
- No data is sent to any external API at any point
