"""The loan officer stays the decision maker. The service recommends; a human
approves, declines, or overrides, and the override is captured rather than
silently discarded."""

from dataclasses import dataclass

from .audit_log import AuditLog
from .scoring import Application, Score, score_application


@dataclass
class Decision:
    applicant_id: str
    officer_id: str
    outcome: str          # approve or decline
    followed_recommendation: bool
    override_reason: str = ""
    note: str = ""


def decide(
    app: Application,
    officer_id: str,
    outcome: str,
    note: str = "",
    override_reason: str = "",
    log: AuditLog | None = None,
) -> Decision:
    """Record a loan officer's decision over the recommendation.

    The officer can depart from the recommendation, and a departure asks for a
    reason, so that the human stays able to disregard, override, or reverse the
    output of the system rather than being carried along by it.

    @implements: norm:eu-ai-act:article-14:paragraph-4:n1
    @implements: norm:eu-ai-act:article-14:paragraph-4:n2
    """
    scored: Score = score_application(app)
    followed = outcome == scored.recommendation
    if not followed and not override_reason:
        raise ValueError(
            "an outcome that departs from the recommendation needs an "
            "override_reason, so the departure is recorded and reviewable"
        )
    decision = Decision(
        applicant_id=app.applicant_id,
        officer_id=officer_id,
        outcome=outcome,
        followed_recommendation=followed,
        override_reason=override_reason,
        note=note,
    )
    if log is not None:
        log.record("decision", decision.__dict__)
        log.record_verifier(app.applicant_id, officer_id)
    return decision
