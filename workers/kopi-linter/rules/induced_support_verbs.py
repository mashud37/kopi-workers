"""Support-verb collapse rates induced from the train split of the gold corpus.
Regenerate with ``python manage.py induce``; never edit this file by hand.
"""

# Each entry is `"<light verb> <noun lemma>": (collapse rate, times seen)`, the
# rate being the share of occurrences whose noun did not survive into the gold
# edit. It is used directly as the rule's confidence, so a construction the gold
# editor usually leaves alone cannot clear a band threshold, and a construction
# absent from the table has no evidence behind it and is refused.
#
# The rate is an upper bound: a noun also disappears when the editor rewrote or
# dropped the whole sentence for unrelated reasons.

COLLAPSE_RATE = {
    "conduct fieldwork": (0.00, 5),
    "conduct interview": (0.00, 5),
    "do esport": (0.00, 10),
    "do research": (0.00, 7),
    "do thing": (0.00, 6),
    "give rise": (0.55, 11),
    "have access": (0.29, 7),
    "have accuracy": (0.25, 4),
    "have awareness": (0.42, 12),
    "have consequence": (0.50, 4),
    "have effect": (0.30, 10),
    "have experience": (0.00, 9),
    "have friend": (0.00, 4),
    "have function": (0.33, 6),
    "have impact": (0.50, 10),
    "have implication": (0.00, 4),
    "have interest": (0.17, 6),
    "have laugh": (0.00, 4),
    "have obligation": (0.17, 6),
    "have time": (0.00, 4),
    "have user": (0.00, 4),
    "make argument": (0.17, 6),
    "make decision": (0.40, 10),
    "make meaning": (0.00, 4),
    "make observation": (0.56, 9),
    "make sense": (0.09, 55),
    "make use": (0.00, 7),
    "offer perspective": (0.00, 4),
    "provide analysis": (0.40, 5),
    "provide answer": (0.17, 6),
    "provide description": (0.83, 6),
    "provide evidence": (0.17, 6),
    "provide insight": (0.33, 6),
    "provide opportunity": (0.89, 9),
    "provide overview": (0.29, 7),
    "provide people": (0.00, 11),
    "provide perspective": (0.60, 5),
    "take approach": (0.25, 4),
    "take break": (0.00, 8),
    "take control": (0.00, 4),
    "take form": (0.00, 5),
    "take place": (0.42, 31),
    "take shape": (0.25, 20),
}
