"""Unit tests for the M4 evaluation harness, strategies, and loaders.

Offline only: every strategy runs on FakeClient (scripted, no network).
Live behaviour is tested exclusively as refusal paths (the gate and the
config guard must raise); no test here may ever call a model.
"""

import json
from pathlib import Path

import pytest

from tere4ai.eval.harness import (
    BENCHMARK_RISK_MAP,
    EVAL_CONFIG_PATH,
    EvalConfigMismatch,
    LiveGateError,
    OfflineStubClient,
    guard_live_config,
    load_benchmark_items,
    load_gold_items,
    read_config_of_record,
    results_artifact_name,
    run_eval,
)
from tere4ai.eval.strategies import STRATEGY_NAMES, TfidfIndex, build_strategy
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.judge.config import ModelConfig
from tere4ai.mcp_server.classify import classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

# Synthetic fixtures -----------------------------------------------------------

MINI_DUMP = {
    "build": {"build_id": "build-test"},
    "nodes": [
        {"id": "test:article-1", "type": "Article", "number": 1, "title": "Widgets"},
        {
            "id": "test:article-1:paragraph-1",
            "type": "Paragraph",
            "text": "Providers shall document biometric widgets in the register.",
        },
        {
            "id": "test:annex-x:point-1",
            "type": "AnnexItem",
            "text": "Biometric widgets used for identification of persons.",
        },
    ],
    "edges": [],
}

MINI_NORMS = {
    "build": {"build_id": "build-test"},
    "norms": [
        {
            "norm_id": "norm:t1",
            "source_node_id": "test:article-1:paragraph-1",
            "judge_verdict": "accepted",
            "deontic_type": "obligation",
            "modal": "shall",
            "actor_explicit": "providers",
            "action": "document biometric widgets",
            "object": "the register",
            "conditions": [],
            "exceptions": [],
        },
        {
            "norm_id": "norm:t2",
            "source_node_id": "test:article-2:paragraph-1",
            "judge_verdict": "rejected",
            "deontic_type": "obligation",
            "modal": "shall",
            "actor_explicit": "deployers",
            "action": "ignore biometric widgets entirely",
            "object": "nothing",
            "conditions": [],
            "exceptions": [],
        },
    ],
}

GOLD_3 = [
    {
        "id": "t:cls-1",
        "kind": "classification",
        "system_features": {
            "description": "An unknown-flags test system with no structured facts.",
            "flags": {},
        },
        "gold": {"risk_category": "uncertain"},
        "gold_citations": [],
    },
    {
        "id": "t:ret-1",
        "kind": "retrieval",
        "question": "Which annex item covers biometric widgets used for identification?",
        "gold": {"node_id": "test:annex-x:point-1"},
        "gold_citations": ["test:annex-x:point-1"],
    },
    {
        "id": "t:qa-1",
        "kind": "qa",
        "question": "What must providers do with biometric widgets?",
        "gold": {"answer_text": "Document them in the register."},
        "gold_citations": ["test:article-1"],
    },
]


def _gen_response(citations, risk=None):
    return json.dumps(
        {"answer_text": "scripted answer", "citations": citations, "risk_category": risk}
    )


def make_generator() -> FakeClient:
    """Scripted generator covering the three test items (keyed on their text)."""
    return FakeClient(
        {
            "unknown-flags test system": _gen_response([], risk="uncertain"),
            "Which annex item covers biometric widgets": _gen_response(
                ["test:annex-x:point-1", "test:fabricated-node"]
            ),
            "What must providers do": _gen_response(["test:article-1:paragraph-1"]),
        },
        model="fake-generator",
    )


def make_judge(verdict="accepted") -> FakeClient:
    return FakeClient(
        {
            "Generated runtime answer under review": json.dumps(
                {"verdict": verdict, "scores": {}, "rationale": "scripted verdict"}
            )
        },
        model="fake-judge",
    )


def build_all_strategies(tmp_path: Path) -> dict:
    generator = make_generator()
    judge = make_judge()
    return {
        name: build_strategy(
            name,
            generator,
            MINI_DUMP,
            MINI_NORMS,
            judge=judge,
            judge_log_path=tmp_path / "judge_log.jsonl",
        )
        for name in STRATEGY_NAMES
    }


# Strategies -------------------------------------------------------------------


def test_tfidf_index_ranks_matching_passage_first():
    index = TfidfIndex(
        [("p1", "biometric widgets identification"), ("p2", "unrelated cabbage soup")]
    )
    hits = index.query("biometric widgets", top_k=2)
    assert hits[0][0] == "p1"
    assert all(len(hit) == 3 for hit in hits)


def test_every_strategy_returns_uniform_shape(tmp_path):
    strategies = build_all_strategies(tmp_path)
    assert set(strategies) == set(STRATEGY_NAMES)
    for name, strategy in strategies.items():
        for item in GOLD_3:
            result = strategy(item)
            assert isinstance(result["answer_text"], str), (name, item["id"])
            assert isinstance(result["citations"], list), (name, item["id"])
            assert "risk_category" in result, (name, item["id"])


def test_graph_strategies_use_deterministic_classification(tmp_path):
    strategies = build_all_strategies(tmp_path)
    for name in ("graph_no_judge", "graph_build_judge", "graph_full"):
        result = strategies[name](GOLD_3[0])
        # Unknown flags: the deterministic ladder says uncertain; the
        # generator can never override it.
        assert result["risk_category"] == "uncertain", name


def test_graph_no_judge_offers_rejected_norms_and_build_judge_does_not(tmp_path):
    strategies = build_all_strategies(tmp_path)
    no_judge = strategies["graph_no_judge"](GOLD_3[2])
    judged = strategies["graph_build_judge"](GOLD_3[2])
    assert "norm:t2" in no_judge["offered_norm_ids"]  # rejected norm still offered
    assert judged["offered_norm_ids"] == ["norm:t1"]  # accepted only


def test_graph_full_withholds_unverifiable_citations_and_attaches_verdict(tmp_path):
    strategies = build_all_strategies(tmp_path)
    unfiltered = strategies["graph_build_judge"](GOLD_3[1])
    gated = strategies["graph_full"](GOLD_3[1])
    assert "test:fabricated-node" in unfiltered["citations"]
    assert "test:fabricated-node" not in gated["citations"]
    assert gated["citations"] == ["test:annex-x:point-1"]
    assert gated["judge_verdict"] == "accepted"
    log = (tmp_path / "judge_log.jsonl").read_text(encoding="utf-8")
    assert "runtime_grounding" in log


def test_graph_full_degrades_on_non_accepted_verdict(tmp_path):
    strategy = build_strategy(
        "graph_full",
        make_generator(),
        MINI_DUMP,
        MINI_NORMS,
        judge=make_judge(verdict="rejected"),
        judge_log_path=tmp_path / "judge_log.jsonl",
    )
    result = strategy(GOLD_3[2])
    assert result["judge_verdict"] == "rejected"
    assert result["status"] == "requires_human_review"


def test_graph_full_requires_a_judge_client():
    with pytest.raises(ValueError, match="judge"):
        build_strategy("graph_full", make_generator(), MINI_DUMP, MINI_NORMS)


def test_unknown_strategy_name_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        build_strategy("graph_maximal", make_generator(), MINI_DUMP, MINI_NORMS)


# Harness: run_eval ------------------------------------------------------------


def test_run_eval_writes_well_formed_deterministic_artifact(tmp_path):
    results_dir = tmp_path / "results"
    artifact = run_eval(
        GOLD_3,
        build_all_strategies(tmp_path),
        dump=MINI_DUMP,
        results_dir=results_dir,
    )
    expected_name = results_artifact_name("build-test", list(STRATEGY_NAMES))
    path = results_dir / expected_name
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["build_id"] == "build-test"
    assert on_disk["live"] is False
    assert on_disk["config"]["mode"] == "offline"
    assert on_disk["strategies"] == sorted(STRATEGY_NAMES)
    assert on_disk["n_items"] == 3
    for name in STRATEGY_NAMES:
        per_item = on_disk["results"][name]["items"]
        assert set(per_item) == {"t:cls-1", "t:ret-1", "t:qa-1"}
        for result in per_item.values():
            assert "answer_text" in result
            assert "citations" in result
            assert result["latency_s"] >= 0
        assert on_disk["results"][name]["models"]["generator"] == "fake-generator"
    assert on_disk["results"]["graph_full"]["models"]["judge"] == "fake-judge"
    assert artifact["artifact_path"] == str(path)

    # Re-running the same build and strategy set overwrites the same file:
    # the name carries no timestamp and no randomness.
    run_eval(GOLD_3, build_all_strategies(tmp_path), dump=MINI_DUMP, results_dir=results_dir)
    assert [p.name for p in results_dir.glob("*.json")] == [expected_name]


def test_run_eval_builds_strategies_from_names_and_factories(tmp_path):
    artifact = run_eval(
        GOLD_3,
        ["plain_llm", "vector_rag"],
        generator_factory=make_generator,
        dump=MINI_DUMP,
        norms_payload=MINI_NORMS,
        results_dir=tmp_path / "results",
    )
    assert artifact["strategies"] == ["plain_llm", "vector_rag"]
    assert artifact["results"]["plain_llm"]["items"]["t:qa-1"]["citations"] == [
        "test:article-1:paragraph-1"
    ]


def test_run_eval_records_per_item_errors_instead_of_dying(tmp_path):
    empty_generator = FakeClient({}, model="fake-generator")  # no scripted keys
    artifact = run_eval(
        GOLD_3[:1],
        {"plain_llm": build_strategy("plain_llm", empty_generator, MINI_DUMP, MINI_NORMS)},
        dump=MINI_DUMP,
        results_dir=tmp_path / "results",
    )
    result = artifact["results"]["plain_llm"]["items"]["t:cls-1"]
    assert "error" in result
    assert result["citations"] == []


def test_artifact_name_is_order_insensitive_and_build_keyed():
    a = results_artifact_name("build-x", ["plain_llm", "vector_rag"])
    b = results_artifact_name("build-x", ["vector_rag", "plain_llm"])
    c = results_artifact_name("build-y", ["plain_llm", "vector_rag"])
    d = results_artifact_name("build-x", ["plain_llm"])
    assert a == b
    assert a != c
    assert a != d
    assert a.startswith("eval_build-x_")


# Live gates and the config guard ----------------------------------------------


def test_config_of_record_parses_the_real_file():
    record = read_config_of_record(EVAL_CONFIG_PATH)
    assert record == {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}


def _fake_cfg(generator="gpt-5.2", judge="claude-opus-4-8") -> ModelConfig:
    return ModelConfig(
        generator_model=generator,
        judge_model=judge,
        generator_api_key="sk-fake",
        judge_api_key="sk-ant-fake",
    )


def test_guard_accepts_matching_config_and_rejects_mismatch():
    assert guard_live_config(cfg=_fake_cfg()) == _fake_cfg()
    with pytest.raises(EvalConfigMismatch, match="generator model"):
        guard_live_config(cfg=_fake_cfg(generator="gpt-other"))
    with pytest.raises(EvalConfigMismatch, match="judge model"):
        guard_live_config(cfg=_fake_cfg(judge="claude-other"))


def test_run_eval_live_refuses_without_env_gate(monkeypatch):
    monkeypatch.delenv("TERE4AI_LIVE_TESTS", raising=False)
    with pytest.raises(LiveGateError, match="TERE4AI_LIVE_TESTS"):
        run_eval(GOLD_3, {}, live=True, dump=MINI_DUMP)


def test_run_eval_live_refuses_on_config_mismatch(monkeypatch, tmp_path):
    # Gate open, but the loaded config differs from the config of record:
    # the run must refuse BEFORE any strategy (and thus any model) runs.
    monkeypatch.setenv("TERE4AI_LIVE_TESTS", "1")
    monkeypatch.setenv("TERE4AI_GENERATOR_MODEL", "gpt-not-the-record")
    monkeypatch.setenv("TERE4AI_JUDGE_MODEL", "claude-not-the-record")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    with pytest.raises(EvalConfigMismatch, match="config of record"):
        run_eval(
            GOLD_3, {}, live=True, dump=MINI_DUMP, results_dir=tmp_path / "results"
        )
    assert not (tmp_path / "results").exists(), "a refused live run must write nothing"


def test_offline_stub_is_clearly_labelled():
    stub = OfflineStubClient()
    body = json.loads(stub.complete("system", "user"))
    assert "no model was called" in body["answer_text"]
    assert body["verdict"] == "needs_human_review"
    assert stub.model == "offline-stub-no-model"


# Loaders ------------------------------------------------------------------


def test_load_gold_seed_items():
    items = load_gold_items()
    assert len(items) == 10
    kinds = sorted(item["kind"] for item in items)
    assert kinds.count("classification") == 6
    assert kinds.count("retrieval") == 2
    assert kinds.count("qa") == 2
    ids = [item["id"] for item in items]
    assert len(set(ids)) == 10
    for item in items:
        assert item["author"] == "seed"
        assert item["second_annotator"] is None


def test_load_benchmark_sample_parses_real_format():
    items = load_benchmark_items()
    payload = json.loads(
        (ROOT / "eval" / "gold" / "benchmark_sample.json").read_text(encoding="utf-8")
    )
    n_scenarios = len(payload["scenarios"])
    n_qa = len(payload["qa_pairs"])
    assert len(items) == n_scenarios + n_qa == 47
    classification = [i for i in items if i["kind"] == "classification"]
    qa = [i for i in items if i["kind"] == "qa"]
    assert len(classification) == n_scenarios
    assert len(qa) == n_qa
    valid_risks = set(BENCHMARK_RISK_MAP.values())
    for item in classification:
        assert item["gold"]["risk_category"] in valid_risks
        # Free-text scenarios are NOT mapped into structured features by
        # the loader; that is annotation work (eval/README.md).
        assert item["system_features"] is None
        assert item["system_text"]
        assert all(c.startswith("eu-ai-act:article-") for c in item["gold_citations"])
    for item in qa:
        assert item["question"]
        assert len(item["gold_citations"]) == 1
        assert item["gold_citations"][0].startswith("eu-ai-act:article-")
    assert len({item["id"] for item in items}) == len(items)


def test_loader_rejects_malformed_items(tmp_path):
    bad = tmp_path / "bad_gold.json"
    bad.write_text(json.dumps({"items": [{"id": "x", "kind": "qa"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_gold_items(bad)


# Gold citations resolve in the published dump ----------------------------------


@pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")
def test_every_gold_citation_exists_in_layer1_dump():
    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in dump["nodes"]}
    for item in load_gold_items():
        for cite in item["gold_citations"]:
            assert cite in node_ids, f"{item['id']}: gold citation {cite} not in dump"


@pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")
def test_gold_classification_items_agree_with_deterministic_classifier():
    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    for item in load_gold_items():
        if item["kind"] != "classification":
            continue
        envelope = classify_ai_system(item["system_features"], dump)
        assert envelope["answer"]["risk_category"] == item["gold"]["risk_category"], item["id"]
        if item["gold_citations"]:
            assert set(item["gold_citations"]) <= set(envelope["source_nodes"]), item["id"]
