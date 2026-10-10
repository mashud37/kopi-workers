# kopi-presenter

Turns a manuscript or an outline into a styled PowerPoint deck and a PDF. It reads `.docx`, `.md`
and `.txt` files and needs an Anthropic key.

## How it works

Claude reads the text and writes a slide plan: the sections, the slides in each, a layout for each
slide, and the evidence it shows. The plan is then checked against house rules, such as quotes only
on findings slides and a single conclusions slide, and the deck is built from it. PowerPoint, or
LibreOffice where PowerPoint is not installed, exports the PDF.

## Use it

1. Drop a manuscript or an outline on the page. Documents already dropped on the editor's page
   are listed too.
2. Run **slides**. **venue** adds a venue line, such as `ICA 2027`.
3. The deck, its PDF and the slide plan appear in a new dated folder under **Results**.

| Option | What it does |
|---|---|
| **condense** | Sends only each paragraph's first and last sentence, for a cheaper plan of a long text |
| **emoji** | Uses colour emoji in place of the default icons |
| **no-pdf** | Builds the deck without exporting a PDF |

## Model

The **Models** page chooses which model writes the plan; [Models](models.md) explains the choices.
A run prints its cost when it finishes.
