"""The set-up rule's closed table (spec G D-G80 (6), (7); DEC-27).

@implements: DEC-27
@grounded_by: REF-11

Outside Articles 8 to 15, a norm whose grammatical subject is a thing is the
duty of the party a sentence of the same Article makes set up, draw up,
produce or carry that thing. The extractor reads one source unit only
(pipeline.py, _generator_user_message), so the setting-up sentence of
another paragraph reaches it as a row of this table, rendered into
extract_norms v5; the judge of v5 receives the rows of the unit it judges.
Each row names the covered paragraph unit, the thing as the Act writes it
there (one or more wordings), the node that holds the setting-up sentence,
the party's value of schema/act_parties.json and the setting-up words,
verbatim in the Act's own characters (’ not '). NOT_COVERED lists the
cases the rule leaves alone, each with its reason. tests/unit/
test_set_up_rule.py checks every row against data/graph_dumps/layer1.json
and reruns the brief's widest sweep over the core.
"""

from __future__ import annotations

from dataclasses import dataclass

POINT_A_NODE = "eu-ai-act:article-16:paragraph-1:point-a"


@dataclass(frozen=True)
class SetUpRow:
    unit: str
    things: tuple[str, ...]
    source: str
    party: str
    setting_up: str


@dataclass(frozen=True)
class NotCovered:
    unit: str
    words: str
    reason: str


def _a(n: str, p: str) -> str:
    return f"eu-ai-act:article-{n}:paragraph-{p}"


ROWS: tuple[SetUpRow, ...] = (
    SetUpRow(_a("5", "5"), ("Those rules",), _a("5", "5"), "member_state",
             "Member States concerned shall lay down in their national law the necessary detailed rules"),
    SetUpRow(_a("5", "7"), ("Those annual reports",), _a("5", "7"), "commission",
             "The Commission shall publish annual reports"),
    SetUpRow(_a("17", "1"), ("That system",), _a("17", "1"), "provider",
             "Providers of high-risk AI systems shall put a quality management system in place"),
    SetUpRow(_a("17", "2"), ("The implementation of the aspects referred to in paragraph 1",), _a("17", "1"), "provider",
             "Providers of high-risk AI systems shall put a quality management system in place"),
    SetUpRow(_a("19", "1"), ("the logs",), _a("19", "1"), "provider",
             "Providers of high-risk AI systems shall keep the logs referred to in Article 12(1)"),
    SetUpRow(_a("22", "3"), ("the mandate",), _a("22", "1"), "provider",
             "providers established in third countries shall, by written mandate, appoint an authorised representative"),
    SetUpRow(_a("25", "2"), ("the obligation laid down in the second subparagraph",), _a("25", "2"), "provider",
             "That initial provider shall closely cooperate with new providers"),
    SetUpRow(_a("25", "4"), ("The voluntary model terms",), _a("25", "4"), "ai_office",
             "The AI Office may develop and recommend voluntary model terms"),
    SetUpRow(_a("26", "5"), ("This obligation",), _a("26", "5"), "deployer",
             "Where deployers have identified a serious incident, they shall also immediately inform first the provider"),
    SetUpRow(_a("26", "5"), ("the monitoring obligation set out in the first subparagraph",), _a("26", "5"), "deployer",
             "Deployers shall monitor the operation of the high-risk AI system"),
    SetUpRow(_a("26", "7"), ("This information",), _a("26", "7"), "deployer",
             "deployers who are employers shall inform workers’ representatives"),
    SetUpRow(_a("26", "10"), ("The reports",), _a("26", "10"), "deployer",
             "Deployers shall submit annual reports"),
    SetUpRow(_a("27", "5"), ("This template",), _a("27", "5"), "ai_office",
             "The AI Office shall develop a template for a questionnaire"),
    SetUpRow(_a("50", "1"), ("This obligation",), _a("50", "1"), "provider",
             "Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed"),
    SetUpRow(_a("50", "2"), ("This obligation",), _a("50", "2"), "provider",
             "Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video "
             "or text content, shall ensure that the outputs of the AI system are marked"),
    SetUpRow(_a("50", "3"), ("This obligation",), _a("50", "3"), "deployer",
             "Deployers of an emotion recognition system or a biometric categorisation system shall inform the natural persons exposed thereto"),
    SetUpRow(_a("50", "4"), ("This obligation",), _a("50", "4"), "deployer",
             "Deployers of an AI system that generates or manipulates image, audio or video content constituting a deep fake, shall disclose"),
    SetUpRow(_a("50", "5"), ("The information referred to in paragraphs 1 to 4", "The information"), _a("50", "1"), "provider",
             "Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed"),
    SetUpRow(_a("50", "5"), ("The information referred to in paragraphs 1 to 4", "The information"), _a("50", "3"), "deployer",
             "Deployers of an emotion recognition system or a biometric categorisation system shall inform the natural persons exposed thereto"),
    SetUpRow(_a("72", "2"), ("The post-market monitoring system", "post-market monitoring", "This obligation"), _a("72", "1"), "provider",
             "Providers shall establish and document a post-market monitoring system"),
    SetUpRow(_a("72", "3"), ("The post-market monitoring system", "The post-market monitoring plan"), _a("72", "1"), "provider",
             "Providers shall establish and document a post-market monitoring system"),
    SetUpRow(_a("73", "2"), ("The report referred to in paragraph 1", "The period for the reporting referred to in the first subparagraph"),
             _a("73", "1"), "provider", "Providers of high-risk AI systems placed on the Union market shall report any serious incident"),
    SetUpRow(_a("73", "3"), ("the report referred to in paragraph 1 of this Article",), _a("73", "1"), "provider",
             "Providers of high-risk AI systems placed on the Union market shall report any serious incident"),
    SetUpRow(_a("73", "4"), ("the report",), _a("73", "1"), "provider",
             "Providers of high-risk AI systems placed on the Union market shall report any serious incident"),
    SetUpRow(_a("73", "6"), ("This",), _a("73", "6"), "provider",
             "the provider shall, without delay, perform the necessary investigations"),
    SetUpRow(_a("73", "7"), ("That guidance",), _a("73", "7"), "commission",
             "The Commission shall develop dedicated guidance"),
    SetUpRow(_a("73", "9"), ("the notification of serious incidents",), _a("73", "1"), "provider",
             "Providers of high-risk AI systems placed on the Union market shall report any serious incident"),
    SetUpRow(_a("73", "10"), ("the notification of serious incidents",), _a("73", "1"), "provider",
             "Providers of high-risk AI systems placed on the Union market shall report any serious incident"),
    # Outside the core of B74 (data/graph_dumps/core_nodes.txt): kept so the
    # rule is the Act's, not the slice's; B74 does not extract them.
    SetUpRow(_a("46", "1"), ("That authorisation",), _a("46", "1"), "market_surveillance_authority",
             "any market surveillance authority may authorise"),
    SetUpRow(_a("46", "3"), ("The authorisation referred to in paragraph 1",), _a("46", "1"), "market_surveillance_authority",
             "any market surveillance authority may authorise"),
    SetUpRow(_a("47", "1"), ("The EU declaration of conformity", "A copy of the EU declaration of conformity"), _a("47", "1"), "provider",
             "The provider shall draw up a written machine readable, physical or electronically signed EU declaration of conformity"),
    SetUpRow(_a("47", "2"), ("The EU declaration of conformity",), _a("47", "1"), "provider",
             "The provider shall draw up a written machine readable, physical or electronically signed EU declaration of conformity"),
    SetUpRow(_a("47", "3"), ("a single EU declaration of conformity", "The declaration"), _a("47", "1"), "provider",
             "The provider shall draw up a written machine readable, physical or electronically signed EU declaration of conformity"),
    SetUpRow(_a("52", "1"), ("That notification",), _a("52", "1"), "provider",
             "the relevant provider shall notify the Commission"),
    SetUpRow(_a("52", "5"), ("Such a request",), _a("52", "5"), "provider",
             "Upon a reasoned request of a provider"),
    SetUpRow(_a("54", "3"), ("the mandate",), _a("54", "1"), "provider",
             "providers established in third countries shall, by written mandate, appoint an authorised representative"),
    SetUpRow(_a("54", "4"), ("The mandate",), _a("54", "1"), "provider",
             "providers established in third countries shall, by written mandate, appoint an authorised representative"),
    SetUpRow(_a("57", "1"), ("That sandbox",), _a("57", "1"), "national_competent_authority",
             "Member States shall ensure that their competent authorities establish at least one AI regulatory sandbox"),
    SetUpRow(_a("57", "3a"), ("That AI regulatory sandbox",), _a("57", "3a"), "ai_office",
             "The AI Office may establish an AI regulatory sandbox at Union level"),
    SetUpRow(_a("57", "5"), ("AI regulatory sandboxes established under this Article", "Such sandboxes"), _a("57", "1"),
             "national_competent_authority",
             "Member States shall ensure that their competent authorities establish at least one AI regulatory sandbox"),
    SetUpRow(_a("57", "5"), ("AI regulatory sandboxes established under this Article", "Such sandboxes"), _a("57", "3a"), "ai_office",
             "The AI Office may establish an AI regulatory sandbox at Union level"),
    SetUpRow(_a("57", "11"), ("The AI regulatory sandboxes",), _a("57", "1"), "national_competent_authority",
             "Member States shall ensure that their competent authorities establish at least one AI regulatory sandbox"),
    SetUpRow(_a("57", "11"), ("The AI regulatory sandboxes",), _a("57", "3a"), "ai_office",
             "The AI Office may establish an AI regulatory sandbox at Union level"),
    SetUpRow(_a("57", "13"), ("The AI regulatory sandboxes",), _a("57", "1"), "national_competent_authority",
             "Member States shall ensure that their competent authorities establish at least one AI regulatory sandbox"),
    SetUpRow(_a("57", "13"), ("The AI regulatory sandboxes",), _a("57", "3a"), "ai_office",
             "The AI Office may establish an AI regulatory sandbox at Union level"),
    SetUpRow(_a("57", "16"), ("Those reports",), _a("57", "16"), "national_competent_authority",
             "National competent authorities shall submit annual reports"),
    SetUpRow(_a("65", "5"), ("The rules of procedure",), _a("65", "5"), "member_state_representative",
             "The designated representatives of the Member States shall adopt the Board’s rules of procedure"),
    SetUpRow(_a("67", "10"), ("That report",), _a("67", "10"), "advisory_forum",
             "The advisory forum shall prepare an annual report"),
    SetUpRow(_a("71", "5"), ("The EU database",), _a("71", "1"), "commission",
             "The Commission shall, in collaboration with the Member States, set up and maintain an EU database"),
    SetUpRow(_a("71", "6"), ("The EU database",), _a("71", "1"), "commission",
             "The Commission shall, in collaboration with the Member States, set up and maintain an EU database"),
    SetUpRow(_a("96", "1"), ("The guidelines referred to in the first subparagraph",), _a("96", "1"), "commission",
             "The Commission shall develop guidelines"),
)

# The cases the rule leaves alone (D-G80 (6); brief R13, R39), each with its reason.
NOT_COVERED: tuple[NotCovered, ...] = (
    NotCovered(_a("5", "1"), "this prohibition", "the prohibition names no party"),
    NotCovered(_a("5", "2"), "the use", "the subject is an act, not a thing a party sets up"),
    NotCovered(_a("5", "3"), "the use", "the subject is an act, not a thing a party sets up"),
    NotCovered(_a("5", "3"), "that authority", "the subject is a party named before, not a thing: the extractor writes the party it stands for"),
    NotCovered(_a("5", "4"), "The notification", "the setting-up sentence names no party (each use shall be notified)"),
    NotCovered(_a("6", "1"), "that AI system", "the subject is the AI system, which no sentence of the Article makes a party set up"),
    NotCovered(_a("24", "2"), "that a high-risk AI system", "a that-clause, not a subject: the sentence's subject is the distributor"),
    NotCovered("eu-ai-act:article-61:paragraph-2", "the consent", "the setting-up sentence names no party (consent obtained in the passive, Article 61(1))"),
    NotCovered(_a("22", "3") + ":point-a", "verify", "a point of Article 22(3), whose actions the paragraph's first sentence gives to the authorised representative"),
    NotCovered(_a("17", "1") + ":point-a", "a strategy for regulatory compliance", "a point of Article 17(1), a bare noun with no norm of its own"),
)

# A subject that is a provision of the Act is an application clause, never a
# thing a party sets up (brief R39): Article 5(8) "This Article", Article
# 6(3) "The first subparagraph", Article 72(4) "The first subparagraph of
# this paragraph".
PROVISION_SUBJECT = r"^(?:this|that|the(?: first| second| third)?)\s+(?:article|paragraph|subparagraph|chapter|section|regulation)\b"


def rows_for(unit: str) -> tuple[SetUpRow, ...]:
    """The rows of one covered unit, in table order."""
    return tuple(row for row in ROWS if row.unit == unit)


def render_rows(rows: tuple[SetUpRow, ...] = ROWS) -> str:
    """The table as prompt v5 and guideline v4 print it, one line per row."""
    lines = []
    for row in rows:
        things = "; ".join(f"“{t}”" for t in row.things)
        lines.append(f"- {row.unit}: {things} is {row.party}'s; source {row.source}: “{row.setting_up}”")
    return "\n".join(lines)


def rows_in(core_nodes: list[str]) -> tuple[SetUpRow, ...]:
    """The rows of the units under the given core node ids (extract_norms v5
    prints the rows of the core of B74, data/graph_dumps/core_nodes.txt)."""
    return tuple(row for row in ROWS if any(row.unit.startswith(node + ":") for node in core_nodes))
