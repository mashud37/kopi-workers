import re

_PATTERN = re.compile(
    '[“”"][^“”"\n]{1,600}[“”"]'  # double quotes
    '|‘[^‘’\n]{1,600}’'  # ‘single’ curly quotes
    '|⟪[^⟫]{1,4000}⟫',        # block quotations
)


def guard(text: str) -> dict:
    """The `text` with every quotation swapped for a placeholder, and the `qmap` back."""
    qmap = {}
    pieces = []
    last_end = 0
    for match in _PATTERN.finditer(text):
        token = f"§Q{len(qmap)}§"
        qmap[token] = match.group(0)
        pieces.append(text[last_end:match.start()])
        pieces.append(token)
        last_end = match.end()
    pieces.append(text[last_end:])
    return {"text": "".join(pieces), "qmap": qmap}


def unguard(text: str, qmap: dict) -> str:
    for token, original in qmap.items():
        if original.startswith('⟪') and original.endswith('⟫'):
            text = text.replace(token, '> ' + original[1:-1])
        else:
            text = text.replace(token, original)
    return text


def word_count(text: str, qmap: dict) -> int:
    return len(unguard(text, qmap).split())
