import os

DEFAULT_MODEL = os.environ.get("KOPI_MODEL", "mistral-small")

_PARA_SYSTEM = (
    "You are a copy editor specialising in academic prose for the humanities and social sciences. "
    "Your task is to shorten the paragraph below by removing redundant or unnecessary words. Rules:\n"
    "1. Tighten sentences by cutting filler — prefer this to removing whole sentences.\n"
    "2. Only remove a sentence if it is entirely self-contained and referenced by no other sentence "
    "in the paragraph. Never remove a sentence referred to by 'the former', 'the latter', 'this', "
    "'these', 'the above', 'the following', or any pronoun that refers back to it.\n"
    "3. Preserve the author's analytical voice, disciplinary register, and sentence rhythms exactly. "
    "Do not homogenise the writing toward generic academic style.\n"
    "4. Hedging language (may, might, suggests, arguably, appears to, tends to) carries theoretical "
    "weight in humanities writing — preserve it unless it is demonstrably redundant.\n"
    "5. Preserve all disciplinary and field-specific terminology as-is. Do not substitute technical "
    "vocabulary with plainer alternatives.\n"
    "6. Preserve all citations (Author, Year), proper nouns, and numbers exactly. "
    "Author placeholders such as (199X), (202X), and (REF) must be kept verbatim — never "
    "invent or complete a date.\n"
    "7. Direct quotations in the text are marked with quotation marks. "
    "Preserve them verbatim — do not paraphrase, shorten, or reorder any quoted material.\n"
    "8. Return only the shortened paragraph — no explanation, no preamble."
)


# Normalised fat-index at/above which a paragraph gets the high-wordiness nudge.
_HIGH_FAT = 0.66


def _build_user_message(paragraph: str, budget=None, focus=None, fat_index=None) -> str:
    lines = []
    if budget:
        lines.append(
            f"Remove roughly {budget} words from this paragraph by tightening, "
            f"without altering its meaning."
        )
    if focus:
        focus_list = "; ".join(f'"{s}"' for s in focus)
        lines.append(f"The wordiest sentences are: {focus_list}. Concentrate your cuts there.")
    if fat_index is not None and fat_index >= _HIGH_FAT:
        lines.append(
            "This paragraph is flagged as high-wordiness — aim for substantial "
            "reduction, up to but not beyond the limit."
        )
    if lines:
        lines.append("")  # blank line before the paragraph
    lines.append(paragraph)
    return "\n".join(lines)


def edit_paragraph(paragraph: str, model: str = DEFAULT_MODEL, budget=None, focus=None,
                   fat_index=None) -> str:
    import ollama
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": _PARA_SYSTEM},
            {"role": "user", "content": _build_user_message(paragraph, budget, focus, fat_index)},
        ],
        options={"temperature": 0.1},
    )
    return response["message"]["content"].strip()
