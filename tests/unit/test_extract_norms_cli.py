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
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"}

    class FakeClient:
        sampling = "provider default (rejected by the model)"
        temperature = "provider default (rejected by the model)"
        effort = "xhigh"
        json_mode = "sent"
        usage = {"calls": 2, "input_tokens": 10, "output_tokens": 5, "requests_sent": 3,
                 "replies_with_usage": 2}

    monkeypatch.setattr(cli, "extract_norms", fake_extract)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    # B99 (spec F D-F30): the command chooses the terminal policy
    policies: list = []
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or FakeClient())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or FakeClient())
    monkeypatch.setattr(cli, "_TEST_POLICIES", policies, raising=False)
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
                                 config={"prompt_version": "v2", "nodes": ["eu-ai-act:article-9", "eu-ai-act:article-10"]},
                                 expected_total=2, work_unit="groups", checkpoint_file="norms_test.checkpoint.jsonl",
                                 models={"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"},
                                 prompt_sha256={"generator": cli.prompt_sha256("extract_norms-v2"),
                                                "judge": cli.prompt_sha256("judge_norms-v2")})
    # Changed by final review A1: a resume is refused while the run it resumes
    # is live, so the prior attempt ends failed here as an interrupted run does.
    store.finish_execution(rid, prev, status="failed", error="KeyboardInterrupt: ")
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
    # B84: the record carries the efforts (models requested, sampling applied), so the assertions are exact dicts now
    assert ex["models"] == {"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"}
    # B99 (spec F D-F29): the declared temperature under <role>_temperature and the declared JSON mode are recorded too
    assert ex["sampling"] == {"generator": "provider default (rejected by the model)", "judge": "provider default (rejected by the model)",
                              "generator_temperature": "provider default (rejected by the model)",
                              "judge_temperature": "provider default (rejected by the model)",
                              "generator_effort": "xhigh", "judge_effort": "xhigh", "generator_json_mode": "sent"}
    assert ex["usage"]["judge"]["calls"] == 2
    # B91: the two counts reach the record and the manifest through the same clients
    assert ex["usage"]["generator"]["requests_sent"] == 3 and ex["usage"]["generator"]["replies_with_usage"] == 2
    payload = json.loads(out.read_text())
    assert payload["build"]["extraction_usage"]["judge"]["requests_sent"] == 3
    assert payload["build"]["extraction_effort"] == {"generator": "xhigh", "judge": "xhigh"}
    assert payload["build"]["extraction_models"]["judge_effort"] == "xhigh"
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
    _assert_no_record(tmp_path)  # B79 item 10: a refused run leaves no record and no alias
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out), "--resume"]) == 2
    assert "accept-legacy" in capsys.readouterr().err and calls == []
    _assert_no_record(tmp_path)
    rc = cli.main(["--nodes", "eu-ai-act:article-9,x", "--dump", str(dump_path), "--out", str(out), "--resume",
                   "--accept-legacy-checkpoint"])
    assert rc == 0 and calls == ["eu-ai-act:article-9"], "the legacy group x is inherited, only article-9 runs"
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][-1]
    assert ex["inherited_from"] == "legacy" and ex["inherited_keys"] == ["x"]


def _assert_no_record(tmp_path):
    assert BuildRecordStore(tmp_path).list_records() == []
    aliases = tmp_path / "build_records" / "aliases.json"
    assert not aliases.is_file() or "test" not in json.loads(aliases.read_text(encoding="utf-8"))


def _first_execution(tmp_path):
    store = BuildRecordStore(tmp_path)
    return store.read(store.resolve("test"))["executions"][0]


def test_a_refusal_over_a_published_record_creates_no_descendant(tmp_path, monkeypatch, capsys):
    """B79 item 10: the stale checkpoint is refused before the descendant is made."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    store = BuildRecordStore(tmp_path)
    old = store.create_record("test", "build-b", None)
    store.set_publication(old, PUBLISHED)
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"group": "x", "result": {"norms": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)]) == 2
    assert "--resume" in capsys.readouterr().err and calls == []
    assert [r["record_id"] for r in store.list_records()] == [old] and store.resolve("test") == old


def test_a_client_that_fails_to_build_leaves_no_record(tmp_path, monkeypatch):
    """B79 item 10: the record is created only after the model clients are built."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)

    def no_client(cfg, **kw):
        raise RuntimeError("the judge client could not be built")

    monkeypatch.setattr(cli, "AnthropicJudge", no_client)
    with pytest.raises(RuntimeError, match="could not be built"):
        cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)])
    assert calls == []
    _assert_no_record(tmp_path)


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


def test_ctrl_c_ends_the_execution_failed_with_the_spend_so_far(tmp_path, monkeypatch):
    """B79 item 22: a KeyboardInterrupt is not an Exception; the record must still end."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms

    def interrupted(dump, node_ids, generator, judge, prompt_version="v1"):
        if node_ids[0] == "eu-ai-act:article-10":
            raise KeyboardInterrupt
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)])
    ex = _first_execution(tmp_path)
    assert ex["status"] == "failed" and ex["error"] == "KeyboardInterrupt: " and ex["ended_at"]
    assert ex["completed_keys"] == ["eu-ai-act:article-9"] and ex["usage"]["generator"]["calls"] == 2
    # review fix F2: the failed attempt records what the clients applied, not the start value
    # B99 (spec F D-F29): the declared temperature under <role>_temperature and the declared JSON mode are recorded too
    assert ex["sampling"] == {"generator": "provider default (rejected by the model)",
                              "judge": "provider default (rejected by the model)",
                              "generator_temperature": "provider default (rejected by the model)",
                              "judge_temperature": "provider default (rejected by the model)",
                              "generator_effort": "xhigh", "judge_effort": "xhigh", "generator_json_mode": "sent"}
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
    assert [r["record_id"] for r in store.list_records()] == [rid], "B79 item 10: refused before the descendant is made"


def test_a_long_group_keeps_the_execution_live(tmp_path, monkeypatch):
    """B79 item 4: a group longer than the expiry must not read liveness unknown."""
    import time

    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.graph_store import build_record

    monkeypatch.setattr(build_record, "HEARTBEAT_INTERVAL_SECONDS", 0.05)
    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms
    beats: list[str] = []

    def slow(dump, node_ids, generator, judge, prompt_version="v1"):
        store = BuildRecordStore(tmp_path)
        rid = store.resolve("test")
        beats.append(store.read(rid)["executions"][0]["heartbeat_at"])
        time.sleep(0.3)
        beats.append(store.read(rid)["executions"][0]["heartbeat_at"])
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", slow)
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)]) == 0
    assert beats[1] > beats[0], "the heartbeat advanced inside one group"


def test_a_run_whose_record_is_published_under_it_stops_and_says_so(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.graph_store.build_record import FrozenRecordError

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms

    def published_meanwhile(dump, node_ids, generator, judge, prompt_version="v1"):
        store = BuildRecordStore(tmp_path)
        rid = store.resolve("test")
        record = json.loads((store.dir / f"{rid}.json").read_text())
        record["publication"] = PUBLISHED  # written by hand: the live check would refuse a real publish
        (store.dir / f"{rid}.json").write_text(json.dumps(record))
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", published_meanwhile)
    with pytest.raises(FrozenRecordError):
        cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out)])
    assert "the failure could not be recorded" in capsys.readouterr().err
    assert out.with_suffix(".checkpoint.jsonl").is_file()


def test_a_resume_is_refused_while_the_first_run_of_the_record_is_live(tmp_path, monkeypatch, capsys):
    """Final review A1: two live runs of one record would both pay for every remaining group."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "build-b", None)
    first = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[],
                                  config={}, expected_total=1, work_unit="groups", checkpoint_file=None)
    rc = cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(dump_path), "--out", str(out), "--resume"])
    err = capsys.readouterr().err
    assert rc == 2 and first in err and "300 s after its last heartbeat" in err and calls == []
    assert [e["run_id"] for e in store.read(rid)["executions"]] == [first], "no second execution started"


def _guard_signals():
    """A test-side handler for SIGTERM and SIGHUP, so a missing handler in the
    command never kills the test process; returns (got, restore)."""
    import signal

    got: list[int] = []

    def guard(signum, frame):
        got.append(signum)

    before = {sig: signal.signal(sig, guard) for sig in (signal.SIGTERM, signal.SIGHUP)}

    def restore():
        for sig, handler in before.items():
            signal.signal(sig, handler)

    return got, guard, restore


def test_a_sigterm_ends_the_extract_execution_failed_with_the_spend_so_far(tmp_path, monkeypatch):
    """Final review A2 (a): a closed terminal or ssh drop (SIGHUP, SIGTERM) takes the interrupt path."""
    import os
    import signal
    import time

    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms

    def terminated(dump, node_ids, generator, judge, prompt_version="v1"):
        if node_ids[0] == "eu-ai-act:article-10":
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(1)
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", terminated)
    got, guard, restore = _guard_signals()
    try:
        with pytest.raises(KeyboardInterrupt):
            cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)])
        assert signal.getsignal(signal.SIGTERM) is guard and signal.getsignal(signal.SIGHUP) is guard
    finally:
        restore()
    assert got == []
    ex = _first_execution(tmp_path)
    assert ex["status"] == "failed" and "SIGTERM" in ex["error"] and ex["usage"]["generator"]["calls"] == 2
    assert ex["sampling"]["generator_effort"] == "xhigh"


def test_each_finished_group_writes_the_usage_so_far_into_the_running_execution(tmp_path, monkeypatch):
    """Final review A2 (b): after a SIGKILL the record still holds the spend up to the last finished group."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms
    seen: list[dict] = []

    def look(dump, node_ids, generator, judge, prompt_version="v1"):
        if node_ids[0] == "eu-ai-act:article-10":
            store = BuildRecordStore(tmp_path)
            seen.append(store.read(store.resolve("test"))["executions"][0])
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", look)
    assert cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)]) == 0
    assert seen[0]["status"] == "running" and seen[0]["usage"]["generator"]["calls"] == 2
    assert seen[0]["usage"]["judge"]["requests_sent"] == 3


# B99 (spec F D-F30): a provider stop ends the execution failed with its reason,
# keeps the checkpoint and names the resume; spec F D-F29: a refused
# declaration stops the run the same way.


def test_the_command_builds_both_clients_with_the_terminal_policy(tmp_path, monkeypatch):
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.extract_norms.model_clients import TERMINAL_POLICY

    _fakes(monkeypatch, cli, [])
    out = tmp_path / "norms_test.json"
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(_dump(tmp_path)), "--out", str(out)]) == 0
    assert cli._TEST_POLICIES == [TERMINAL_POLICY, TERMINAL_POLICY]


def test_a_provider_stop_is_recorded_keeps_the_checkpoint_prints_the_resume_and_resumes(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.extract_norms.model_clients import ProviderUnavailable

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"
    calls: list[str] = []
    _fakes(monkeypatch, cli, calls)
    inner = cli.extract_norms

    def stop_on_the_second_group(dump, node_ids, generator, judge, prompt_version="v1"):
        if node_ids[0] == "eu-ai-act:article-10":
            raise ProviderUnavailable(6, "HTTP 529")
        return inner(dump, node_ids, generator, judge, prompt_version)

    monkeypatch.setattr(cli, "extract_norms", stop_on_the_second_group)
    argv = ["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)]
    assert cli.main(argv) == 3
    store = BuildRecordStore(tmp_path)
    (ex,) = store.read(store.resolve("test"))["executions"]
    assert ex["status"] == "failed" and ex["error"] == "provider unavailable after 6 attempts: HTTP 529"
    assert ex["completed_keys"] == ["eu-ai-act:article-9"]
    assert ex["sampling"]["generator_json_mode"] == "sent"
    # review X-C1: the dashboard reads the declared temperature under <role>_temperature
    assert ex["sampling"]["generator_temperature"] == ex["sampling"]["generator"]
    assert ex["sampling"]["judge_temperature"] == ex["sampling"]["judge"]
    ckpt = out.with_suffix(".checkpoint.jsonl")
    assert [json.loads(line)["group"] for line in ckpt.read_text().splitlines()] == ["eu-ai-act:article-9"]
    err = capsys.readouterr().err
    assert "stopped: provider unavailable after 6 attempts: HTTP 529" in err
    assert f"the checkpoint {ckpt.name} is kept (1 of 2 groups done); continue with:" in err
    assert (f"  .venv/bin/python -m tere4ai.extract_norms --nodes eu-ai-act:article-9,eu-ai-act:article-10 "
            f"--dump {dump_path} --out {out} --resume") in err
    monkeypatch.setattr(cli, "extract_norms", inner)
    assert cli.main([*argv, "--resume"]) == 0 and calls == ["eu-ai-act:article-9", "eu-ai-act:article-10"]


def test_a_refused_declaration_is_recorded_and_exits_4(tmp_path, monkeypatch, capsys):
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.judge.config import DeclaredParameterRefused

    out = tmp_path / "norms_test.json"
    _fakes(monkeypatch, cli, [])

    def refused(dump, node_ids, generator, judge, prompt_version="v1"):
        raise DeclaredParameterRefused("openai", "g", "temperature", "0", "HTTP 400: temperature unsupported")

    monkeypatch.setattr(cli, "extract_norms", refused)
    assert cli.main(["--nodes", "eu-ai-act:article-9", "--dump", str(_dump(tmp_path)), "--out", str(out)]) == 4
    store = BuildRecordStore(tmp_path)
    (ex,) = store.read(store.resolve("test"))["executions"]
    assert ex["status"] == "failed"
    assert ex["error"] == ("configuration error: openai:g refused the declared temperature 0 "
                           "(HTTP 400: temperature unsupported); correct its row in config/model_parameters.json")
    assert "stopped: configuration error: openai:g refused" in capsys.readouterr().err


def test_the_groups_untyped_in_scope_counts_are_summed_into_the_payload_and_the_record(tmp_path, monkeypatch):
    """B65 ruling 54 (DEC-19): the per-group count of in-scope norms without a
    requirement type survives the merge, which sums a fixed key list."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"

    def group(node_id, untyped):
        return {"norms": [{"norm_id": f"norm:{node_id}:n1"}], "judge_runs": [],
                "stats": {"source_units": 1, "candidates": 1, "verdicts": {"accepted": 1},
                          "nodes_failed": [], "invalid_norms": [], "untyped_in_scope": untyped}}

    _fakes(monkeypatch, cli, [], results={"eu-ai-act:article-9": group("eu-ai-act:article-9", 2),
                                          "eu-ai-act:article-10": group("eu-ai-act:article-10", 1)})
    rc = cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump_path), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text())["stats"]["untyped_in_scope"] == 3
    store = BuildRecordStore(tmp_path)
    assert store.read(store.resolve("test"))["executions"][0]["counts"]["untyped_in_scope"] == 3


def test_the_groups_counts_of_norms_without_a_category_are_summed_into_the_payload_and_the_record(
    tmp_path, monkeypatch, capsys
):
    """B124 (DEC-21, spec G D-G62): the count of norms on a unit outside the
    rule table survives the merge, which sums a fixed key list; a group
    written before B124 carries no count and adds nothing (review focus 3)."""
    import tere4ai.extract_norms.__main__ as cli

    dump_path = _dump(tmp_path)
    out = tmp_path / "norms_test.json"

    def group(node_id, without):
        return {"norms": [{"norm_id": f"norm:{node_id}:n1"}], "judge_runs": [],
                "stats": {"source_units": 1, "candidates": 1, "verdicts": {"accepted": 1},
                          "nodes_failed": [], "invalid_norms": [], "without_target_system_category": without}}

    # article-10 takes _fakes' default result, whose stats carry no count
    _fakes(monkeypatch, cli, [], results={"eu-ai-act:article-9": group("eu-ai-act:article-9", 0),
                                          "eu-ai-act:article-99": group("eu-ai-act:article-99", 2)})
    rc = cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10,eu-ai-act:article-99",
                   "--dump", str(dump_path), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text())["stats"]["without_target_system_category"] == 2
    store = BuildRecordStore(tmp_path)
    assert store.read(store.resolve("test"))["executions"][0]["counts"]["without_target_system_category"] == 2
    assert "norms without a target_system_category (source unit outside the rule table): 2" in capsys.readouterr().out
