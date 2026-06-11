import re

_PATTERN = re.compile(
    '[“”"][^“”"\n]{1,600}[“”"]'  # double quotes
    '|‘[^‘’\n]{1,600}’'  # ‘single’ curly quotes
    '|⟪[^⟫]{1,4000}⟫',        # block quotations
)


def guard(text: str) -> tuple[str, dict]:
    qmap = {}
    counter = [0]

    def _replace(m):
        token = f"§Q{counter[0]}§"
        qmap[token] = m.group(0)
        counter[0] += 1
        return token

    return _PATTERN.sub(_replace, text), qmap


def unguard(text: str, qmap: dict) -> str:
    for token, original in qmap.items():
        if original.startswith('⟪') and original.endswith('⟫'):
            text = text.replace(token, '> ' + original[1:-1])
        else:
            text = text.replace(token, original)
    return text


def word_count(text: str, qmap: dict) -> int:
    return len(unguard(text, qmap).split())
