"""Scoring. The model is a placeholder; the shape of the output is what
matters downstream, because a score plus a recommendation given to a human
decision maker is exactly the Annex III point 5 situation."""

from dataclasses import dataclass


@dataclass
class Application:
    applicant_id: str
    monthly_income: float
    existing_debt: float
    missed_payments_24m: int
    requested_amount: float


@dataclass
class Score:
    value: float          # 0.0 to 1.0, higher is lower risk
    recommendation: str   # approve, review, or decline
    factors: list[str]


def explain(score: "Score") -> str:
    """Plain-language reason codes for one score.

    The loan officer receiving the recommendation is told which inputs moved
    it and in which direction, so the operation of the system is intelligible
    to the person acting on its output rather than a bare number.

    @implements: norm:eu-ai-act:article-13:paragraph-1:n1
    @implements: norm:eu-ai-act:article-13:paragraph-1:n2
    """
    if not score.factors:
        return (
            f"Score {score.value:.2f} ({score.recommendation}). No adverse "
            "factor was found in the application data."
        )
    reasons = "; ".join(score.factors)
    return (
        f"Score {score.value:.2f} ({score.recommendation}). Factors that "
        f"lowered the score: {reasons}."
    )


def score_application(app: Application) -> Score:
    factors = []
    value = 0.75
    if app.monthly_income > 0:
        ratio = app.existing_debt / app.monthly_income
        if ratio > 6:
            value -= 0.25
            factors.append(f"debt to income ratio {ratio:.1f}")
    if app.missed_payments_24m:
        value -= 0.05 * app.missed_payments_24m
        factors.append(f"{app.missed_payments_24m} missed payments in 24 months")
    value = max(0.0, min(1.0, value))
    if value >= 0.7:
        recommendation = "approve"
    elif value >= 0.45:
        recommendation = "review"
    else:
        recommendation = "decline"
    return Score(value=value, recommendation=recommendation, factors=factors)
