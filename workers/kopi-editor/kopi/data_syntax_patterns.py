import re

INTENSIFIER_LEMMAS = frozenset([
    "very", "really", "quite", "rather", "somewhat", "fairly",
    "highly", "largely", "extremely", "deeply", "particularly",
])

SKIP_AFTER_INTENSIFIER = frozenset(["than", "so", "enough", "when", "different"])

INTENSIFIER_DEP_PATTERN = [
    {"RIGHT_ID": "head", "RIGHT_ATTRS": {"POS": {"IN": ["ADJ", "ADV"]}}},
    {
        "LEFT_ID": "head",
        "REL_OP": ">",
        "RIGHT_ID": "adv",
        "RIGHT_ATTRS": {
            "DEP": "advmod",
            "LEMMA": {"IN": ["very", "really", "quite", "rather", "somewhat",
                             "fairly", "highly", "largely", "extremely",
                             "deeply", "particularly"]},
        },
    },
]

RELCL_PATTERN = re.compile(
    r"\b(a|an|the)\s+(\w+)\s+that\s+(?:is|are|was|were)\s+([a-z]+)\b",
    re.IGNORECASE,
)

DEMONSTRATIVE_GERUNDS = {
    "demonstrates": "demonstrating",
    "demonstrate": "demonstrating",
    "shows": "showing",
    "show": "showing",
    "suggests": "suggesting",
    "suggest": "suggesting",
    "means": "meaning",
    "mean": "meaning",
    "indicates": "indicating",
    "indicate": "indicating",
    "reveals": "revealing",
    "reveal": "revealing",
    "implies": "implying",
    "imply": "implying",
    "confirms": "confirming",
    "confirm": "confirming",
    "highlights": "highlighting",
    "highlight": "highlighting",
    "illustrates": "illustrating",
    "illustrate": "illustrating",
    "provides": "providing",
    "provide": "providing",
    "offers": "offering",
    "offer": "offering",
    "represents": "representing",
    "represent": "representing",
    "enables": "enabling",
    "enable": "enabling",
    "allows": "allowing",
    "allow": "allowing",
    "requires": "requiring",
    "require": "requiring",
    "involves": "involving",
    "involve": "involving",
}
