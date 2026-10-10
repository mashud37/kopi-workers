# kopi-presenter

Turns a manuscript or outline into a styled PowerPoint deck and a PDF in one command. Only the text
sent to the model leaves the machine.

## How it works

A language model distils the text into a slide plan (sections, slides, layouts, evidence). Python
then checks the plan against house rules (quotes only on findings slides, one conclusions slide)
and builds the deck; PowerPoint or LibreOffice exports the PDF.

```mermaid
flowchart LR
    DOC[/"input/ manuscript"/] --> LLM["slide plan"]
    LLM --> RULES["house rules"]
    RULES --> PPTX[("output/ .pptx")]
    PPTX --> PDF[("output/ .pdf")]
```

## Setup

```powershell
pip install -r requirements.txt
python manage.py install
```

Set `api.anthropic_key` in `config.local.yaml`, or the `ANTHROPIC_API_KEY` environment variable.
For any server that accepts OpenAI's chat format, set `llm.backend: openai-compatible`,
`llm.base_url` and `llm.server_model` there instead, with its key in `api.llm_key` or
`KOPI_LLM_API_KEY`.

## Commands

`python manage.py` with no arguments opens the menu.

| Action | Command |
|---|---|
| Build a deck | `python manage.py slides paper.docx` |
| Review and revise the plan before building | `python manage.py slides paper.docx --review` |
| Rebuild from a saved plan without a model call | `python manage.py slides paper.docx --plan "output/paper slides <time>/paper.json"` |
| Show the configuration | `python manage.py config` |
| Check dependencies and create `config.local.yaml` | `python manage.py install` |
