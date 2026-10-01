"""Elicitation envelope wrapper for the facade and the MCP tool.

@implements: DEC-13, DEC-18
Engineering MUST (architecture.md Section 13, no silent degradation).
The elicitor proposes schema-valid facts with textual support; it never
classifies. This wrapper packages the proposal as a Section 8 envelope
whose status is requires_human_review by construction: elicited facts
are proposals until a human confirms or edits them, and only the
deterministic ladder ever assigns a risk category.

B10: the call is made over the served build's dump and snapshots, so the
Act's provisions in the prompt are that build's text, and the answer
carries the quote of the description behind each kept fact, the facts
dropped for want of one, and the prompt record.
"""

from pathlib import Path
from typing import Any

from tere4ai.elicit_features.elicitor import (
    DEFAULT_PROMPT_VERSION,
    elicit,
    schema_flag_names,
)
from tere4ai.mcp_server.tools import make_envelope

ELICITATION_JUDGE_VERDICT = "not_judged_elicitation_proposal"

# The shortest description the elicitor accepts, in characters: the
# facade's ElicitRequest and the MCP tool both read this one value.
MIN_DESCRIPTION_CHARS = 30

PROPOSAL_NOTE = (
    "elicited facts are proposals; confirm or edit them before "
    "classification, the deterministic ladder alone decides"
)
QUOTE_NOTE = (
    "each proposed fact carries words of the description; code checked that "
    "the words are there, a person judges whether they support the fact"
)


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def elicit_envelope(
    description: str,
    generator: Any,
    *,
    dump: dict[str, Any],
    snapshots_dir: Path | str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> dict[str, Any]:
    """One paid generator call over the served build; a facts PROPOSAL envelope.

    A provision of the prompt that does not resolve in the build makes no
    generator call; missing_facts then names the definition. Each flag not
    elicited and each dropped fact is named once in missing_facts.
    """
    graph_version = _graph_version(dump)
    result = elicit(
        description,
        generator,
        dump=dump,
        snapshots_dir=snapshots_dir,
        prompt_version=prompt_version,
    )
    if result.features is None:
        # A rendering failure leaves no rendered prompt: its one note names
        # the definition that does not resolve, and the dashboard shows it.
        unresolved = result.notes if result.prompt.get("rendered_sha256") is None else []
        return make_envelope(
            answer=None,
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            legal_status_notes=result.notes,
            missing_facts=[*unresolved, "elicitation failed; fill the facts manually"],
            judge_verdict=ELICITATION_JUDGE_VERDICT,
        )
    dropped = {d["path"]: d["reason"] for d in result.dropped}
    elicited = set((result.features.get("flags") or {}).keys())
    missing = []
    for name in schema_flag_names():
        if name in elicited:
            continue
        path = f"flags.{name}"
        if path in dropped:
            missing.append(f"{path} dropped: {dropped[path]}")
        else:
            missing.append(f"flag not elicited: {name}")
    missing.extend(
        f"{d['path']} dropped: {d['reason']}"
        for d in result.dropped
        if not d["path"].startswith("flags.")
    )
    return make_envelope(
        answer={
            "features": result.features,
            "quotes": result.quotes,
            "dropped": result.dropped,
            "notes": result.notes,
            "prompt": result.prompt,
        },
        status="requires_human_review",
        graph_version=graph_version,
        confidence=0.5,
        legal_status_notes=[PROPOSAL_NOTE, QUOTE_NOTE],
        missing_facts=missing,
        judge_verdict=ELICITATION_JUDGE_VERDICT,
    )
