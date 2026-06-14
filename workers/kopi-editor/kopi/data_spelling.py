"""American → British spelling map, for normalising LLM output to British English.

Small local models often 'correct' British spelling to American even when the
prompt forbids it; this deterministic pass restores the British forms after
editing. Curated to avoid false positives: `size`/`seize`/`prize` are not `-ise`
verbs, and genuinely ambiguous pairs (program/programme, practice/practise,
license/licence) are deliberately excluded.
"""

# -ize verbs that take British -ise. Each expands to its inflections + -isation.
_ISE_VERBS = [
    "organize", "recognize", "prioritize", "socialize", "individualize",
    "personalize", "emphasize", "categorize", "characterize", "summarize",
    "realize", "theorize", "conceptualize", "generalize", "minimize", "maximize",
    "normalize", "standardize", "criticize", "specialize", "materialize",
    "mobilize", "stabilize", "commercialize", "marginalize", "problematize",
    "contextualize", "legitimize", "optimize", "utilize", "memorize",
    "capitalize", "centralize", "colonize", "democratize", "destabilize",
    "internalize", "rationalize", "visualize", "homogenize", "synthesize",
    "polarize", "moralize", "hypothesize", "operationalize",
]


def _ise_pairs(verb: str) -> dict:
    root = verb[:-3]  # drop "ize"
    forms = {"ize": "ise", "izes": "ises", "ized": "ised",
             "izing": "ising", "ization": "isation", "izations": "isations"}
    return {root + am: root + br for am, br in forms.items()}


_YSE = {
    "analyze": "analyse", "analyzes": "analyses", "analyzed": "analysed", "analyzing": "analysing",
    "paralyze": "paralyse", "paralyzes": "paralyses", "paralyzed": "paralysed", "paralyzing": "paralysing",
    "catalyze": "catalyse", "catalyzes": "catalyses", "catalyzed": "catalysed", "catalyzing": "catalysing",
}

_OUR = {
    "behavior": "behaviour", "behaviors": "behaviours", "behavioral": "behavioural",
    "color": "colour", "colors": "colours", "colored": "coloured", "coloring": "colouring", "colorful": "colourful",
    "favor": "favour", "favors": "favours", "favored": "favoured", "favoring": "favouring",
    "favorite": "favourite", "favorable": "favourable",
    "labor": "labour", "labors": "labours", "labored": "laboured",
    "honor": "honour", "honors": "honours", "honored": "honoured",
    "neighbor": "neighbour", "neighbors": "neighbours", "neighborhood": "neighbourhood",
    "flavor": "flavour", "flavors": "flavours",
    "humor": "humour", "rumor": "rumour", "rumors": "rumours",
}

_RE = {
    "center": "centre", "centers": "centres", "centered": "centred", "centering": "centring",
    "theater": "theatre", "theaters": "theatres",
    "meter": "metre", "meters": "metres",
    "fiber": "fibre", "fibers": "fibres", "caliber": "calibre",
}

_OTHER = {
    "defense": "defence", "offense": "offence",
    "catalog": "catalogue", "catalogs": "catalogues", "dialog": "dialogue", "dialogs": "dialogues",
    "modeling": "modelling", "modeled": "modelled",
    "labeling": "labelling", "labeled": "labelled",
    "traveling": "travelling", "traveled": "travelled",
}

AMERICAN_TO_BRITISH: dict = {}
for _v in _ISE_VERBS:
    AMERICAN_TO_BRITISH.update(_ise_pairs(_v))
AMERICAN_TO_BRITISH.update(_YSE)
AMERICAN_TO_BRITISH.update(_OUR)
AMERICAN_TO_BRITISH.update(_RE)
AMERICAN_TO_BRITISH.update(_OTHER)
