"""Chat entry point.

The model call is stubbed. What matters here is the shape of the exchange: a
visitor sends a message, the assistant answers, and the answer carries the
disclosure and the marking the Article 50 duties ask for.
"""

from dataclasses import dataclass, field

DISCLOSURE = (
    "You are chatting with an automated assistant. Ask for a colleague at any "
    "time and we will connect you to a person."
)


@dataclass
class Reply:
    text: str
    escalate: bool = False
    # Machine-readable marking travelling with every generated answer, so a
    # downstream consumer can detect that the content was produced by an AI
    # system rather than typed by a human agent.
    # @implements: norm:eu-ai-act:article-50:paragraph-2:n1
    marking: dict = field(default_factory=lambda: {"generated_by": "ai_system"})


def _model_answer(question: str, context: dict) -> str:
    """Stubbed generation. A real deployment calls an LLM here."""
    if "order" in question.lower():
        return f"Your order {context.get('order_id', 'unknown')} is on its way."
    if "return" in question.lower():
        return "You can return any item within 30 days of delivery."
    return "I can help with orders, returns, and product questions."


def _with_disclosure(text: str, context: dict) -> str:
    """Put the disclosure in front of the answer at the first interaction.

    The information is given at the point the visitor first meets the system,
    in plain language, in the reply itself rather than a footer they may never
    reach.

    @implements: norm:eu-ai-act:article-50:paragraph-5:n1
    @implements: norm:eu-ai-act:article-50:paragraph-1:n1
    """
    if context.get("turn_index", 0) == 0:
        return f"{DISCLOSURE}\n\n{text}"
    return text


def answer(question: str, context: dict | None = None) -> Reply:
    context = context or {}
    if "human" in question.lower() or "agent" in question.lower():
        return Reply(
            _with_disclosure("Connecting you to a colleague now.", context),
            escalate=True,
        )
    return Reply(_with_disclosure(_model_answer(question, context), context))
