"""Hold positive and negative test cases (`docs/good.md` section 3) that
every candidate method for a family runs against, not just the registered
one. Cases stay after their defect is fixed.
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
        survives: text that must **not** be inside the deleted span, on a case
            that is otherwise expected to fire. ``span`` alone cannot express
            this, because it matches by containment: a case asking for "that
            are" to go is passed by a rule that deletes "that are increasingly"
            and eats the adverb with it. Section 3.4 of ``good.md`` calls that
            the single defect class behind most of the negative cases, so it
            needs to be assertable rather than argued about in a docstring.

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
    survives: str = ""


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
        "relative-clause", "fire",
        "the adverb must survive the reduction, not block it: 'that are' goes and "
        "'increasingly personalised' stays",
        observed=True,
        span="that are",
        survives="increasingly",
    ),
    Case(
        "She described a conversation that has recently shaped a relationship "
        "with her sister over the last year.",
        "relative-clause", "refuse",
        "active perfect, not a passive: the auxiliary chain ends in 'have', and "
        "reducing it yields 'a conversation recently shaped a relationship', a "
        "main clause asserting something nobody claimed",
        span="that has",
    ),
    Case(
        "This study followed participants who had been using TikTok since "
        "early 2019 and throughout the pandemic.",
        "relative-clause", "fire",
        "perfect passive: the whole auxiliary chain goes because it ends in "
        "'be', which the older span test refused for containing 'had'",
        span="who had been",
        survives="using",
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

# Adjunct cases run at corpus paragraph length, around 110 words, and that is a
# requirement rather than a stylistic choice. A ranked family spends a word
# budget set from the band, so at the firm band a 38-word case can lose only five
# words: every `fire` case failed because its target phrase did not fit, and
# every `refuse` case passed because the protected phrase was never reachable.
# Both readings were artefacts of case length. A case has to be big enough that
# the method genuinely *could* make the mistake it is being tested for.
ADJUNCT = (
    Case(
        "The sample consisted of three interviews with early-career researchers working "
        "across two departments. Each conversation lasted about an hour and was recorded "
        "with the participant's consent, then transcribed in full before any coding began. "
        "Recruitment ran through departmental mailing lists and word of mouth, which "
        "produced a group that was more junior than the department as a whole. Transcripts "
        "were coded descriptively in a first pass, and the resulting code groups were "
        "reviewed twice before the thematic work started. Where a participant referred to "
        "a colleague by name, the name was replaced with a generic description at the point "
        "of transcription rather than afterwards.",
        "adjunct", "refuse",
        "'of three interviews' is the argument of 'consisted', not an adjunct",
        span="of three interviews",
    ),
    Case(
        "The study focuses on youth political communication and activism. Earlier work in "
        "this area has tended to treat platforms as neutral channels through which messages "
        "pass, rather than as active participants in how those messages are shaped. That "
        "assumption is what this chapter sets out to question, drawing on material gathered "
        "over eighteen months of fieldwork. The argument is not that platforms determine "
        "what young people say, which would replace one kind of determinism with another, "
        "but that the shape of a feed makes some kinds of speech easier than others. "
        "Establishing that requires attention to the ordinary texture of use rather than to "
        "moments of obvious controversy.",
        "adjunct", "refuse",
        "'on youth political communication' is the argument of 'focuses'",
        span="on youth political communication and activism",
    ),
    Case(
        "Whether people keep scrolling depends on the recommendation system. Participants "
        "described the feed as something that pulled them along rather than something they "
        "chose, and several returned to that image without prompting in later sessions. "
        "The design of that system is therefore central to any account of their experience, "
        "even though none of them could describe how it worked in any detail. What they "
        "could describe, often precisely, was how it felt to be caught by it late at night "
        "when they had meant to stop an hour earlier. That gap between mechanism and "
        "experience is where this chapter locates its argument.",
        "adjunct", "refuse",
        "'on the recommendation system' is the argument of 'depends'",
        span="on the recommendation system",
    ),
    Case(
        "This chapter draws on the perspective of other work in the field. It treats the "
        "platform as an object of everyday practice rather than as a technical artefact "
        "with properties that can be read off its architecture. The distinction matters for "
        "how the analysis proceeds, because it decides what counts as evidence: an "
        "interface feature is interesting here only insofar as somebody noticed it and did "
        "something with it. That commitment has costs, and the most obvious is that it "
        "leaves the infrastructure itself largely undescribed. Other work has taken the "
        "opposite route and described the infrastructure carefully while saying little "
        "about how it is lived with.",
        "adjunct", "refuse",
        "'on the perspective' is the argument of 'draws'",
        span="on the perspective",
    ),
    Case(
        "Data anonymisation proceeded in several steps. Participants were given an alias in "
        "the form of a randomly chosen name, and that alias was used consistently across "
        "field notes, transcripts and the final write-up. Interviewees who referred to "
        "other people by name had those names transcribed generically, as brother, mother "
        "or roommate, at the point of transcription. Locations were described in broad "
        "geographic terms, particularly where a participant lived outside the city in which "
        "the fieldwork was based. Care was taken not to name the universities participants "
        "studied at, or their places of work, since either would narrow the field of "
        "possible identities considerably.",
        "adjunct", "fire",
        "'in the form of a randomly chosen name' is a droppable adjunct",
        span="in the form of a randomly chosen name",
    ),
    Case(
        "Notes were compiled into a spreadsheet after each session, usually the same "
        "evening while the conversation was still fresh. In this spreadsheet, each topic "
        "received its own row, while the notes were placed in separate columns for each "
        "participant. This summary sheet gave a first overview of the data and made it "
        "possible to see which topics had been covered thinly and which had been returned "
        "to repeatedly without prompting. It also made the gaps visible early enough to "
        "adjust the remaining sessions, which mattered more than the tidiness of the "
        "record itself.",
        "adjunct", "fire",
        "sentence-initial locative adjunct, droppable with its comma",
        span="In this spreadsheet",
    ),
    Case(
        "Notes were taken by the researcher during the interview sessions. They recorded "
        "what was said about each of the main topics covered, and were written up the same "
        "evening while the conversation was still fresh in mind. These notes were not "
        "verbatim and were never treated as a substitute for the transcript, but they "
        "carried something the transcript did not: a sense of which answers had come "
        "easily and which had taken effort to reach. That distinction shaped which passages "
        "were returned to during coding, and it is the kind of judgement that is difficult "
        "to reconstruct after the fact.",
        "adjunct", "fire",
        "temporal adjunct, droppable",
        span="during the interview sessions",
    ),
)

TAGGED = (
    Case(
        "As Lull (1990: 41) has theorised for the case of television, media technologies "
        "provide people with a variety of opportunities to fulfil certain social roles "
        "and ideals.",
        "tagged", "refuse",
        "deletes the sentence's only predicate, leaving 'media technologies people with'",
        observed=True,
        span="provide",
    ),
    Case(
        "As Lull (1990: 41) has theorised for the case of television, media technologies "
        "provide people with a variety of opportunities to fulfil certain social roles "
        "and ideals.",
        "tagged", "refuse",
        "takes the last complement of 'of' and leaves the preposition dangling",
        observed=True,
        span="opportunities",
    ),
    Case(
        "Sunder, for example, told me the following in relation to speaking about TikTok "
        "with his parents.",
        "tagged", "refuse",
        "leaves 'in relation to' with nothing to govern",
        observed=True,
        span="speaking",
    ),
    Case(
        "Sunder, for example, told me the following in relation to speaking about TikTok "
        "with his parents.",
        "tagged", "refuse",
        "takes the noun and strands its determiner: 'told me the in relation to'",
        observed=True,
        span="following",
    ),
    Case(
        "Furthermore, the participants in this study were recruited through a single "
        "online community.",
        "tagged", "fire",
        "a sentence-initial connective is the family's clearest deletion, and without a "
        "fire case a rule that proposes nothing passes every case above",
        span="Furthermore",
    ),
    Case(
        "Gretta's description nicely illustrates something that I noticed with all my "
        "participants.",
        "tagged", "fire",
        "the run is 'nicely illustrates' and only the root is unsafe, so refusing the "
        "whole run throws away a deletion nothing objected to",
        observed=True,
        span="nicely",
        survives="illustrates",
    ),
    Case(
        "TikTok sharing practices might be enabling of social interaction.",
        "tagged", "refuse",
        "trimming the root out of 'be enabling' leaves the auxiliary of a verb that "
        "stayed: 'might enabling'",
        observed=True,
        span="be",
    ),
    Case(
        "Sharing this content provided opportunities to articulate relationships.",
        "tagged", "refuse",
        "takes the object of a verb that stayed: 'provided to articulate'",
        observed=True,
        span="opportunities",
    ),
    Case(
        "In the next section, I reflect on these conditions alongside a number of "
        "cases from the literature that demonstrate how TikTok's content "
        "recommendation system turns the app into an exclusionary online space.",
        "tagged", "refuse",
        "takes a relative clause's verb and leaves its subject: 'cases from the "
        "literature that how'",
        observed=True,
        span="demonstrate",
    ),
    Case(
        "Put differently, there are many forms of activity that people practice in "
        "their everyday lives, and in relation to TikTok.",
        "tagged", "refuse",
        "trimming the root out of 'there are' deletes the subject of a verb that "
        "stayed, leaving no subject at all",
        observed=True,
        span="there",
    ),
)

ALL = RELATIVE + REALISATION + ADJUNCT + TAGGED


def for_family(family: str) -> tuple:
    return tuple(case for case in ALL if case.family == family)
