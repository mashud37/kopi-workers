"""Validate slide JSON against house-style rules and attempt auto-repair via LLM."""

import json
import re

import anthropic

_VALID_LAYOUTS = {
    "split",
    "iconrow",
    "cards",
    "matrix",
    "stepflow",
    "statement",
    "bullets",
    "boxes",
    "circle",
    "prose",
}


def lint_and_repair(slide_data: dict, original_content: str, config: dict) -> dict:
    print("       Checking slide JSON ...")
    errors = _lint(slide_data)
    if not errors:
        print("       Lint: OK")
        return slide_data

    print(f"       Lint: {len(errors)} issue(s) found")
    for e in errors:
        print(f"         • {e}")

    if not config.get("linter", {}).get("auto_repair", True):
        print("       Auto-repair disabled, proceeding with original JSON")
        return slide_data

    print("       Attempting repair ...")
    repaired = _repair(slide_data, errors, config)

    print("       Verifying repair ...")
    second = _lint(repaired)
    if not second:
        print("       Repair: OK")
    else:
        print(f"       Repair incomplete: {len(second)} issue(s) remain (proceeding):")
        for e in second:
            print(f"         • {e}")
    return repaired


# ---- Lint rules ----

def _lint(data: dict) -> list[str]:
    errors: list[str] = []

    meta = data.get("meta", {})
    for field in ("title", "author", "venue"):
        if not meta.get(field):
            errors.append(f"meta.{field} is missing or empty")

    sections = data.get("sections", [])
    if not (4 <= len(sections) <= 6):
        errors.append(f"sections has {len(sections)} items; expected 4–6")

    slides = data.get("slides", [])
    if not slides:
        errors.append("slides array is empty")

    section_set = set(sections)

    for i, slide in enumerate(slides):
        pfx = f"slides[{i}] '{slide.get('title', '?')}'"

        if not slide.get("title"):
            errors.append(f"{pfx}: missing title")

        sec = slide.get("section", "")
        if sec and sec not in section_set:
            errors.append(f"{pfx}: section '{sec}' not in sections list")

        layout = slide.get("layout", "")
        if layout not in _VALID_LAYOUTS:
            errors.append(f"{pfx}: unknown layout '{layout}'")

        body = slide.get("body", {})
        bullets = body.get("bullets", [])

        if len(bullets) > 4:
            errors.append(f"{pfx}: {len(bullets)} bullets (cap is 4)")

        for j, b in enumerate(bullets):
            wc = len(b.get("text", "").split())
            if wc > 24:
                errors.append(f"{pfx} bullet[{j}]: {wc} words, shorten to ≤18")

    return errors


# ---- Repair ----

def _repair(slide_data: dict, errors: list[str], config: dict) -> dict:
    api_key = config.get("api", {}).get("anthropic_key", "")
    model = config.get("llm", {}).get("model", "claude-haiku-4-5-20251001")

    max_tokens = config.get("llm", {}).get("max_tokens", 8192)
    client = anthropic.Anthropic(api_key=api_key)
    error_list = "\n".join(f"- {e}" for e in errors)

    prompt = (
        f"Fix the following validation errors in the slide JSON. "
        f"Shorten over-long bullets by distilling to the essential phrase "
        f"(do not just truncate). Return ONLY the corrected JSON, no fences, no prose.\n\n"
        f"ERRORS:\n{error_list}\n\n"
        f"JSON:\n{json.dumps(slide_data, indent=2, ensure_ascii=False)}"
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\n?```\s*$", "", raw, flags=re.MULTILINE)
        return json.loads(raw.strip())
    except Exception as exc:
        print(f"       Repair call failed ({exc}), using original JSON")
        return slide_data
