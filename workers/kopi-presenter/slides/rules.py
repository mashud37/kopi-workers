"""Deterministic house rules applied to the LLM's slide JSON before rendering.

Layout-agnostic — enforced regardless of what the model returns.
"""


def _is_findings(sec: str) -> bool:
    return ("find" in sec) or ("result" in sec)


def _is_conclusion(sec: str) -> bool:
    return "conclu" in sec


def apply_house_rules(data: dict) -> dict:
    """
    1. Quotes (quote-green/quote-dark) are allowed ONLY on Findings/Results slides
       (material/data quotes). Elsewhere they are demoted to a plain `note`, so
       paraphrase is never dressed up as a verbatim quotation.
    2. Every content slide must carry bullets — a `statement` slide (just a title +
       big claim/sub) is converted to a bullet list.
    3. All Conclusion slides are merged into ONE plain bullet slide titled
       "Conclusions" with no evidence box.
    """
    for slide in data.get("slides", []):
        section = str(slide.get("section", "")).lower()
        body = slide.get("body") or {}

        # 1. quote gating
        ev = body.get("evidence")
        if ev and ev.get("kind") in ("quote-green", "quote-dark") and not _is_findings(section):
            body["evidence"] = {
                "kind": "note",
                "text": ev.get("text", ""),
                "source": ev.get("source", ""),
            }

        # 2. never a title-only / statement-only slide — force bullets
        if slide.get("layout") == "statement":
            slide["layout"] = "bullets"
            bullets = []
            if body.get("claim"):
                bullets.append({"text": body["claim"]})
            if body.get("sub"):
                bullets.append({"text": body["sub"]})
            body = {"bullets": bullets, "evidence": body.get("evidence")}

        slide["body"] = body

    # 3. merge all conclusion slides into one bullets slide
    slides = data.get("slides", [])
    concl_idx = [i for i, s in enumerate(slides)
                 if _is_conclusion(str(s.get("section", "")).lower())]
    if concl_idx:
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
        first = concl_idx[0]
        data["slides"] = [s for j, s in enumerate(slides) if j not in concl_idx[1:]]
        data["slides"][first if first < len(data["slides"]) else -1] = merged
    return data


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
