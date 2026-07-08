"""Live smoke test for the M3 runtime tools and the runtime grounding judge.

COSTS REAL API MONEY: it calls the configured OpenAI generator and the
Anthropic judge twice each (one evaluate_project_evidence call and one
generate_control_backlog call, each of which is one generator call plus one
runtime-grounding judge call). It is skipped unless the environment
variable TERE4AI_LIVE_TESTS is set to "1", and it requires a fully
configured .env (TERE4AI_GENERATOR_MODEL, TERE4AI_JUDGE_MODEL,
OPENAI_API_KEY, ANTHROPIC_API_KEY) plus the judged M2 norms dump. Run it
deliberately, for example:

    TERE4AI_LIVE_TESTS=1 .venv/bin/python -m pytest \
        tests/integration/test_runtime_live.py -q -x
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("TERE4AI_LIVE_TESTS") != "1",
        reason="live model test; set TERE4AI_LIVE_TESTS=1 to run (costs money)",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMS_PATH = REPO_ROOT / "data" / "graph_dumps" / "norms_core.json"

SYNTHETIC_RISK_PLAN = (
    "We maintain a documented risk management plan for the system, and it "
    "is reviewed and updated at every release. Identified risks and their "
    "mitigations are recorded in a risk register owned by the engineering lead."
)

RUNTIME_VERDICTS = ("accepted", "rejected", "needs_human_review")


def _load_accepted_norms():
    if not NORMS_PATH.exists():
        pytest.skip(f"judged norms dump missing: {NORMS_PATH}")
    payload = json.loads(NORMS_PATH.read_text(encoding="utf-8"))
    accepted = [n for n in payload.get("norms", []) if n.get("judge_verdict") == "accepted"]
    if not accepted:
        pytest.skip("norms dump holds no judge-accepted norms")
    return accepted, payload


def _clients():
    from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
    from tere4ai.judge.config import load_model_config

    cfg = load_model_config()
    return cfg, OpenAIGenerator(cfg), AnthropicJudge(cfg)


def _assert_envelope_shape(envelope):
    from tere4ai.mcp_server.tools import STATUS_VOCABULARY

    for key in (
        "answer",
        "status",
        "confidence",
        "source_nodes",
        "source_spans",
        "graph_evidence_subgraph",
        "legal_status_notes",
        "missing_facts",
        "judge_verdict",
        "generated_at",
        "graph_version",
        "non_legal_advice_notice",
    ):
        assert key in envelope, f"envelope missing {key}"
    assert envelope["status"] in STATUS_VOCABULARY
    assert envelope["non_legal_advice_notice"]
    # The closed vocabulary itself can never carry compliance-like terms;
    # live free-text rationales may mention them while denying them, so the
    # check targets the status, not the whole dump.
    for forbidden in ("compliant", "certified", "approved"):
        assert forbidden not in envelope["status"]


def test_live_evaluate_project_evidence_on_one_accepted_norm():
    from tere4ai.mcp_server.evidence import evaluate_project_evidence

    accepted, payload = _load_accepted_norms()
    a9p2 = [
        n for n in accepted if n["source_node_id"].startswith("eu-ai-act:article-9:paragraph-2")
    ]
    norm = (a9p2 or accepted)[0]
    cfg, generator, judge = _clients()

    envelope = evaluate_project_evidence(
        norm,
        {
            "artifact_type": "risk_management_plan",
            "artifact_id": "live-smoke-rmp",
            "content": SYNTHETIC_RISK_PLAN,
        },
        generator,
        judge,
        prompt_version="v1",
        graph_version=str(payload.get("build", {}).get("build_id", "unknown")),
    )

    _assert_envelope_shape(envelope)
    # Any verdict is acceptable; what matters is that a verdict exists and
    # that a non-accepting one degraded the status.
    assert envelope["judge_verdict"] in RUNTIME_VERDICTS
    if envelope["judge_verdict"] != "accepted":
        assert envelope["status"] == "requires_human_review"
    answer = envelope["answer"]
    assert answer["assessment"] in (
        "satisfied",
        "partially_satisfied",
        "missing",
        "contradicted",
        "cannot_assess",
    )
    assert answer["judge_rationale"]
    # The judge is the configured independent Claude family (DEC-07).
    assert answer["judge_model"] == cfg.judge_model
    assert "claude" in answer["judge_model"].lower()
    assert envelope["source_nodes"] == [norm["source_node_id"]]
    for quote in answer["quotes"]:
        assert quote in SYNTHETIC_RISK_PLAN or " ".join(quote.split()) in " ".join(
            SYNTHETIC_RISK_PLAN.split()
        )


def test_live_generate_control_backlog_cites_only_input_norms():
    from tere4ai.mcp_server.backlog import generate_control_backlog

    accepted, payload = _load_accepted_norms()
    norms = accepted[:3]
    assert len(norms) == 3, "need three accepted norms for the backlog smoke"
    cfg, generator, judge = _clients()

    envelope = generate_control_backlog(
        norms,
        "A high-risk AI system that triages emergency-room patients in an EU hospital.",
        generator,
        judge,
        prompt_version="v1",
        graph_version=str(payload.get("build", {}).get("build_id", "unknown")),
    )

    _assert_envelope_shape(envelope)
    assert envelope["judge_verdict"] in RUNTIME_VERDICTS
    if envelope["judge_verdict"] != "accepted":
        assert envelope["status"] == "requires_human_review"
    else:
        assert envelope["status"] == "applicable_missing_evidence"
    answer = envelope["answer"]
    assert answer["items"], f"no backlog items survived; notes: {answer['notes']}"
    assert answer["judge_model"] == cfg.judge_model
    assert "claude" in answer["judge_model"].lower()
    allowed_ids = {n["norm_id"] for n in norms}
    for item in answer["items"]:
        assert set(item["norm_ids"]) <= allowed_ids
        assert item["priority"] in ("must", "should")
