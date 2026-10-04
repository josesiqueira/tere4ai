"""Unit tests for the M4 evaluation harness, strategies, and loaders.

Offline only: every strategy runs on FakeClient (scripted, no network).
Live behaviour is tested exclusively as refusal paths (the gate and the
config guard must raise); no test here may ever call a model.

Also covers DEC-17: run_eval and main record one E6 evaluation record per
run and write the results artifact atomically, refuse a served manifest
lacking a role, and finish the record failed on any exception.
"""

import json
import types
from pathlib import Path

import pytest
from tests.fixtures.model_parameters import declared, write_table

from tere4ai.eval.evaluation_record import EvaluationRecordStore
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
from tere4ai.graph_store.build_chain import build_chain, sha256_of_file
from tere4ai.judge import config as config_module
from tere4ai.judge.config import ModelConfig

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
        "gold": {"risk_category": "undetermined"},
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
            "unknown-flags test system": _gen_response([], risk="undetermined"),
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
        # Unknown flags: the deterministic ladder says undetermined; the
        # generator can never override it.
        assert result["risk_category"] == "undetermined", name


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


def test_graph_runtime_judge_offers_every_norm_and_gates_with_the_runtime_judge(tmp_path):
    # B126: condition 3 (every extracted norm offered, the build judge
    # ignored) plus the runtime grounding judge of graph_full
    strategies = build_all_strategies(tmp_path)
    answered = strategies["graph_runtime_judge"](GOLD_3[2])
    assert "norm:t2" in answered["offered_norm_ids"]  # rejected norm still offered
    assert answered["offered_norm_ids"] == strategies["graph_no_judge"](GOLD_3[2])["offered_norm_ids"]
    assert answered["judge_verdict"] == "accepted"
    gated = strategies["graph_runtime_judge"](GOLD_3[1])
    assert "test:fabricated-node" not in gated["citations"]
    assert gated["citations"] == ["test:annex-x:point-1"]
    assert gated["judge_verdict"] == "accepted"
    assert strategies["graph_runtime_judge"].models["judge"] == "fake-judge"


def test_graph_runtime_judge_requires_a_judge_client():
    with pytest.raises(ValueError, match="graph_runtime_judge needs a judge"):
        build_strategy("graph_runtime_judge", make_generator(), MINI_DUMP, MINI_NORMS)


def test_graph_runtime_judge_takes_a_prompt_version_suffix(tmp_path):
    strategy = build_strategy("graph_runtime_judge@v2", make_generator(), MINI_DUMP, MINI_NORMS,
                              judge=make_judge(), judge_log_path=tmp_path / "judge_log.jsonl")
    assert strategy.name == "graph_runtime_judge@v2"
    assert strategy.models["judge_prompt_version"] == "v2"
    assert build_strategy("graph_runtime_judge", make_generator(), MINI_DUMP, MINI_NORMS,
                          judge=make_judge()).models["judge_prompt_version"] == "v1"


def test_uses_runtime_judge_names_the_two_judged_conditions():
    from tere4ai.eval.strategies import uses_runtime_judge
    assert STRATEGY_NAMES[-1] == "graph_runtime_judge"
    assert [n for n in STRATEGY_NAMES if uses_runtime_judge(n)] == ["graph_full", "graph_runtime_judge"]
    assert uses_runtime_judge("graph_full@v2") and uses_runtime_judge("graph_runtime_judge@v2")
    assert not uses_runtime_judge("graph_no_judge@v2") and not uses_runtime_judge("graph_fullish")


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
    # B99 (spec F D-F29): the efforts are the declared rows' values now
    return ModelConfig(generator_model=generator, judge_model=judge, generator_api_key="sk-fake",
                       judge_api_key="sk-ant-fake", generator_parameters=declared(generator, "openai"),
                       judge_parameters=declared(judge, "anthropic"))


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
    # B99 (spec F D-F29): a declared row for each model, and no .env read, so a
    # local .env with the retired lines cannot refuse first
    monkeypatch.delenv("TERE4AI_GENERATOR_EFFORT", raising=False)
    monkeypatch.delenv("TERE4AI_JUDGE_EFFORT", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv_once", lambda: None)
    monkeypatch.setattr(config_module, "MODEL_PARAMETERS_PATH", write_table(
        tmp_path / "model_parameters.json", declared("gpt-not-the-record", "openai"),
        declared("claude-not-the-record", "anthropic")))
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
        # B128: one annotator's label each; the two independent labels and
        # the adjudication come with the protocol, never from the classifier.
        assert item["labels"] == []
        assert item["adjudication"] is None


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


# AnnexItem-level retrieval (#55) ----------------------------------------------


def test_retrieval_items_offer_annex_items():
    generator = make_generator()
    strategy = build_strategy("graph_build_judge", generator, MINI_DUMP, MINI_NORMS)
    result = strategy(GOLD_3[1])
    _system, user = generator.calls[-1]
    assert "test:annex-x:point-1" in user
    assert "Biometric widgets used for identification" in user
    assert result["offered_annex_item_ids"] == ["test:annex-x:point-1"]


def test_qa_items_do_not_get_annex_context():
    generator = make_generator()
    strategy = build_strategy("graph_build_judge", generator, MINI_DUMP, MINI_NORMS)
    result = strategy(GOLD_3[2])
    assert "offered_annex_item_ids" not in result
    _system, user = generator.calls[-1]
    assert "Annex items from the Act" not in user


@pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")
def test_gold_ret_items_hit_annex_item_granularity_in_the_real_index():
    from tere4ai.eval.harness import load_gold_items

    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    index = TfidfIndex(
        [
            (n["id"], n["text"])
            for n in dump["nodes"]
            if n.get("type") == "AnnexItem" and n.get("text")
        ]
    )
    for item in load_gold_items():
        if item["kind"] != "retrieval":
            continue
        hits = [nid for nid, _s, _t in index.query(item["question"], top_k=5)]
        assert any(
            gold in hits for gold in item["gold_citations"]
        ), f"{item['id']}: gold {item['gold_citations']} not in top-5 {hits}"


# QA article-text retrieval (#54) ----------------------------------------------


def test_qa_items_offer_operative_passages_with_node_ids():
    generator = make_generator()
    strategy = build_strategy("graph_build_judge", generator, MINI_DUMP, MINI_NORMS)
    result = strategy(GOLD_3[2])
    _system, user = generator.calls[-1]
    assert "Operative provisions of the Act" in user
    assert "test:article-1:paragraph-1" in user
    assert "Providers shall document biometric widgets" in user
    assert result["offered_passage_ids"]


def test_qa_passages_never_include_recitals():
    dump_with_recital = json.loads(json.dumps(MINI_DUMP))
    dump_with_recital["nodes"].append(
        {
            "id": "test:recital-1",
            "type": "Recital",
            "text": "Biometric widgets deserve careful documentation by providers.",
        }
    )
    generator = make_generator()
    strategy = build_strategy("graph_build_judge", generator, dump_with_recital, MINI_NORMS)
    result = strategy(GOLD_3[2])
    _system, user = generator.calls[-1]
    assert "test:recital-1" not in user
    assert "test:recital-1" not in result.get("offered_passage_ids", [])


@pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")
def test_gold_qa_items_hit_their_article_in_the_real_passage_index():
    from tere4ai.eval.harness import load_gold_items

    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    index = TfidfIndex(
        [
            (n["id"], n["text"])
            for n in dump["nodes"]
            if n.get("type") in ("Paragraph", "Point", "Subparagraph", "AnnexItem")
            and n.get("text")
        ]
    )
    for item in load_gold_items():
        if item["kind"] != "qa":
            continue
        hits = [nid for nid, _s, _t in index.query(item["question"], top_k=5)]
        assert any(
            any(h.startswith(gold) for h in hits) for gold in item["gold_citations"]
        ), f"{item['id']}: no top-5 passage under {item['gold_citations']}; got {hits}"


# Prompt A/B conditions + shared audit log (#39) ---------------------------------


def test_graph_full_at_version_runs_that_judge_prompt(tmp_path, monkeypatch):
    import tere4ai.extract_norms.pipeline as pipeline_mod

    prompts = tmp_path / "prompts" / "runtime_grounding"
    prompts.mkdir(parents=True)
    (prompts / "vB.md").write_text("VARIANT-B JUDGE PROMPT", encoding="utf-8")
    monkeypatch.setattr(pipeline_mod, "PROMPTS_DIR", tmp_path / "prompts")

    generator = make_generator()
    judge = make_judge()
    strategy = build_strategy(
        "graph_full@vB",
        generator,
        MINI_DUMP,
        MINI_NORMS,
        judge=judge,
        judge_log_path=tmp_path / "judge_log.jsonl",
    )
    assert strategy.models["judge_prompt_version"] == "vB"
    result = strategy(GOLD_3[2])
    assert result["judge_verdict"] == "accepted"
    judge_system, _user = judge.calls[-1]
    assert judge_system == "VARIANT-B JUDGE PROMPT"
    log = (tmp_path / "judge_log.jsonl").read_text(encoding="utf-8")
    assert '"prompt_version": "vB"' in log


def test_plain_graph_full_defaults_to_v1(tmp_path):
    strategy = build_strategy(
        "graph_full",
        make_generator(),
        MINI_DUMP,
        MINI_NORMS,
        judge=make_judge(),
        judge_log_path=tmp_path / "judge_log.jsonl",
    )
    assert strategy.models["judge_prompt_version"] == "v1"


def test_audit_log_scrubs_key_material(tmp_path):
    from tere4ai.judge.audit_log import append_event, read_events

    log = tmp_path / "log.jsonl"
    append_event(
        log,
        {
            "timestamp": "2026-07-10T00:00:00+00:00",
            "rationale": "the artifact leaked sk-abc123DEF456ghi789 and "
            "t4a_0123456789ab_SeCrEtSeCrEt00 in its text",
            "nested": {"header": "Authorization: Bearer abcdefghijklmnopqrstu"},
        },
    )
    events = list(read_events(log))
    blob = json.dumps(events)
    assert "sk-abc123DEF456ghi789" not in blob
    assert "SeCrEtSeCrEt00" not in blob
    assert "abcdefghijklmnopqrstu" not in blob
    assert blob.count("[REDACTED]") == 3


def test_consolidate_merges_and_tags_by_kind(tmp_path):
    from tere4ai.judge.audit_log import append_event, consolidate

    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    append_event(a, {"timestamp": "2026-07-10T02:00:00+00:00", "verdict": "accepted"})
    append_event(b, {"timestamp": "2026-07-10T01:00:00+00:00", "verdict": "rejected"})
    merged = consolidate({"extraction": a, "runtime_grounding": b})
    assert [e["log_kind"] for e in merged] == ["runtime_grounding", "extraction"]


def test_repo_root_env_override(monkeypatch, tmp_path):
    """B54: a wheel install points TERE4AI_REPO_ROOT at a checkout; the
    default stays parents[3] (the editable-install repo root)."""
    from tere4ai.eval import harness

    monkeypatch.setenv("TERE4AI_REPO_ROOT", str(tmp_path))
    assert harness._repo_root() == tmp_path.resolve()
    monkeypatch.delenv("TERE4AI_REPO_ROOT")
    assert harness._repo_root() == Path(harness.__file__).resolve().parents[3]


def test_read_config_of_record_names_the_missing_path(tmp_path):
    from tere4ai.eval import harness

    missing = tmp_path / "eval" / "config_evaluated.yaml"
    with pytest.raises(harness.EvalAssetMissingError) as exc:
        harness.read_config_of_record(missing)
    assert str(missing) in str(exc.value)
    assert "TERE4AI_REPO_ROOT" in str(exc.value)


# Evaluation records (DEC-17) ---------------------------------------------------


def test_run_eval_records_an_offline_run_with_the_artifact_copied(tmp_path):
    strategies_map = build_all_strategies(tmp_path)
    items = list(GOLD_3)
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(items, strategies_map, results_dir=tmp_path / "results", record_store=store, argv=["--offline"])
    rec = store.read(out["record_id"])
    assert rec["kind"] == "run" and rec["command"] == "eval_harness" and rec["config"]["mode"] == "offline"
    assert rec["models"] is None and rec["usage"] is None and rec["outcome"]["status"] == "completed"
    assert rec["outcome"]["intended_items"] == [i["id"] for i in items]
    (artifact,) = rec["outputs"]
    assert artifact["role"] == "artifact" and (store.dir / artifact["copy"]).read_bytes() == Path(out["artifact_path"]).read_bytes()
    assert [i["role"] for i in rec["inputs"]] == ["gold_seed"], "prebuilt strategies: the harness read no dump"
    assert rec["notes"] == ["the strategies were passed prebuilt; the harness did not read their inputs"]


def test_run_eval_item_error_yields_a_partial_record(tmp_path):
    items = list(GOLD_3)[:2]
    second = items[1]["id"]

    def broken(item):
        if item["id"] == second:
            raise ValueError("no")
        return {"answer_text": "a", "citations": [], "risk_category": "high"}
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(items, {"plain_llm": broken}, results_dir=tmp_path / "r", record_store=store)
    rec = store.read(out["record_id"])
    assert rec["outcome"]["status"] == "partial" and rec["outcome"]["completed_items"] == [items[0]["id"]]


def test_run_eval_without_a_store_records_nothing_and_writes_atomically(tmp_path):
    items = list(GOLD_3)[:1]
    out = run_eval(items, {"plain_llm": lambda item: {"answer_text": "a", "citations": [], "risk_category": "high"}},
                   results_dir=tmp_path / "r")
    assert out["record_id"] is None and not (tmp_path / "evaluation_records").exists()
    assert not list((tmp_path / "r").glob("tmp*")), "no temp file is left behind"
    assert Path(out["artifact_path"]).read_text().endswith("\n")


def _write_legacy_dumps(dump_dir: Path) -> None:
    """Minimal legacy layer1/norms dumps under dump_dir, the shape
    tests/unit/test_run_ablations_record.py's _dumps helper writes."""
    (dump_dir / "layer1.json").write_text(
        json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}), encoding="utf-8"
    )
    (dump_dir / "norms_core.json").write_text(
        json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "stats": {}}), encoding="utf-8"
    )


def test_main_records_by_default_and_not_with_no_record(tmp_path):
    from tere4ai.eval import harness as h
    _write_legacy_dumps(tmp_path)
    args = ["--strategies", "plain_llm", "--results-dir", str(tmp_path / "r"), "--dump-dir", str(tmp_path)]
    assert h.main(args) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["command"] == "eval_harness" and rec["argv"][:2] == ["--strategies", "plain_llm"]
    assert [i["role"] for i in rec["inputs"]] == ["layer1_dump", "norms", "gold_seed"], "the names branch read the dumps"
    assert rec["inputs"][0]["file"] == "layer1.json" and rec["sampling"] is None, "the offline stub reports no sampling"
    assert rec["build"]["base_build_id"] == "build-b", "the dumps were read from tmp_path, not the checkout"
    assert h.main(args + ["--no-record"]) == 0
    assert len(EvaluationRecordStore(tmp_path, create=False).list_records()) == 1


def test_the_harness_names_the_run_it_repeats_and_refuses_an_unknown_one(tmp_path, capsys):
    """B81 item 19."""
    from tere4ai.eval import harness as h
    _write_legacy_dumps(tmp_path)
    args = ["--strategies", "plain_llm", "--results-dir", str(tmp_path / "r"), "--dump-dir", str(tmp_path)]
    assert h.main(args) == 0
    (first,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert h.main(args + ["--repeat-of", first["record_id"]]) == 0
    second = next(r for r in EvaluationRecordStore(tmp_path, create=False).list_records()
                  if r["record_id"] != first["record_id"])
    assert second["relations"]["repeat_of"] == first["record_id"]
    assert h.main(args + ["--repeat-of", "0123456789ab"]) == 2
    assert "--repeat-of" in capsys.readouterr().out
    assert h.main(args + ["--repeat-of", first["record_id"], "--no-record"]) == 2
    assert len(EvaluationRecordStore(tmp_path, create=False).list_records()) == 2
    # B81 item 10: a refused --repeat-of on a fresh dump directory creates no store
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _write_legacy_dumps(fresh)
    assert h.main(["--strategies", "plain_llm", "--results-dir", str(tmp_path / "r"), "--dump-dir", str(fresh),
                   "--repeat-of", "0123456789ab"]) == 2
    assert not (fresh / "evaluation_records").exists()


def test_a_per_item_error_names_the_file_never_the_path(tmp_path):
    """B81 item 24: the results artifact is an output file others read."""
    items = list(GOLD_3)[:1]

    def broken(item):
        raise FileNotFoundError("[Errno 2] No such file or directory: '/home/someone/private/cache/features.json'")
    out = run_eval(items, {"plain_llm": broken}, results_dir=tmp_path / "r")
    error = out["results"]["plain_llm"]["items"][items[0]["id"]]["error"]
    assert "/home" not in error and error.endswith("'features.json'")


def test_a_manifest_lacking_a_role_raises_the_asset_error_before_begin(tmp_path):
    from tere4ai.eval import harness as h
    _write_legacy_dumps(tmp_path)
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-xyz.json").write_text(json.dumps({
        "build_id": "build-xyz", "files": {"layer1_dump": "layer1.json"}}))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-xyz"}))
    store = EvaluationRecordStore(tmp_path)
    with pytest.raises(h.EvalAssetMissingError, match="^the active publication names no norms file$"):
        run_eval(list(GOLD_3)[:1], ["plain_llm"], generator_factory=make_generator, results_dir=tmp_path / "r",
                 record_store=store, dump_dir=tmp_path)
    assert store.list_records() == []


def _keep_output_fails(monkeypatch):
    def boom(self, record_id, role, path, **kw):
        raise OSError("copy refused")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", boom)


def test_a_failing_keep_output_after_the_artifact_write_fails_the_record(tmp_path, monkeypatch):
    store = EvaluationRecordStore(tmp_path)
    _keep_output_fails(monkeypatch)
    with pytest.raises(OSError, match="copy refused"):
        run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                 results_dir=tmp_path / "r", record_store=store)
    (kept,) = list((tmp_path / "r").iterdir())
    assert kept.name.startswith("eval_"), "the compatibility file, no temp file left (G3b)"
    artifact = json.loads(kept.read_text())
    assert artifact["item_ids"] == [GOLD_3[0]["id"]] and "plain_llm" in artifact["results"], "this run's bytes"
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and "copy refused" in rec["outcome"]["error"]


def test_a_keyboard_interrupt_inside_the_strategy_loop_fails_the_record(tmp_path):
    items = list(GOLD_3)[:2]

    def interrupted(item):
        if item["id"] == items[1]["id"]:
            raise KeyboardInterrupt
        return {"answer_text": "a", "citations": []}
    store = EvaluationRecordStore(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        run_eval(items, {"plain_llm": interrupted}, results_dir=tmp_path / "r", record_store=store)
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and rec["outcome"]["error"] == "KeyboardInterrupt: "
    assert rec["ended_at"] is not None


def _publish(dump_dir, files, base="build-b"):
    """A real publication over the files as they are (G1): the manifest names their digests."""
    chain = build_chain(dump_dir / files["layer1_dump"], dump_dir / files["norms"],
                        alignments_path=dump_dir / files["alignments"] if files.get("alignments") else None)
    chain_id = chain["chain_id"]
    (dump_dir / "publications").mkdir(exist_ok=True)
    (dump_dir / "publications" / f"{chain_id}.json").write_text(json.dumps(
        {"build_id": f"{base}+chain-{chain_id}", "chain_id": chain_id, "files": files, "inputs": chain["inputs"]}))
    (dump_dir / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": chain_id}))
    return chain_id


def test_a_preloaded_dump_or_prebuilt_strategies_bind_to_no_publication(tmp_path):
    _write_legacy_dumps(tmp_path)
    chain_id = _publish(tmp_path, {"layer1_dump": "layer1.json", "norms": "norms_core.json"})
    store = EvaluationRecordStore(tmp_path)
    kw = {"generator_factory": make_generator, "results_dir": tmp_path / "r", "record_store": store,
          "dump_dir": tmp_path}
    preloaded = run_eval(list(GOLD_3)[:1], ["plain_llm"], dump=MINI_DUMP, **kw)
    prebuilt = run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                        results_dir=tmp_path / "r2", record_store=store, dump_dir=tmp_path)
    for out in (preloaded, prebuilt):
        rec = store.read(out["record_id"])
        assert rec["build"]["publication"] is None
        assert rec["build"]["publication_reason"] == "the harness did not read the served files"
    served = store.read(run_eval(list(GOLD_3)[:1], ["plain_llm"], **{**kw, "results_dir": tmp_path / "r3"})["record_id"])
    assert served["build"]["publication"]["build_id"] == f"build-b+chain-{chain_id}"


def test_a_writer_stores_its_failure_with_the_file_name_only(tmp_path, monkeypatch):
    store = EvaluationRecordStore(tmp_path)
    deep = tmp_path / "very" / "deep" / "artifact.json"

    def boom(self, record_id, role, path, **kw):
        raise FileNotFoundError(2, "No such file or directory", str(deep))
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", boom)
    with pytest.raises(FileNotFoundError):
        run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                 results_dir=tmp_path / "r", record_store=store)
    (rec,) = store.list_records()
    assert rec["outcome"]["error"] == "FileNotFoundError: [Errno 2] No such file or directory: 'artifact.json'"


def test_an_offline_run_with_graph_full_records_the_runtime_judge_prompt_hash(tmp_path):
    from tere4ai.eval import harness as h
    from tere4ai.judge.runtime_grounding import load_prompt, prompt_sha256
    _write_legacy_dumps(tmp_path)
    store = EvaluationRecordStore(tmp_path)
    kw = {"generator_factory": h.OfflineStubClient, "judge_factory": h.OfflineStubClient, "record_store": store,
          "dump_dir": tmp_path, "judge_log_path": tmp_path / "judge_log.jsonl"}
    full = run_eval(list(GOLD_3)[:1], ["plain_llm", "graph_full"], results_dir=tmp_path / "r", **kw)
    assert store.read(full["record_id"])["prompt_sha256"] == {
        "runtime_grounding": prompt_sha256(load_prompt("runtime_grounding", "v1"))}
    plain = run_eval(list(GOLD_3)[:1], ["plain_llm"], results_dir=tmp_path / "r2", **kw)
    assert store.read(plain["record_id"])["prompt_sha256"] is None


def test_the_runtime_judge_prompt_is_hashed_only_when_the_strategy_reports_its_version(tmp_path):
    # B81 item 23: the name graph_full alone is no evidence that a runtime judge was called
    from tere4ai.eval import harness as h
    from tere4ai.judge.runtime_grounding import load_prompt, prompt_sha256
    assert h.runtime_judge_prompt_sha256({"graph_full": {}}) is None
    assert h.runtime_judge_prompt_sha256({"graph_full@v2": {}}) is None
    assert h.runtime_judge_prompt_sha256({"graph_full": {"judge_prompt_version": "v1"}}) == {
        "runtime_grounding": prompt_sha256(load_prompt("runtime_grounding", "v1"))}
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(list(GOLD_3)[:1], {"graph_full": lambda item: {"answer_text": "a", "citations": []}},
                   results_dir=tmp_path / "r", record_store=store)
    assert store.read(out["record_id"])["prompt_sha256"] is None


def test_the_harness_asks_for_a_judge_when_only_graph_runtime_judge_is_requested(tmp_path):
    # B126 (ruling R2): the judge is built for every condition that calls it, not only graph_full
    with pytest.raises(ValueError, match="graph_runtime_judge was requested but no judge_factory"):
        run_eval(list(GOLD_3)[:1], ["graph_runtime_judge"], generator_factory=make_generator,
                 dump=MINI_DUMP, norms_payload=MINI_NORMS, results_dir=tmp_path / "r")
    built = []
    artifact = run_eval(list(GOLD_3)[:1], ["graph_runtime_judge"], generator_factory=make_generator,
                        judge_factory=lambda: built.append(1) or make_judge(), dump=MINI_DUMP,
                        norms_payload=MINI_NORMS, results_dir=tmp_path / "r",
                        judge_log_path=tmp_path / "judge_log.jsonl")
    assert built == [1]
    assert artifact["strategies"] == ["graph_runtime_judge"]


def test_an_offline_run_with_graph_runtime_judge_records_the_runtime_judge_prompt_hash(tmp_path):
    from tere4ai.eval import harness as h
    from tere4ai.judge.runtime_grounding import load_prompt, prompt_sha256
    expected = {"runtime_grounding": prompt_sha256(load_prompt("runtime_grounding", "v1"))}
    assert h.runtime_judge_prompt_sha256({"graph_runtime_judge": {"judge_prompt_version": "v1"}}) == expected
    assert h.runtime_judge_prompt_sha256({"graph_runtime_judge": {}}) is None
    _write_legacy_dumps(tmp_path)
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(list(GOLD_3)[:1], ["graph_runtime_judge"], generator_factory=h.OfflineStubClient,
                   judge_factory=h.OfflineStubClient, record_store=store, dump_dir=tmp_path,
                   judge_log_path=tmp_path / "judge_log.jsonl", results_dir=tmp_path / "r")
    assert store.read(out["record_id"])["prompt_sha256"] == expected


def test_a_failure_finish_refused_by_validation_still_ends_the_record_failed(tmp_path, monkeypatch):
    # B97 item 9 (Task 8): the record never stays running; B102 final review: the retry drops only the
    # client-built fields, so the items that finished and the notes survive
    from tere4ai.eval import harness as h
    from tere4ai.judge.config import ConfigurationError
    store = EvaluationRecordStore(tmp_path)
    monkeypatch.setattr(h, "_own_usage", lambda generator, judge: ["not", "an", "object"])
    items = list(GOLD_3)[:2]

    def refused(item):
        if item["id"] == items[1]["id"]:
            raise ConfigurationError("effort is not declared")
        return {"answer_text": "a", "citations": []}
    with pytest.raises(ConfigurationError):
        run_eval(items, {"plain_llm": refused}, results_dir=tmp_path / "r", record_store=store)
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and rec["ended_at"]
    assert rec["outcome"]["error"].startswith("ConfigurationError: effort is not declared; the full failure record "
                                              "was refused: refusing to finish: ")
    assert "at usage" in rec["outcome"]["error"] and rec["usage"] is None
    assert rec["outcome"]["completed_items"] == [items[0]["id"]]
    assert rec["notes"] == ["the strategies were passed prebuilt; the harness did not read their inputs"]


@pytest.mark.parametrize("refusals", [2, 3])
def test_a_finish_refused_again_never_replaces_the_runs_own_error(tmp_path, monkeypatch, capsys, refusals):
    # B102 final review: refused twice, the record ends failed with the error alone; refused three times,
    # it stays as it is, one stderr line names it, and the caller still raises the run's own error
    from tere4ai.eval.evaluation_record import EvaluationRecordError
    from tere4ai.judge.config import ConfigurationError
    store = EvaluationRecordStore(tmp_path)
    real_finish, calls = store.finish, []

    def finish(record_id, **fields):
        calls.append(fields)
        if len(calls) <= refusals:
            raise EvaluationRecordError("refusing to finish: a test refusal")
        return real_finish(record_id, **fields)
    monkeypatch.setattr(store, "finish", finish)

    def refused(item):
        raise ConfigurationError("effort is not declared")
    with pytest.raises(ConfigurationError, match="effort is not declared"):
        run_eval(list(GOLD_3)[:1], {"plain_llm": refused}, results_dir=tmp_path / "r", record_store=store)
    (rec,) = store.list_records()
    assert len(calls) == 3 and set(calls[2]) == {"status", "error"}
    if refusals == 2:
        assert rec["outcome"]["status"] == "failed" and rec["ended_at"]
        assert rec["outcome"]["error"].startswith("ConfigurationError: effort is not declared; the full failure "
                                                  "record was refused: refusing to finish: a test refusal")
    else:
        assert rec["outcome"]["status"] == "running" and rec["ended_at"] is None
        assert (f"evaluation record {rec['record_id']} could not be ended: refusing to finish: a test refusal"
                in capsys.readouterr().err)


def test_the_record_keeps_this_runs_artifact_bytes_under_the_compatibility_name(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                   results_dir=tmp_path / "r", record_store=store)
    out_path = Path(out["artifact_path"])
    (ref,) = store.read(out["record_id"])["outputs"]
    assert ref["role"] == "artifact" and ref["file"] == out_path.name
    assert ref["sha256"] == sha256_of_file(store.dir / ref["copy"]) == sha256_of_file(out_path)
    assert [p.name for p in (tmp_path / "r").iterdir()] == [out_path.name], "no temp file left"


def test_a_failed_final_move_names_the_temp_file_that_holds_the_results(tmp_path, monkeypatch):
    # B81 item 35: the temp file is the only copy of the results when the move fails; it is kept and named,
    # by its full path in the raised error (the operator's terminal) and by its file name in the record
    import os
    store = EvaluationRecordStore(tmp_path)
    results_dir = tmp_path / "r"
    real_replace = os.replace

    def failing(src, dst):
        if Path(dst).parent == results_dir:
            raise OSError(18, "Invalid cross-device link", str(src))
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", failing)
    with pytest.raises(OSError) as raised:
        run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                 results_dir=results_dir, record_store=store)
    (tmp,) = results_dir.iterdir()
    assert f"the results stay in {tmp}; move it to " in str(raised.value)
    assert tmp.name.startswith("tmp") and json.loads(tmp.read_text())["item_ids"] == [GOLD_3[0]["id"]]
    (rec,) = store.list_records()
    out_name = results_artifact_name("unknown-build", ["plain_llm"])
    assert rec["outcome"]["status"] == "failed"
    assert f"the results stay in {tmp.name}; move it to {out_name}" in rec["outcome"]["error"]
    assert str(tmp_path) not in rec["outcome"]["error"]


def test_a_concurrent_writer_replacing_the_shared_path_never_lands_in_this_record(tmp_path, monkeypatch):
    store = EvaluationRecordStore(tmp_path)
    real_keep = EvaluationRecordStore.keep_output
    other = b'{"another run": true}\n'

    def interleaved(self, record_id, role, path, **kw):
        # run B replaces the shared deterministic path between A's write and A's copy
        for p in (tmp_path / "r").glob("eval_*.json"):
            p.write_bytes(other)
        (tmp_path / "r" / kw.get("name", "x")).write_bytes(other)
        return real_keep(self, record_id, role, path, **kw)
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", interleaved)
    out = run_eval(list(GOLD_3)[:1], {"plain_llm": lambda item: {"answer_text": "a", "citations": []}},
                   results_dir=tmp_path / "r", record_store=store)
    (ref,) = store.read(out["record_id"])["outputs"]
    kept = json.loads((store.dir / ref["copy"]).read_bytes())
    assert kept["item_ids"] == out["item_ids"] and kept["results"] == out["results"], "this run's bytes"
    assert Path(out["artifact_path"]).read_bytes() == (store.dir / ref["copy"]).read_bytes()


def test_an_interrupted_harness_run_keeps_the_completed_items_and_the_spend(tmp_path, monkeypatch):
    """B81 item 4, harness side."""
    from tere4ai.eval import harness as h

    items = list(GOLD_3)[:2]

    class Counting:
        model = "fake-generator"

        def __init__(self):
            self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "requests_sent": 0,
                          "replies_with_usage": 0}

        def complete(self, system, user):
            self.usage["requests_sent"] += 1
            if self.usage["calls"] == 1:
                raise KeyboardInterrupt
            self.usage["calls"] += 1
            return "{}"

    def fake_build(name, generator, dump, norms_payload, judge=None, judge_log_path=None):
        def strategy(item):
            generator.complete("s", item["id"])
            return {"answer_text": "a", "citations": [], "risk_category": "high"}
        return strategy

    monkeypatch.setattr(h, "build_strategy", fake_build)
    store = EvaluationRecordStore(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        run_eval(items, ["plain_llm"], generator_factory=Counting, dump=MINI_DUMP, norms_payload=MINI_NORMS,
                 results_dir=tmp_path / "r", record_store=store)
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and rec["outcome"]["completed_items"] == [items[0]["id"]]
    assert rec["usage"]["generator"] == {"calls": 1, "input_tokens": 0, "output_tokens": 0, "requests_sent": 2,
                                         "replies_with_usage": 0}
    assert rec["usage"]["judge"] is None


# Codex review of 73b8baa..782f26a: the models are read after the replies ------


class _EffortJudge(FakeClient):
    """A judge that, like the real clients, knows its effort only once it has
    answered; its nth call can be made to raise an interrupt."""

    def __init__(self, interrupt_on_call=None):
        super().__init__(
            {"Generated runtime answer under review": json.dumps(
                {"verdict": "accepted", "scores": {}, "rationale": "scripted verdict"})},
            model="fake-judge")
        self._interrupt_on_call = interrupt_on_call

    @property
    def effort(self):
        return "high" if self.calls else "no replies"

    def complete(self, system, user):
        if self._interrupt_on_call is not None and len(self.calls) + 1 == self._interrupt_on_call:
            raise KeyboardInterrupt
        return super().complete(system, user)


def _graph_full(tmp_path, judge):
    return {"graph_full": build_strategy("graph_full", make_generator(), MINI_DUMP, MINI_NORMS, judge=judge,
                                         judge_log_path=tmp_path / "judge_log.jsonl")}


def _live_without_network(monkeypatch):
    """The live path's two guards replaced; the strategies are prebuilt over fakes, so nothing is called."""
    import tere4ai.eval.harness as h
    monkeypatch.setattr(h, "_require_live_gate", lambda: None)
    monkeypatch.setattr(h, "guard_live_config",
                        lambda config_path=None: types.SimpleNamespace(as_public_dict=lambda: {"mode": "live"}))


def test_the_artifact_records_the_judge_effort_the_replies_were_produced_under(tmp_path):
    judge = _EffortJudge()
    artifact = run_eval(GOLD_3, _graph_full(tmp_path, judge), dump=MINI_DUMP, results_dir=tmp_path / "r")
    assert judge.calls, "the judge answered at least once"
    assert artifact["results"]["graph_full"]["models"]["judge_effort"] == "high"
    on_disk = json.loads(Path(artifact["artifact_path"]).read_text())
    assert on_disk["results"]["graph_full"]["models"]["judge_effort"] == "high"


def test_a_live_record_names_the_judge_effort_after_the_replies_completed_or_failed(tmp_path, monkeypatch):
    _live_without_network(monkeypatch)
    store = EvaluationRecordStore(tmp_path)
    out = run_eval(GOLD_3, _graph_full(tmp_path, _EffortJudge()), live=True, dump=MINI_DUMP,
                   results_dir=tmp_path / "r", record_store=store)
    assert store.read(out["record_id"])["models"]["graph_full"]["judge_effort"] == "high"
    with pytest.raises(KeyboardInterrupt):
        run_eval(GOLD_3, _graph_full(tmp_path, _EffortJudge(interrupt_on_call=2)), live=True, dump=MINI_DUMP,
                 results_dir=tmp_path / "r2", record_store=store)
    (failed,) = [r for r in store.list_records() if r["outcome"]["status"] == "failed"]
    assert failed["models"]["graph_full"]["judge_effort"] == "high", "a failed run records what it saw"


def test_a_refused_declared_parameter_ends_the_harness_record_failed_after_one_item(tmp_path):
    """B99 (spec F D-F29): a declared parameter the provider refuses stops the
    run; the per-item handler never records it as an item error and the
    request is never sent again for the next item."""
    from tere4ai.judge.config import DeclaredParameterRefused

    items = list(GOLD_3)[:2]
    seen: list[str] = []

    def refused(item):
        seen.append(item["id"])
        raise DeclaredParameterRefused("openai", "g", "effort", "xhigh", "HTTP 400: effort unsupported")
    store = EvaluationRecordStore(tmp_path)
    with pytest.raises(DeclaredParameterRefused):
        run_eval(items, {"plain_llm": refused}, results_dir=tmp_path / "r", record_store=store)
    assert seen == [items[0]["id"]]
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and rec["outcome"]["completed_items"] == []
    assert rec["outcome"]["error"].startswith(
        "DeclaredParameterRefused: configuration error: openai:g refused the declared effort xhigh (HTTP 400: ")


class _DeclaredGenerator:
    """A generator double reporting declared values, as the real clients do since B99."""

    sampling, temperature, effort, json_mode = "0", "0", "N/A", "sent"
    model = "stub-generator"

    def complete(self, system, user):
        return "{}"


def test_a_generator_only_live_record_leaves_the_judge_sampling_null(tmp_path, monkeypatch):
    """B99 (spec F D-F29), Task 5 review: a live run without graph_full builds
    no judge, so the judge-role sampling keys are null, as before B99, in the
    completed and the failed finish alike."""
    import tere4ai.eval.harness as h
    from tere4ai.judge.config import DeclaredParameterRefused

    _live_without_network(monkeypatch)
    refuse = {"on": False}

    def fake_build(name, generator, dump, norms_payload, judge=None, judge_log_path=None):
        def strategy(item):
            if refuse["on"]:
                raise DeclaredParameterRefused("openai", "g", "effort", "xhigh", "HTTP 400: effort unsupported")
            return {"answer_text": "a", "citations": [], "risk_category": "high"}
        return strategy

    monkeypatch.setattr(h, "build_strategy", fake_build)
    store = EvaluationRecordStore(tmp_path)
    kw = {"generator_factory": _DeclaredGenerator, "live": True, "dump": MINI_DUMP, "norms_payload": MINI_NORMS,
          "record_store": store}
    out = run_eval(list(GOLD_3)[:1], ["plain_llm"], results_dir=tmp_path / "r", **kw)
    expected = {"generator": "0", "judge": None, "generator_temperature": "0", "judge_temperature": None,
                "generator_effort": "N/A", "judge_effort": None, "generator_json_mode": "sent"}
    assert store.read(out["record_id"])["sampling"] == expected
    refuse["on"] = True
    with pytest.raises(DeclaredParameterRefused):
        run_eval(list(GOLD_3)[:1], ["plain_llm"], results_dir=tmp_path / "r2", **kw)
    (failed,) = [r for r in store.list_records() if r["outcome"]["status"] == "failed"]
    assert failed["sampling"] == expected


def test_current_level_maps_old_values_and_passes_new_ones():
    from tere4ai.eval.harness import current_level

    assert current_level("transparency_only") == "limited_risk"
    assert current_level("prohibited") == "unacceptable_risk"
    assert current_level("limited_risk") == "limited_risk"
    assert current_level(None) is None
    assert current_level("uncertain") == "undetermined"
    assert current_level("minimal_or_none") == "minimal_risk"


def test_benchmark_map_uses_the_pyramid_names():
    from tere4ai.eval.harness import BENCHMARK_RISK_MAP

    assert BENCHMARK_RISK_MAP == {
        "prohibited": "unacceptable_risk",
        "high-risk": "high_risk",
        "limited": "limited_risk",
        "minimal": "minimal_risk",
    }


def test_a_run_refuses_a_test_set_item_on_a_deleted_unit(tmp_path):
    """B132 (D-G68 (3)): the answer key is corrected, never run on a unit the
    Omnibus deleted; the refusal comes before any strategy runs."""
    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    item = {"id": "gold:x", "kind": "retrieval", "question": "q", "gold": {"node_id": "eu-ai-act:article-10:paragraph-5"},
            "gold_citations": ["eu-ai-act:article-10:paragraph-5"]}
    ran = []
    with pytest.raises(ValueError, match="cites a unit the Omnibus deleted"):
        run_eval([item], {"s": lambda i: ran.append(i) or {}}, dump=dump, results_dir=tmp_path)
    assert ran == []
