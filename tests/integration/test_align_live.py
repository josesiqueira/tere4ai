"""Live smoke test for the M2 alignment pipeline.

COSTS REAL API MONEY: it calls the configured OpenAI generator once and the
Anthropic mapping judge once per surviving candidate (up to three), aligning
one real norm against the seven HLEG requirements. It is skipped unless the
environment variable TERE4AI_LIVE_TESTS is set to "1", and it requires a
fully configured .env (TERE4AI_GENERATOR_MODEL, TERE4AI_JUDGE_MODEL,
OPENAI_API_KEY, ANTHROPIC_API_KEY). Run it deliberately, for example:

    TERE4AI_LIVE_TESTS=1 .venv/bin/python -m pytest \
        tests/integration/test_align_live.py -q -x
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("TERE4AI_LIVE_TESTS") != "1",
        reason="live model test; set TERE4AI_LIVE_TESTS=1 to run (costs money)",
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = REPO_ROOT / "data" / "graph_dumps" / "layer1.json"
NODE_ID = "eu-ai-act:article-9:paragraph-1"


def _fixture_norm() -> dict:
    """The Article 9(1) risk-management obligation, built deterministically
    from the real layer1 dump (real source span id and verbatim text)."""
    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    node = next(n for n in dump["nodes"] if n["id"] == NODE_ID)
    return {
        "norm_id": f"norm:{NODE_ID}:n1",
        "layer": 2,
        "type": "NormativeStatement",
        "source_node_id": NODE_ID,
        "source_span_id": node["source_span"]["span_id"],
        "deontic_type": "obligation",
        "modal": "shall",
        "actor_explicit": None,
        "actor_inferred": "provider",
        "actor_inference_source_node_id": "eu-ai-act:article-16",
        "action": "establish, implement, document and maintain",
        "object": "a risk management system",
        "target_system_category": "high_risk",
        "conditions": ["in relation to high-risk AI systems"],
        "exceptions": [],
        "condition_ids": [],
        "exception_ids": [],
        "lifecycle_phase_ids": ["cross_phase"],
        "extraction_method": "fixture_deterministic",
        "extractor_model": "fixture",
        "extractor_prompt_version": "v1",
        "confidence": 1.0,
        "judge_verdict": "accepted",
        "judge_run_id": None,
        "review_status": "accepted",
        "source_text": node["text"],
    }


def test_live_alignment_of_article_9_1_against_hleg():
    from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes
    from tere4ai.align_hleg_altai.pipeline import align_norms
    from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
    from tere4ai.judge.config import load_model_config

    assert DUMP_PATH.exists(), "layer1 dump missing; run python -m tere4ai.parse_legal_structure"

    norm = _fixture_norm()
    norms_schema = json.loads(
        (REPO_ROOT / "schema" / "json_schemas" / "norms.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(norms_schema).validate(norm)

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)
    hleg_nodes = build_hleg_nodes()

    result = align_norms([norm], hleg_nodes, generator, judge, prompt_version="v1")

    assertions = result["assertions"]
    assert assertions, f"no schema-valid assertions produced; stats: {result['stats']}"

    alignments_schema = json.loads(
        (REPO_ROOT / "schema" / "json_schemas" / "alignments.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(alignments_schema)
    for assertion in assertions:
        validator.validate(assertion)
        assert assertion["source_evidence_span_ids"] == [norm["source_span_id"]]
        assert assertion["target_evidence_span_ids"]
        assert assertion["judge_verdict"] in ("accepted", "rejected", "needs_human_review")

    model_judge_runs = [
        run for run in result["judge_runs"] if run["judge_model"] != "mechanical:quote_check"
    ]
    assert model_judge_runs, "at least one candidate must reach the model judge"
    for run in model_judge_runs:
        assert run["judge_kind"] == "mapping"
        assert run["judge_model"] == cfg.judge_model
        assert "claude" in run["judge_model"].lower()

    accepted = [a for a in assertions if a["judge_verdict"] == "accepted"]
    print(f"\nlive alignment of {norm['norm_id']}: {len(assertions)} assertion(s), "
          f"{len(accepted)} accepted")
    for assertion in assertions:
        print(
            f"  [{assertion['judge_verdict']}] {assertion['target_id']} "
            f"({assertion['relation_type']}, final_score {assertion['final_score']:.2f})"
        )
