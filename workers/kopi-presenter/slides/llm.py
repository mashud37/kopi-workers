"""Claude Haiku API integration: manuscript → structured slide JSON."""

import json
import re
from typing import Optional

import anthropic

# ---------------------------------------------------------------------------
# System prompt — condensed for token efficiency while preserving all rules.
# ~1 500 tokens; cached across calls so input cost is minimal.
# ---------------------------------------------------------------------------
_SYSTEM = """You are a slide-generation assistant for academic conference presentations.
Convert the provided manuscript or outline into a polished presentation deck.

OUTPUT: Return ONLY a valid JSON object — no markdown fences, no prose.

═══ QUOTE INTEGRITY (CRITICAL) ═══
• Quotes ("quote-green" / "quote-dark") are allowed ONLY on FINDINGS slides, where
  they reproduce MATERIAL/DATA evidence (verbatim participant quotes, dataset text,
  UI/ad copy) copied word-for-word.
• NEVER quote scholars' work. In Context / Method / Discussion / Conclusion do NOT
  use quote boxes at all — cite parenthetically in a bullet, e.g. (Surname Year).
• If words are yours (paraphrase/synthesis), they are NOT a quote. Putting non-verbatim
  text in quotation marks is academic misconduct. Use kind "note" (no quote marks)
  for a synthesised highlight, or omit evidence.
(The code also enforces this: any quote outside Findings is auto-converted to a note.)

═══ STYLE RULES ═══
• Slide title = CLAIM, never a label ("Trust complicates engagement" not "Trust")
• EVERY content slide must have bullet points (2–4) — never a title + a single claim alone
• One idea per slide; ≤ 3 top-level bullets (4 only if each is very short); ≤ 1 nesting level
• Keep bullets SHORT and scannable: aim ≤ 14 words, hard max 18; ≤ 40 words total body per slide
• Slides are signposts, not the paper — distil to the essential phrase, cut filler
• Bold key terms: **term**
• British spelling; hedged, precise academic tone
• Evidence is OPTIONAL — add one object only when it strengthens the claim; omit otherwise
• CONCLUSION: exactly ONE slide, "layout":"bullets", 3–4 short key takeaways,
  NO evidence. (Its title is set to "Conclusions" automatically.)

═══ SECTION ARC ═══
Create 4–6 short section labels (e.g. Context / Method / Findings / Discussion / Conclusion).
Use the IDENTICAL list on every slide — the code assigns breadcrumb highlights automatically.

═══ LAYOUT OPTIONS ═══
split      – text-left (bullets) + evidence-right (default for argument + quote)
iconrow    – 3 analytic columns with emoji icons (last = Negative/complicating case)
cards      – 2 side-by-side cards (e.g. Method | Participants)
matrix     – 2×2 grid for typologies or crossed dimensions
stepflow   – horizontal process stages
bullets    – simple list with optional evidence
boxes      – enumerated named themes
circle     – ring with a centre word + orbiting keywords (optional left bullets);
             body: {"center":"Attention","keywords":["Reach","Clicks","Purchases"],"bullets":[…]}

═══ JSON SCHEMA ═══
{
  "meta": {
    "title": "Presentation title — one line",
    "author": "Dr Full Name",
    "affiliation": "Institution, Country",
    "venue": "Conference Name Year, City, Country",
    "email": "email@domain.com"
  },
  "sections": ["Context", "Method", "Findings", "Discussion", "Conclusion"],
  "slides": [ <content-slide objects — NO title/closing, those are added automatically> ]
}

═══ SLIDE OBJECT (by layout) ═══

SPLIT / BULLETS
{ "section":"Context", "title":"Claim title", "layout":"split",
  "body": {
    "bullets": [
      {"text":"Point with **key term** (Surname Year)"},
      {"text":"Second concise point."}
    ],
    "evidence": {"kind":"note", "text":"Synthesised highlight (no quote marks)."}
  }
}
  evidence.kind options:
    "stats"       — 2-3 headline numbers stacked as big callouts (great for Method/Findings):
                    {"kind":"stats","items":[{"number":"77%","label":"from one firm"},{"number":"1641","label":"statements"}]}
    "stat"        — a single headline number + caption: {"kind":"stat","number":"77%","label":"…"}
    "quote-dark"  — VERBATIM data/material quote (Findings only); {"text":"…","source":"…"}
    "note"        — your own paraphrase or synthesis (NO quote marks); {"text":"…","label":"optional","source":"optional"}
    "figure"      — placeholder; add "alt":"description"
  Prefer "stats"/"stat" when striking numbers anchor the slide; "note" for a synthesised
  highlight. omit "evidence" entirely when nothing useful is available.

ICONROW  ("icon" = a semantic icon NAME from the list below, NOT an emoji)
{ "layout":"iconrow", "body": {
    "columns": [
      {"icon":"phone", "lead":"As a technology", "text":"Description.", "quote":"Name: 'verbatim'"},
      {"icon":"books", "lead":"As a text", "text":"..."},
      {"icon":"warning", "lead":"Negative cases", "text":"..."}
    ]
  }
}
  last column = Negative/complicating case; "quote" is optional

CARDS
{ "layout":"cards", "body": {
    "cards": [{"title":"Card A","text":"Body.","icon":"method"}, {"title":"Card B","text":"Body.","icon":"people"}]
  }
}
  OPTIONAL "icon" (on cards or matrix cells) — choose one name:
  people, person, chart, trend, idea, target, flag, shield, lock, method, money,
  cart, shop, globe, clock, search, link, share, doc, data, list, comment, books,
  sparkle, view, tag, question, computer, check, warning, info. Omit if unsure.

MATRIX
{ "layout":"matrix", "body": {
    "cells": [
      {"label":"Quadrant 1","text":"..."},{"label":"Quadrant 2","text":"..."},
      {"label":"Quadrant 3","text":"..."},{"label":"Quadrant 4","text":"..."}
    ]
  }
}

STEPFLOW
{ "layout":"stepflow", "body": {"steps":["Stage 1 desc.","Stage 2 desc.","Stage 3 desc."]} }

BOXES
{ "layout":"boxes", "body": {
    "bullets": [
      {"text":"**Theme name** (N): description."},
      {"text":"Second theme: description."}
    ]
  }
}

═══ ICON NAMES (for "icon" fields) ═══
people person settings method process globe check warning info doc data clipboard
search link star chart trend idea shop cart share phone clock lock card money
comment chat books sparkle list flag goal target shield security view tag question computer

═══ RICHNESS ═══
You receive the FULL manuscript. Mine it for CONCRETE specifics — exact figures,
named entities, dataset sizes, percentages, concrete examples — and put them on the
slides (they make the deck credible and vivid). Use "stats"/"stat" for striking
numbers; in Findings, support claims with a verbatim "quote-dark" or a synthesised
"note". Keep each bullet short but SPECIFIC (a named example beats a vague summary).

═══ DECK STRUCTURE ═══
Title and closing slides are generated automatically. Include ONLY content slides in "slides".
Typical deck: intro/context → RQ/objective → method → findings (2–4 slides) → discussion → conclusion.
Aim for 8–14 content slides for a 20-minute conference talk.
End with exactly ONE Conclusion slide: layout "bullets", 3–4 short takeaways, no evidence.

Return ONLY the JSON object."""


def generate_slide_json(
    content: str,
    config: dict,
    venue_override: Optional[str] = None,
) -> dict:
    defaults = config.get("defaults", {})

    hints: list[str] = []
    if venue_override:
        hints.append(f"Venue: {venue_override}")
    elif defaults.get("venue"):
        hints.append(f"Default venue if not in manuscript: {defaults['venue']}")
    if defaults.get("author"):
        hints.append(f"Default author if not in manuscript: {defaults['author']}")
    if defaults.get("affiliation"):
        hints.append(f"Default affiliation if not in manuscript: {defaults['affiliation']}")
    if defaults.get("email"):
        hints.append(f"Default email if not in manuscript: {defaults['email']}")

    hint_block = ("\n".join(hints) + "\n\n") if hints else ""
    word_count = len(content.split())
    is_manuscript = word_count > 1500

    task_line = (
        "Convert the following ACADEMIC MANUSCRIPT into a conference presentation "
        "slide deck. Distil the key arguments, claims, and evidence — do NOT try "
        "to cover everything. Select the most impactful 8–14 content slides."
        if is_manuscript
        else
        "Convert the following outline/notes into a conference presentation slide deck."
    )

    user_msg = (
        f"{hint_block}"
        f"{task_line}\n\n"
        f"---\n{content}\n---\n\n"
        f"Return ONLY the JSON object."
    )
    return _complete_json(config, user_msg)


def revise_slide_json(slide_data: dict, feedback: str, config: dict) -> dict:
    """Apply the presenter's natural-language feedback to an existing plan."""
    user_msg = (
        "Here is the current presentation slide deck as JSON:\n\n"
        f"{json.dumps(slide_data, ensure_ascii=False)}\n\n"
        "The presenter reviewed it and gave this feedback:\n"
        f"\"{feedback}\"\n\n"
        "Apply the feedback, leaving everything else unchanged. Obey all the rules "
        "above (schema, layouts, evidence kinds, British spelling, one Conclusion "
        "slide). Return ONLY the full updated JSON object."
    )
    return _complete_json(config, user_msg)


def _complete_json(config: dict, user_msg: str) -> dict:
    api_key = config.get("api", {}).get("anthropic_key", "")
    if not api_key or api_key.startswith("YOUR_"):
        raise ValueError(
            "Anthropic API key not set. "
            "Add it to config.local.yaml (api.anthropic_key) "
            "or set the ANTHROPIC_API_KEY environment variable."
        )
    model = config.get("llm", {}).get("model", "claude-haiku-4-5-20251001")
    max_tokens = config.get("llm", {}).get("max_tokens", 8192)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    usage = response.usage
    print(
        f"       Tokens — input: {usage.input_tokens:,}  output: {usage.output_tokens:,}  "
        f"(est. cost: ${_cost_usd(usage.input_tokens, usage.output_tokens, model):.4f})"
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"The model hit the {max_tokens:,}-token output limit and the slide "
            "JSON was truncated. Raise llm.max_tokens in config.local.yaml "
            "(try 8192+) or ask for fewer slides, then re-run."
        )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```\s*$", "", raw, flags=re.MULTILINE)

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model did not return valid JSON ({e}). "
            f"Last 200 chars received:\n...{raw.strip()[-200:]}"
        ) from e


def _cost_usd(input_tokens: int, output_tokens: int, model: str) -> float:
    rates = {
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "claude-haiku-4-5": (0.80, 4.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-opus-4-7": (15.00, 75.00),
    }
    in_rate, out_rate = rates.get(model, (0.80, 4.00))
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
