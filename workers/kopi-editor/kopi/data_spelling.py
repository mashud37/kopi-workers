"""Map American to British spellings so `edit` can restore British English
after an LLM corrects it to American despite the prompt. Excludes ambiguous
pairs like program/programme and practice/practise.
"""

# -ize verbs that take British -ise. Each expands to its inflections + -isation.
_ISE_VERBS = [
    "organize",
    "recognize",
    "prioritize",
    "socialize",
    "individualize",
    "personalize",
    "emphasize",
    "categorize",
    "characterize",
    "summarize",
    "realize",
    "theorize",
    "conceptualize",
    "generalize",
    "minimize",
    "maximize",
    "normalize",
    "standardize",
    "criticize",
    "specialize",
    "materialize",
    "mobilize",
    "stabilize",
    "commercialize",
    "marginalize",
    "problematize",
    "contextualize",
    "legitimize",
    "optimize",
    "utilize",
    "memorize",
    "capitalize",
    "centralize",
    "colonize",
    "democratize",
    "destabilize",
    "internalize",
    "rationalize",
    "visualize",
    "homogenize",
    "synthesize",
    "polarize",
    "moralize",
    "hypothesize",
    "operationalize",
]

_ISE_FORMS = {
    "ize": "ise",
    "izes": "ises",
    "ized": "ised",
    "izing": "ising",
    "ization": "isation",
    "izations": "isations",
}

_YSE = {
    "analyze": "analyse",
    "analyzes": "analyses",
    "analyzed": "analysed",
    "analyzing": "analysing",
    "paralyze": "paralyse",
    "paralyzes": "paralyses",
    "paralyzed": "paralysed",
    "paralyzing": "paralysing",
    "catalyze": "catalyse",
    "catalyzes": "catalyses",
    "catalyzed": "catalysed",
    "catalyzing": "catalysing",
}

_OUR = {
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "behavioral": "behavioural",
    "color": "colour",
    "colors": "colours",
    "colored": "coloured",
    "coloring": "colouring",
    "colorful": "colourful",
    "favor": "favour",
    "favors": "favours",
    "favored": "favoured",
    "favoring": "favouring",
    "favorite": "favourite",
    "favorable": "favourable",
    "labor": "labour",
    "labors": "labours",
    "labored": "laboured",
    "honor": "honour",
    "honors": "honours",
    "honored": "honoured",
    "neighbor": "neighbour",
    "neighbors": "neighbours",
    "neighborhood": "neighbourhood",
    "flavor": "flavour",
    "flavors": "flavours",
    "humor": "humour",
    "rumor": "rumour",
    "rumors": "rumours",
}

_RE = {
    "center": "centre",
    "centers": "centres",
    "centered": "centred",
    "centering": "centring",
    "theater": "theatre",
    "theaters": "theatres",
    "meter": "metre",
    "meters": "metres",
    "fiber": "fibre",
    "fibers": "fibres",
    "caliber": "calibre",
}

_OTHER = {
    "defense": "defence",
    "offense": "offence",
    "catalog": "catalogue",
    "catalogs": "catalogues",
    "dialog": "dialogue",
    "dialogs": "dialogues",
    "modeling": "modelling",
    "modeled": "modelled",
    "labeling": "labelling",
    "labeled": "labelled",
    "traveling": "travelling",
    "traveled": "travelled",
}

AMERICAN_TO_BRITISH: dict = {}
for _v in _ISE_VERBS:
    _root = _v[:-3]  # drop "ize"
    for _am, _br in _ISE_FORMS.items():
        AMERICAN_TO_BRITISH[_root + _am] = _root + _br
AMERICAN_TO_BRITISH.update(_YSE)
AMERICAN_TO_BRITISH.update(_OUR)
AMERICAN_TO_BRITISH.update(_RE)
AMERICAN_TO_BRITISH.update(_OTHER)
