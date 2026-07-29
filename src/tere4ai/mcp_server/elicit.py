"""Elicitation envelope wrapper for the demo facade.

@implements: DEC-13
Engineering MUST (architecture.md Section 13, no silent degradation).
The elicitor proposes schema-valid facts with textual support; it never
classifies. This wrapper packages the proposal as a Section 8 envelope
whose status is requires_human_review by construction: elicited facts
are proposals until a human confirms or edits them, and only the
deterministic ladder ever assigns a risk category.
"""

from typing import Any

from tere4ai.elicit_features.elicitor import elicit_features, schema_flag_names
from tere4ai.mcp_server.tools import make_envelope

ELICITATION_JUDGE_VERDICT = "not_judged_elicitation_proposal"


def elicit_envelope(
    description: str,
    generator: Any,
    *,
    graph_version: str,
    prompt_version: str = "v4",
) -> dict[str, Any]:
    """One paid generator call; returns a facts PROPOSAL envelope."""
    features, notes = elicit_features(
        description, generator, prompt_version=prompt_version
    )
    if features is None:
        return make_envelope(
            answer=None,
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            legal_status_notes=notes,
            missing_facts=["elicitation failed; fill the facts manually"],
            judge_verdict=ELICITATION_JUDGE_VERDICT,
        )
    elicited = set((features.get("flags") or {}).keys())
    missing = [
        f"flag not elicited: {name}"
        for name in schema_flag_names()
        if name not in elicited
    ]
    return make_envelope(
        answer={"features": features, "notes": notes},
        status="requires_human_review",
        graph_version=graph_version,
        confidence=0.5,
        legal_status_notes=[
            "elicited facts are proposals; confirm or edit them before "
            "classification, the deterministic ladder alone decides"
        ],
        missing_facts=missing,
        judge_verdict=ELICITATION_JUDGE_VERDICT,
    )
