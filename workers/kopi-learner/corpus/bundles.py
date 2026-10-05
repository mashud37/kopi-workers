"""Mine existing kopi-editor output bundles, the primary training source,
aligning each `_original.md`/`_edited.md` pair by paragraph and
reconstructing the production prompt that produced each edit.
"""
import re

import editor
from cli import config, ui
from corpus import sample as corpus_sample
from distil import samples

# Mined edits were produced at an unknown intensity; guard them leniently so a
# legitimately firm Opus cut is not filtered as "over-compression": we still drop
# edits that broke meaning or dropped a citation/number (the cosine/citation checks).
_MINED_CEILING = 0.60
_MODELS_RE = re.compile(r"\*\*Models?:\*\*\s*([^\n·|]+?)\s+via\b", re.IGNORECASE)


def discover() -> list[dict]:
    """Every bundle with both an original and an edited file, tagged by model."""
    out_root = editor.output_dir()
    if not out_root.exists():
        raise SystemExit(f"kopi-editor output/ not found at {out_root}, nothing to mine.")
    found = []
    for orig in out_root.rglob("*_original.md"):
        stem = orig.name[: -len("_original.md")]
        edited = orig.with_name(f"{stem}_edited.md")
        if not edited.exists():
            continue
        # arch/<model>/<doc>_original.md -> the folder names the model
        rel = orig.resolve().relative_to(out_root.resolve())
        model = "unknown"
        if rel.parts and rel.parts[0].lower() == "arch" and len(rel.parts) >= 2:
            model = rel.parts[1]
        else:
            report = orig.with_name(f"{stem}_report.md")
            if report.exists():
                match = _MODELS_RE.search(report.read_text(encoding="utf-8", errors="ignore"))
                model = match.group(1).strip() if match else "unknown"
        # `doc` identifies the SOURCE document (the file stem), not the bundle/model
        # folder, so the same paragraph edited by Opus and by Qwen shares a key and
        # can be paired for DPO. `bundle` keeps the folder for logging only.
        found.append({
            "doc": stem,
            "bundle": orig.parent.name,
            "model": model,
            "role": samples.role_of(model),
            "original": orig,
            "edited": edited,
        })
    return found


def _samples_for_bundle(bundle: dict, min_words: int) -> list[dict]:
    original_text = bundle["original"].read_text(encoding="utf-8", errors="ignore")
    edited_text = bundle["edited"].read_text(encoding="utf-8", errors="ignore")
    orig_paras = original_text.split("\n\n")
    edit_paras = edited_text.split("\n\n")
    if len(orig_paras) != len(edit_paras):
        return []                                  # not paragraph-aligned; skip the bundle

    orig_words = len(original_text.split())
    reduction = max(0, orig_words - len(edited_text.split()))
    state = editor.prepare_doc(original_text, config.lang())
    cands = editor.candidates_at(state, reduction)

    out = []
    for c in cands:
        i = c["index"]
        if i >= len(edit_paras):
            continue
        original = c["text"]
        edit = edit_paras[i].strip()
        if not edit or not corpus_sample._is_prose(original, min_words):
            continue
        out.append(samples.make(
            {
                "source": "mined",
                "doc": bundle["doc"],
                "idx": i,
                "model": bundle["model"],
                "lang": config.lang(),
            },
            {
                "original": original,
                "instructions": c.get("instructions"),
                "mode": c["mode"],
                "floor": c.get("floor"),
                "max_compression": _MINED_CEILING,
            },
            edit))
    return out


def mine() -> list[dict]:
    """Mine all bundles into per-(paragraph, model) samples."""
    min_words = int(config.settings().get("corpus", {}).get("min_paragraph_words", 40))
    bundles = discover()
    if not bundles:
        raise SystemExit("no bundles with original+edited found in kopi-editor/output.")
    ui.step(f"mining {len(bundles)} bundles from kopi-editor/output")
    by_role: dict[str, int] = {}
    out = []
    for i, b in enumerate(bundles, 1):
        ui.info(f"[{i}/{len(bundles)}] {b['bundle'][:40]}/{b['doc'][:25]}  ({b['model']} -> {b['role']})")
        try:
            recs = _samples_for_bundle(b, min_words)
        except Exception as e:
            ui.warn(f"skipped {b['doc']}: {e}")
            continue
        out.extend(recs)
        by_role[b["role"]] = by_role.get(b["role"], 0) + len(recs)
    ui.ok(f"mined {len(out)} paragraph samples  ·  " + ", ".join(f"{k}={v}" for k, v in by_role.items()))
    return out
