"""Live smoke test for the M2 norm-extraction pipeline.

COSTS REAL API MONEY: it calls the configured OpenAI generator and the
Anthropic judge on one real source unit. It is skipped unless the
environment variable TERE4AI_LIVE_TESTS is set to "1", and it requires a
fully configured .env (TERE4AI_GENERATOR_MODEL, TERE4AI_JUDGE_MODEL,
OPENAI_API_KEY, ANTHROPIC_API_KEY). Run it deliberately, for example:

    TERE4AI_LIVE_TESTS=1 .venv/bin/python -m pytest \
        tests/integration/test_extract_norms_live.py -q -x
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


def test_live_extraction_on_article_9_paragraph_1():
    from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
    from tere4ai.extract_norms.pipeline import extract_norms
    from tere4ai.judge.config import load_model_config

    assert DUMP_PATH.exists(), "layer1 dump missing; run python -m tere4ai.parse_legal_structure"
    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)

    result = extract_norms(dump, [NODE_ID], generator, judge, prompt_version="v1")

    norms = result["norms"]
    assert norms, f"no schema-valid norms extracted; stats: {result['stats']}"

    schema = json.loads(
        (REPO_ROOT / "schema" / "json_schemas" / "norms.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    for norm in norms:
        validator.validate(norm)
        assert norm["source_span_id"]
        assert norm["judge_verdict"] in ("accepted", "rejected", "needs_human_review")

    # Article 9(1) states the risk-management-system obligation.
    assert any(norm["deontic_type"] == "obligation" for norm in norms)

    judge_runs = result["judge_runs"]
    assert judge_runs, "every judged candidate must produce a JudgeRun"
    for run in judge_runs:
        assert run["judge_kind"] == "extraction"
        assert run["judge_model"] == cfg.judge_model
        assert "claude" in run["judge_model"].lower()
