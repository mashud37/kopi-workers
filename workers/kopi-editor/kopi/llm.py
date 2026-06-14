import os

DEFAULT_MODEL = os.environ.get("KOPI_MODEL", "qwen2.5:7b")

_PARA_SYSTEM = (
    "You are a line editor making one paragraph of academic prose clearer and more accessible, "
    "following plain-language editing principles. This is COPY EDITING, NOT summarising: your "
    "edit must still say everything the original says — every claim, example, citation, and nuance — "
    "only more plainly.\n\n"
    "Edit the paragraph to:\n"
    "- cut filler, padding, and empty hedging (e.g. 'it is worth noting that', 'in order to', "
    "'the fact that', 'it is important to note');\n"
    "- prefer the active voice, and short plain words over long Latinate ones;\n"
    "- replace clichéd metaphors and idioms with direct statement;\n"
    "- split a sentence only if it is genuinely overlong or hard to follow.\n\n"
    "Hard rules:\n"
    "1. PRESERVE ALL CONTENT. Tighten wording WITHIN each sentence. Do not delete whole sentences, "
    "drop examples or asides, or compress two points into one. Never summarise. Keep every distinct "
    "point the original makes; if a sentence cannot be shortened without losing meaning, leave it.\n"
    "2. Stay close to the original length — typically 10–25% shorter, and NEVER more than a third "
    "shorter. Tightening wording is the goal, not making the paragraph small.\n"
    "3. KEEP THE PROSE FLOWING — read it aloud in your head. Vary sentence length and openings, and "
    "join related ideas with natural connectives (and, but, which, because, while). Do NOT produce a "
    "string of short choppy sentences, and do NOT begin consecutive sentences with the same word. "
    "Plain does not mean staccato.\n"
    "4. Preserve the author's argument, analytical voice, and disciplinary register. Keep genuine "
    "hedging (may, might, suggests, arguably, appears to) — it carries theoretical weight.\n"
    "5. Keep all field-specific terminology as-is; plain-word swaps apply only to ordinary long "
    "words, not terms of art.\n"
    "6. Preserve every citation (Author, Year), placeholder (199X, 202X, REF), proper noun, number, "
    "and quoted phrase EXACTLY — never invent, complete, alter, or drop one.\n"
    "7. The user turn may include editor's notes — apply them but NEVER repeat or mention them.\n"
    "8. Return ONLY the edited paragraph itself, as a SINGLE paragraph on one line — no line breaks "
    "or blank lines, even if you split a sentence in two. No preamble, no explanation, and no "
    "parenthetical comments about your changes (never write things like '(Note: ...)', "
    "'(split for clarity)', or '(rephrased)').\n\n"
    "Examples of good edits (note how all content survives and the length barely drops):\n\n"
    "Original: It is worth noting that the data, which were collected over a period of several "
    "months, were subsequently analysed by the research team in order to determine whether a "
    "relationship existed between the two variables.\n"
    "Edited: The data, collected over several months, were then analysed by the research team to "
    "determine whether a relationship existed between the two variables.\n\n"
    "Original: Miller (2011) argues that social media reflect the cultures in which they are "
    "embedded.\n"
    "Edited: Miller (2011) argues that social media reflect the cultures they are embedded in.\n"
    "(Already clear — barely changed, and the citation is untouched.)"
)


def _spelling_rule(lang: str) -> str:
    """A strong, explicit spelling-variety rule — small models default to American
    spelling unless told otherwise, which is wrong for a British-English text."""
    if lang == "american":
        return ("SPELLING: Use American spelling and conventions throughout "
                "(-ize, -or, -er) and keep them consistent.")
    return ("SPELLING: This text uses BRITISH English. Keep British spelling and conventions "
            "— -ise (not -ize), -our (not -or), -re (not -er): e.g. personalise, behaviour, "
            "organisation, centre. NEVER convert a British spelling to its American form.")


def _system_for(lang: str = "british") -> str:
    return f"{_PARA_SYSTEM}\n\n{_spelling_rule(lang)}"


def _build_user_message(paragraph: str, instructions=None) -> str:
    """The user turn: optional editor's notes, then the paragraph to edit.

    ``instructions`` is the per-paragraph directive list from ``kopi.diagnose``
    (categorical guidance such as "Remove hedges and padding"). The notes are
    clearly fenced and labelled as instructions; rule 6 of the system prompt
    forbids echoing them, so unlike the old verbatim-snippet hints they cannot
    leak into the edited text. With no notes, the user turn is just the paragraph.
    """
    if instructions:
        notes = "\n".join(f"- {line}" for line in instructions)
        return (
            "Editor's notes for this paragraph (apply silently, do not repeat):\n"
            f"{notes}\n\n"
            "Paragraph:\n"
            f"{paragraph}"
        )
    return paragraph


def build_messages(paragraph: str, instructions=None, lang: str = "british") -> list[dict]:
    """The full chat messages for one paragraph edit.

    Built on the client (local pass and cloud client both use this), so the
    prompt lives in one place and prompt changes need no service redeploy — the
    Cloud Run service just relays these messages to Ollama.
    """
    return [
        {"role": "system", "content": _system_for(lang)},
        {"role": "user", "content": _build_user_message(paragraph, instructions)},
    ]


def edit_paragraph(paragraph: str, model: str = DEFAULT_MODEL, instructions=None,
                   lang: str = "british") -> str:
    import ollama
    response = ollama.chat(
        model=model,
        messages=build_messages(paragraph, instructions, lang),
        options={"temperature": 0.1},
        # Keep the model resident between paragraphs so each call skips the
        # cold-load (the dominant per-call overhead).
        keep_alive="10m",
    )
    return response["message"]["content"].strip()
