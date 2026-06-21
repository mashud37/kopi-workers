import os

DEFAULT_MODEL = os.environ.get("KOPI_MODEL", "qwen2.5:7b")

# The role and the kinds of edit to make never change. What changes with the
# requested reduction is the INTENSITY block (rules 1–2 below) — how hard to cut
# and whether a sentence may be dropped — selected by mode in `_system_for`.
_PREAMBLE = (
    "You are a line editor making one paragraph of academic prose clearer, more accessible, and "
    "tighter, following plain-language editing principles. This is COPY EDITING, NOT summarising: your "
    "edit must still say everything the original says — every claim, example, citation, and nuance — "
    "only more plainly.\n\n"
    "Edit the paragraph to:\n"
    "- cut filler, padding, and empty hedging (e.g. 'it is worth noting that', 'in order to', "
    "'the fact that', 'it is important to note');\n"
    "- prefer the active voice, and short plain words over long Latinate ones;\n"
    "- replace clichéd metaphors and idioms with direct statement;\n"
    "- split a sentence only if it is genuinely overlong or hard to follow.\n\n"
    "Hard rules:\n"
)

# Rules 1–2, selected by the run's intensity. These set how much length may change
# and whether whole sentences may go — the levers that must track the request.
_INTENSITY = {
    "clarity": (
        "1. THIS IS A CLARITY PASS, NOT A REDUCTION — the reader asked for plainer wording, not a "
        "shorter text. Keep EVERY sentence; do not merge or drop any. Keep every claim, example, "
        "citation, number, and nuance.\n"
        "2. Change the length as little as possible. Fix only outright wordiness — a redundant 'in "
        "order to', a doubled phrase, an empty hedge — and leave everything else exactly as long as "
        "it is. Most paragraphs should come back almost unchanged; returning a paragraph essentially "
        "as-is is a correct, expected outcome. Never remove more than a few words from a paragraph.\n"
    ),
    "light": (
        "1. PRESERVE ALL CONTENT. Keep every sentence — do not merge or drop any. Keep every claim, "
        "example, citation, number, and nuance; tighten only the wording inside sentences.\n"
        "2. Tighten lightly. Cut clear filler, padding, and empty hedging, and prefer plain words, "
        "but expect to remove only a small share of words. Leave lean sentences untouched — do not "
        "force a cut where nothing is wasteful.\n"
    ),
    "firm": (
        "1. PRESERVE ALL CONTENT. Tighten wording within sentences. You MAY merge a short follow-on "
        "sentence into the one before it when it merely restates or weakly extends the same point — "
        "absorb it as a clause, do not drop it. You MAY remove a sentence only if it is purely "
        "redundant: it repeats a point already made in full and adds no new claim, example, or "
        "nuance. Never summarise, never compress two distinct points into one, and never drop an "
        "example or aside that carries independent meaning. If a sentence makes its own point, keep "
        "it.\n"
        "2. Tighten firmly. Academic prose is usually padded; wordy sentences, hedged openings, and "
        "roundabout phrasing are exactly what to cut — do not leave a wordy passage standing because "
        "it is grammatical. Reduce a wordy passage markedly (commonly 15–30% of its words); leave a "
        "genuinely lean one almost untouched. Never keep a sentence long merely to stay close to the "
        "original length. The one limit is content — do not cut more than about a third of a "
        "paragraph, since beyond that you are dropping points rather than tightening wording.\n"
    ),
    "aggressive": (
        "1. PRESERVE THE SUBSTANCE, CUT THE REST — THE AUTHOR HAS ASKED FOR A MAJOR REDUCTION. Keep "
        "every DISTINCT claim, every citation, every number, and the author's argument and analytical "
        "voice. But you MAY now drop a sentence outright when it is redundant or marginal — it "
        "restates a point already made, labours an example the reader already grasps, or adds an "
        "aside the argument does not need — and you SHOULD merge weak follow-on sentences into the "
        "one before them.\n"
        "2. Reduce substantially. Compress wordy passages hard and use the shortest faithful wording "
        "throughout. Cut words and weak sentences freely; the only things you may never cut are a "
        "distinct point, a citation, and a number. Do not pad to reach a length, and do not cut so "
        "much that a claim, a load-bearing example, or a real nuance disappears.\n"
    ),
}

# Rules 3–8 hold for every intensity.
_FIXED_RULES = (
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
    "'(split for clarity)', or '(rephrased)')."
)

_EXAMPLES = (
    "Examples of good edits (every claim survives; wordy phrasing is cut hard, lean phrasing is left "
    "alone):\n\n"
    "Original: It is worth noting that the data, which were collected over a period of several "
    "months, were subsequently analysed by the research team in order to determine whether a "
    "relationship existed between the two variables.\n"
    "Edited: The data, collected over several months, were analysed to determine whether the two "
    "variables were related.\n"
    "(All content survives; the padding — 'It is worth noting that', 'over a period of', 'in order "
    "to', 'subsequently' — is gone, a third of the words with it.)\n\n"
    "Original: It should be borne in mind that the participants who took part in the study had, for "
    "the most part, relatively little prior experience with the technology being examined.\n"
    "Edited: Most participants had little prior experience with the technology examined.\n"
    "(A wordy sentence cut to its substance — no point lost.)\n\n"
    "Original: Miller (2011) argues that social media reflect the cultures in which they are "
    "embedded.\n"
    "Edited: Miller (2011) argues that social media reflect the cultures they are embedded in.\n"
    "(Already lean — only a tiny change; do not force a cut where nothing is wasteful, and the "
    "citation is untouched.)"
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


def _system_for(lang: str = "british", mode: str = "firm") -> str:
    intensity = _INTENSITY.get(mode, _INTENSITY["firm"])
    return f"{_PREAMBLE}{intensity}{_FIXED_RULES}\n\n{_EXAMPLES}\n\n{_spelling_rule(lang)}"


def _build_user_message(paragraph: str, instructions=None, floor: int | None = None) -> str:
    """The user turn: optional editor's notes + length target, then the paragraph.

    ``instructions`` is the per-paragraph directive list from ``kopi.diagnose``
    (categorical guidance such as "Remove hedges and padding"). ``floor`` is the
    soft word target for this paragraph when a reduction was requested — a concrete
    number a small model follows far better than "be concise". Both are clearly
    fenced and labelled; rule 7 forbids echoing them. With neither, the user turn
    is just the paragraph.
    """
    notes = list(instructions or [])
    if floor is not None:
        orig = len(paragraph.split())
        if floor < orig:
            notes.append(
                f"Length target for this paragraph: aim for about {floor} words (it has {orig} now). "
                "This is a guide — never drop a distinct point, citation, or number to hit it."
            )
    if not notes:
        return paragraph
    note_block = "\n".join(f"- {line}" for line in notes)
    return (
        "Editor's notes for this paragraph (apply silently, do not repeat):\n"
        f"{note_block}\n\n"
        "Paragraph:\n"
        f"{paragraph}"
    )


def build_messages(paragraph: str, instructions=None, lang: str = "british",
                   mode: str = "firm", floor: int | None = None) -> list[dict]:
    """The full chat messages for one paragraph edit.

    Built on the client (local pass and cloud client both use this), so the prompt
    lives in one place and prompt changes need no service redeploy — the Cloud Run
    service just relays these messages to Ollama. ``mode`` selects the intensity
    block; ``floor`` adds the per-paragraph length target.
    """
    return [
        {"role": "system", "content": _system_for(lang, mode)},
        {"role": "user", "content": _build_user_message(paragraph, instructions, floor)},
    ]


def edit_paragraph(paragraph: str, model: str = DEFAULT_MODEL, instructions=None,
                   lang: str = "british", mode: str = "firm", floor: int | None = None) -> str:
    import ollama
    response = ollama.chat(
        model=model,
        messages=build_messages(paragraph, instructions, lang, mode, floor),
        options={"temperature": 0.1},
        # Keep the model resident between paragraphs so each call skips the
        # cold-load (the dominant per-call overhead).
        keep_alive="10m",
    )
    return response["message"]["content"].strip()
