"""Escalation to a human agent. Available on request and whenever the
assistant is unsure, which is a fact the classification relies on."""

from dataclasses import dataclass


@dataclass
class Handoff:
    conversation_id: str
    reason: str


def escalate(conversation_id: str, reason: str = "requested by visitor") -> Handoff:
    return Handoff(conversation_id=conversation_id, reason=reason)
