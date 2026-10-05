"""Apply the deterministic house rules to the model's slide JSON before rendering,
whatever layouts it returned.
"""


def _is_findings(sec: str) -> bool:
    return ("find" in sec) or ("result" in sec)


def _is_conclusion(sec: str) -> bool:
    return "conclu" in sec


def _gate_quotes(body: dict, section: str) -> dict:
    """Quotes (quote-green/quote-dark) are allowed ONLY on Findings/Results slides
    (material/data quotes). Elsewhere they are demoted to a plain `note`, so
    paraphrase is never dressed up as a verbatim quotation."""
    ev = body.get("evidence")
    if ev and ev.get("kind") in ("quote-green", "quote-dark") and not _is_findings(section):
        return {**body, "evidence": {
            "kind": "note",
            "text": ev.get("text", ""),
            "source": ev.get("source", ""),
        }}
    return body


def _force_bullets(slide: dict, body: dict) -> dict:
    """Every content slide must carry bullets: a `statement` slide (just a title +
    big claim/sub) is converted to a bullet list."""
    if slide.get("layout") != "statement":
        return {**slide, "body": body}
    bullets = []
    if body.get("claim"):
        bullets.append({"text": body["claim"]})
    if body.get("sub"):
        bullets.append({"text": body["sub"]})
    new_body = {"bullets": bullets, "evidence": body.get("evidence")}
    return {**slide, "layout": "bullets", "body": new_body}


def _apply_slide_rules(slide: dict) -> dict:
    section = str(slide.get("section", "")).lower()
    body = slide.get("body") or {}
    body = _gate_quotes(body, section)
    return _force_bullets(slide, body)


def _merge_conclusion_slides(slides: list[dict]) -> list[dict]:
    """All Conclusion slides are merged into ONE plain bullet slide titled
    "Conclusions" with no evidence box."""
    concl_idx = [i for i, s in enumerate(slides)
                 if _is_conclusion(str(s.get("section", "")).lower())]
    if not concl_idx:
        return slides

    bullets = []
    for i in concl_idx:
        bullets += _derive_bullets(slides[i])
    seen, deduped = set(), []
    for b in bullets:
        key = b.get("text", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(b)
    merged = {
        "section": slides[concl_idx[0]].get("section", "Conclusion"),
        "title": "Conclusions",
        "layout": "bullets",
        "body": {"bullets": deduped[:5]},
    }
    kept = [s for j, s in enumerate(slides) if j not in concl_idx[1:]]
    first = concl_idx[0]
    position = first if first < len(kept) else -1
    kept[position] = merged
    return kept


def apply_house_rules(data: dict) -> dict:
    """Apply the quote gate and the statement-to-bullets rule to every slide, then
    merge all conclusion slides into one. Returns a new plan, `data` is untouched."""
    slides = [_apply_slide_rules(slide) for slide in data.get("slides", [])]
    slides = _merge_conclusion_slides(slides)
    return {**data, "slides": slides}


def _derive_bullets(slide: dict) -> list[dict]:
    """Pull plain bullet dicts out of whatever layout a slide used."""
    body = slide.get("body") or {}
    if body.get("bullets"):
        return [{"text": b.get("text", "")} for b in body["bullets"] if b.get("text")]
    out = []
    if body.get("claim"):
        out.append({"text": body["claim"]})
    if body.get("sub"):
        out.append({"text": body["sub"]})
    out += [{"text": str(s)} for s in body.get("steps", []) if str(s).strip()]
    for c in body.get("cards", []):
        if c.get("text"):
            out.append({"text": c["text"]})
    for cell in body.get("cells", []):
        txt = cell.get("text") or cell.get("label")
        if txt:
            out.append({"text": txt})
    return out
