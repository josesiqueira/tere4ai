"""Regression tests for the extraction CLI (the lost-run bug of 2026-07-08)."""

import json

import pytest

from tere4ai.extract_norms.__main__ import _slug
from tere4ai.graph_store.build_record import BuildRecordStore


def test_slug_never_exceeds_filename_limits():
    core = [f"eu-ai-act:article-{n}" for n in [3, 5, 6, 7] + list(range(8, 28)) + [50, 72, 73]]
    core += ["eu-ai-act:annex-iii", "eu-ai-act:annex-iv"]
    slug = _slug(core)
    assert len(f"norms_{slug}.json") < 100, slug
    # stable across calls (hash-based, not order of a set)
    assert slug == _slug(core)
    # distinct node lists give distinct slugs
    assert slug != _slug(core[:-1])


def test_slug_readable_for_small_runs():
    assert _slug(["eu-ai-act:article-9"]).startswith("article-9")


def _fakes(monkeypatch, cli, calls, results=None):
    def fake_extract(dump, node_ids, generator, judge, prompt_version="v1"):
        calls.append(node_ids[0])
        if results is not None and node_ids[0] in results:
            return results[node_ids[0]]
        return {"norms": [{"norm_id": f"norm:{node_ids[0]}:n1"}], "judge_runs": [],
                "stats": {"source_units": 1, "candidates": 1, "verdicts": {"accepted": 1},
                          "nodes_failed": [], "invalid_norms": []}}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j"}

    class FakeClient:
        sampling = "provider default (rejected by the model)"
        usage = {"calls": 2, "input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr(cli, "extract_norms", fake_extract)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg: FakeClient())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg: FakeClient())
    monkeypatch.setattr(cli, "load_prompt", lambda kind, version: f"{kind}-{version}")


def _dump(tmp_path):
    p = tmp_path / "layer1.json"
    p.write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    return p


def test_checkpoint_resume_skips_done_groups(tmp_path, monkeypatch):
    """Resume completes group 2 without re-calling models for group 1, inheriting its result once."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    # a prior attempt on this record wrote group A under its own run id
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "build-b", None)
    prev = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[],
                                 inputs=[{"role": "layer1_dump", "file": "layer1.json", "sha256": cli.sha256_of_file(dump_path)}],
                                 config={"prompt_version": "v1", "nodes": ["eu-ai-act:article-9", "eu-ai-act:article-10"]},
                                 expected_total=2, work_unit="groups", checkpoint_file="norms_test.checkpoint.jsonl")
    ckpt = out.with_suffix(".checkpoint.jsonl")
    ckpt.write_text(json.dumps({"run_id": prev, "group": "eu-ai-act:article-9", "result": {
        "norms": [{"norm_id": "norm:eu-ai-act:article-9:n1"}], "judge_runs": [],
        "stats": {"source_units": 1, "candidates": 1, "verdicts": {"accepted": 1}, "nodes_failed": [], "invalid_norms": []},
    }}) + "\n")
    rc = cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out), "--resume"])
    assert rc == 0 and calls == ["eu-ai-act:article-10"]
    payload = json.loads(out.read_text())
    assert {n["norm_id"] for n in payload["norms"]} == {"norm:eu-ai-act:article-9:n1", "norm:eu-ai-act:article-10:n1"}
    assert payload["stats"]["source_units"] == 2 and not ckpt.exists()
    ex = store.read(rid)["executions"][1]
    assert ex["resumes_run_id"] == prev and ex["inherited_from"] == prev
    assert ex["inherited_keys"] == ["eu-ai-act:article-9"] and ex["completed_keys"] == ["eu-ai-act:article-10"]


def test_extract_writes_execution_record_and_run_id_on_checkpoint_lines(tmp_path, monkeypatch):
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    seen: list[dict] = []
    inner = cli.extract_norms

    def spy(dump, node_ids, generator, judge, prompt_version="v1"):
        ck = out.with_suffix(".checkpoint.jsonl")
        if ck.is_file():
            seen.extend(json.loads(line) for line in ck.read_text().splitlines())
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", spy)
    rc = cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)])
    assert rc == 0 and seen and all("run_id" in line for line in seen)
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][0]
    assert ex["command"] == "extract_norms" and ex["covers_steps"] == ["L2.1", "L2.2"] and ex["status"] == "done"
    assert ex["expected_total"] == 2 and ex["work_unit"] == "groups" and ex["checkpoint_file"] == "norms_test.checkpoint.jsonl"
    assert ex["completed_keys"] == ["eu-ai-act:article-9", "eu-ai-act:article-10"] and ex["inherited_keys"] == []
    assert ex["models"] == {"generator_model": "g", "judge_model": "j"} and set(ex["prompt_sha256"]) == {"generator", "judge"}
    assert ex["sampling"]["generator"].startswith("provider default") and ex["usage"]["judge"]["calls"] == 2
    assert ex["counts"]["candidates"] == 2 and ex["work_failures"] == {"nodes_failed": 0, "norms_failed": 0}
    assert ex["outputs"][0]["file"] == "norms_test.json" and seen[0]["run_id"] == ex["run_id"]


def test_extract_refuses_stale_or_incompatible_checkpoint_with_exit_2(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"group": "x", "result": {"norms": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)]) == 2
    assert "--resume" in capsys.readouterr().err and calls == []
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out), "--resume"]) == 2
    assert "accept-legacy" in capsys.readouterr().err and calls == []
    rc = cli.main(["--nodes", "eu-ai-act:article-9,x", "--dump", str(dump_path), "--out", str(out), "--resume",
                   "--accept-legacy-checkpoint"])
    assert rc == 0 and calls == ["eu-ai-act:article-9"], "the legacy group x is inherited, only article-9 runs"
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][-1]
    assert ex["inherited_from"] == "legacy" and ex["inherited_keys"] == ["x"]


def test_extract_on_a_published_record_continues_as_descendant(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    _fakes(monkeypatch, cli, [])
    store = BuildRecordStore(tmp_path)
    old = store.create_record("test", "build-b", None)
    store.set_publication(old, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                               "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                               "postload_gates": [], "manifests": []})
    rc = cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)])
    assert rc == 0 and "descendant" in capsys.readouterr().out
    new = store.resolve("test")
    assert new != old and store.read(new)["parent_record_id"] == old and store.read(old)["executions"] == []


def test_extract_failure_records_usage_and_keeps_checkpoint(tmp_path, monkeypatch):
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms

    def boom(dump, node_ids, generator, judge, prompt_version="v1"):
        if node_ids[0] == "eu-ai-act:article-10":
            raise RuntimeError("usage limit reached")
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", boom)
    with pytest.raises(RuntimeError):
        cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)])
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][0]
    assert ex["status"] == "failed" and "usage limit" in ex["error"]
    assert ex["completed_keys"] == ["eu-ai-act:article-9"] and ex["usage"]["generator"]["calls"] == 2
    assert out.with_suffix(".checkpoint.jsonl").is_file(), "the checkpoint stays for resume"


PUBLISHED = {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
             "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [], "postload_gates": [],
             "manifests": []}


def test_extract_never_overwrites_an_artefact_a_published_build_names(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    dumps = tmp_path / "data" / "graph_dumps"
    dumps.mkdir(parents=True)
    slug = cli._slug(["eu-ai-act:article-9"])
    out = dumps / f"norms_{slug}.json"
    out.write_text('{"norms": ["published"]}')
    before = out.read_bytes()
    store = BuildRecordStore(dumps)
    rid = store.create_record(slug, "build-b", None)
    run = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[],
                                config={}, expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=[{"role": "norms", "file": out.name, "sha256": cli.sha256_of_file(out)}])
    store.set_publication(rid, PUBLISHED)
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path)]) == 1
    err = capsys.readouterr().err
    assert f"record {rid}" in err and "--out" in err and calls == [] and out.read_bytes() == before
    assert [r["record_id"] for r in store.list_records()] == [rid], "refused before any record is created"

    # (a) the record continues as a descendant and the file exists, whoever wrote it
    out.write_text('{"norms": ["edited by hand"]}')
    before = out.read_bytes()
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path)]) == 1
    assert "descendant" in capsys.readouterr().err and calls == [] and out.read_bytes() == before
