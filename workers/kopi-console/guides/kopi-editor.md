# kopi-editor

Copy-edits an academic Word document into plainer prose while keeping the argument, the author's
voice, the citations and the quotations. It reads `.docx` files.

## How it works

The document is read on your computer and each paragraph is diagnosed for what it needs: fewer
words, no restated sentences, active voice, shorter sentences. What happens next depends on the
command:

| Command | What it does | Model |
|---|---|---|
| **analyze** | Reports readability, filler phrases and restated sentences, and how many words could go | none |
| **proof** | Removes filler and padding, swaps cliches and long words for plain ones | none |
| **edit** | Sends each paragraph to a model with its diagnosis and keeps the edits that pass the guard | the one chosen in Settings |

The guard rejects any edit that changes a citation, a number or the meaning of the paragraph, and
keeps the original paragraph instead. Quotations are never sent for editing.

## Use it

1. Drop a `.docx` on the page.
2. Run **analyze** to see how much the document can lose.
3. Run **proof** for the safe fixes alone, or **edit** for a full edit. **edit** takes the number
   of words to remove as a guide: a small number tightens the wording, a large one also drops
   restated sentences, and a blank asks only for plainer wording.
4. Each run writes a folder under **Results**, named after the document, the command and the
   time:

| File | What it holds |
|---|---|
| `_edited.md` | The edited text |
| `_side-by-side.md` | Each paragraph before and after, unchanged ones marked |
| `_changelog.md` or `_report.md` | Every change, step by step, and the readability before and after |
| `.diff` | The changes line by line |

**analyze** writes one `_analysis.md` report instead. To turn the edited text into slides, open
`_edited.md` and choose **Copy to documents**; it then appears in kopi-presenter's file list.

## Settings

**Who edits** chooses the model behind **edit**; [Models](models.md) explains the choices. There
is no default Claude model, so every paid run is a deliberate choice. **Spelling** is British or
American.
