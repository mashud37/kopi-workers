"""The negative and positive cases every method must face.

These are ``docs/good.md`` section 3 as data. Each one is a real failure observed
in this repo or a near neighbour of one, and the point of holding them here
rather than in a test file is that they run against *every* candidate method for
a family, not just the one that happens to be registered.

A case that no method has ever failed is worth keeping. A criterion is only
useful if some input violates it, so cases stay after the defect they describe is
fixed, to prove the fix is still in force.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    """One expectation about a method's behaviour on one input.

    Attributes:
        text: the input sentence or paragraph.
        family: which family's methods this case applies to.
        expect: ``refuse`` (propose nothing), ``fire`` (propose something), or
            ``unchanged`` (a repair pass must be a no-op).
        why: what breaks when the expectation fails, in one line.
        observed: True when this case was taken from an actual failure rather
            than constructed, which makes it the higher-value kind.
        span: the exact text the case is about. For ``fire``, the text that must
            go; for ``refuse``, the text that must survive. Without it a case
            asks only whether the method did *anything*, which for a family that
            offers several candidates per paragraph is barely a test, and which
            fails a refuse case for editing some other phrase correctly.

    A case has to be the size of the thing it tests. The first version of the
    adjunct cases was one sentence each, and every ``fire`` case failed: at the
    firm band a 13-word sentence may lose about 4 words, so an 8-word phrase
    could never fit the budget whatever the rule decided. That measured the
    band's ceiling, not the licence.
    """
    text: str
    family: str
    expect: str
    why: str
    observed: bool = False
    span: str = ""


RELATIVE = (
    Case(
        "It is exactly these kinds of reactions and ways of dealing with "
        "manifestations of algorithmic power that are key to my thesis.",
        "relative-clause", "refuse",
        "it-cleft: 'that are' is the cleft pivot, deleting it leaves no predicate",
        observed=True,
    ),
    Case(
        "It is within this domain of human practice that the social qualities "
        "of social media have always emerged.",
        "relative-clause", "refuse",
        "it-cleft with a verbal remainder",
        observed=True,
    ),
    Case(
        "This is a resource that can be creatively utilised by scholars.",
        "relative-clause", "refuse",
        "deleting the span destroys the modal 'can'",
        observed=True,
    ),
    Case(
        "These are practices that are increasingly personalised by the platform.",
        "relative-clause", "refuse",
        "deleting the span destroys the adverb and with it a claim",
        observed=True,
    ),
    Case(
        "The theory that is central has been widely discussed.",
        "relative-clause", "refuse",
        "bare predicate adjective cannot follow its noun",
    ),
    Case(
        "The data which we collected over several months were then coded.",
        "relative-clause", "refuse",
        "object relativiser: deleting it strands the verb",
    ),
    Case(
        "The claim, which is false, was repeated by several authors.",
        "relative-clause", "refuse",
        "non-restrictive: reduction changes the clause's relation to the head",
    ),
    Case(
        "The data which were collected over several months were then coded.",
        "relative-clause", "fire",
        "canonical past-participle reduction",
    ),
    Case(
        "Researchers who are studying algorithms often begin with metaphors.",
        "relative-clause", "fire",
        "canonical present-participle reduction",
    ),
    Case(
        "The book which is on the table belongs to the department.",
        "relative-clause", "fire",
        "prepositional predicate reduction",
    ),
    Case(
        "Students who are eager to learn tend to ask more questions.",
        "relative-clause", "fire",
        "adjective with a complement reduces safely",
    ),
)

REALISATION = (
    Case(
        "It focuses, for instance, on topics like U.S. politics and media studies.",
        "realisation", "unchanged",
        "initialism, not a sentence end",
        observed=True,
    ),
    Case(
        "She said it was “less surprising ... but still weird” afterwards.",
        "realisation", "unchanged",
        "ellipsis inside a quotation, not a sentence end",
        observed=True,
    ),
    Case(
        "The point is made by cf. boyd, 2010 and taken up later.",
        "realisation", "unchanged",
        "abbreviation, and the cited name is genuinely lower case",
        observed=True,
    ),
    Case(
        "As Chen et al. 2020 argue, the platform shapes what people see.",
        "realisation", "unchanged",
        "'al.' is an abbreviation",
    ),
    Case(
        "Participants described it as “just random people who i don't care about”.",
        "realisation", "unchanged",
        "quoted material is evidence and must pass through verbatim",
    ),
    Case(
        "The study used an spaCy pipeline for parsing.",
        "realisation", "fire",
        "article disagrees with the following word and must be repaired",
    ),
)

ADJUNCT = (
    Case(
        "The sample consisted of three interviews with early-career researchers. Each "
        "conversation lasted about an hour and was recorded with the participant's consent. "
        "Transcripts were coded descriptively before any thematic work began, and the "
        "resulting code groups were reviewed twice.",
        "adjunct", "refuse",
        "'of three interviews' is the argument of 'consisted', not an adjunct",
        span="of three interviews",
    ),
    Case(
        "The study focuses on youth political communication and activism. Earlier work in "
        "this area has tended to treat platforms as neutral channels rather than as active "
        "participants. That assumption is what this chapter sets out to question.",
        "adjunct", "refuse",
        "'on youth political communication' is the argument of 'focuses'",
        span="on youth political communication and activism",
    ),
    Case(
        "Whether people keep scrolling depends on the recommendation system. Participants "
        "described the feed as something that pulled them along rather than something they "
        "chose. The design of that system is therefore central to any account of their "
        "experience.",
        "adjunct", "refuse",
        "'on the recommendation system' is the argument of 'depends'",
        span="on the recommendation system",
    ),
    Case(
        "This chapter draws on the perspective of other work in the field. It treats the "
        "platform as an object of everyday practice rather than as a technical artefact. "
        "The distinction matters for how the analysis proceeds.",
        "adjunct", "refuse",
        "'on the perspective' is the argument of 'draws'",
        span="on the perspective",
    ),
    Case(
        "Participants were given an alias in the form of a randomly chosen name. "
        "Interviewees who referred to other people by name had those names transcribed "
        "generically, as brother, mother, or roommate. Locations were described in broad "
        "geographic terms.",
        "adjunct", "fire",
        "'in the form of a randomly chosen name' is a droppable adjunct",
        span="in the form of a randomly chosen name",
    ),
    Case(
        "Notes were compiled into a spreadsheet after each session. In this spreadsheet, "
        "each topic received its own row, while the notes were placed in separate columns "
        "for each participant. This summary sheet gave a first overview of the data.",
        "adjunct", "fire",
        "sentence-initial locative adjunct, droppable with its comma",
        span="In this spreadsheet",
    ),
    Case(
        "Notes were taken by the researcher during the interview sessions. They recorded "
        "what was said about each of the main topics covered, and were written up the same "
        "evening while the conversation was still fresh.",
        "adjunct", "fire",
        "temporal adjunct, droppable",
        span="during the interview sessions",
    ),
)

ALL = RELATIVE + REALISATION + ADJUNCT


def for_family(family: str) -> tuple:
    return tuple(case for case in ALL if case.family == family)
