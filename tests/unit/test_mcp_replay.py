"""C3 task 2: a paid MCP tool is not paid twice for an identical call.

Ruling R3 of the C3 plan: an identical call (same caller, tool, arguments,
served build and model parameters) inside the replay window returns the
first answer with a note and makes no model call; an identical call while
the first is running waits for it; an answer that failed is never reused.
Every test uses fake model clients that count their calls; no test makes a
paid call or reads .env.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import UTC, datetime, timedelta

import pytest

from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.mcp_server import backlog as backlog_rules
from tere4ai.mcp_server import elicit as elicit_rules
from tere4ai.mcp_server import evidence as evidence_rules
from tere4ai.mcp_server import keys, replay, server

NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
NORM = {
    "norm_id": NORM_ID,
    "layer": 2,
    "type": "NormativeStatement",
    "source_node_id": "eu-ai-act:article-9:paragraph-1",
    "source_span_id": "span:009.001",
    "source_text": "A risk management system shall be established.",
    "deontic_type": "obligation",
    "modal": "shall",
    "actor_explicit": None,
    "actor_inferred": "provider",
    "action": "establish",
    "object": "a risk management system",
    "target_system_category": "high_risk",
    "conditions": [],
    "exceptions": [],
    "judge_verdict": "accepted",
    "review_status": "accepted",
}
CONTENT = "We maintain a documented risk management system for our service."
QUOTE = "We maintain a documented risk management system"
GENERATOR_REPLY = json.dumps(
    {"assessment": "satisfied", "quotes": [QUOTE], "gaps": [], "rationale": "Quoted."}
)
SCORES = {
    "semantic_similarity": 0.9,
    "normative_relevance": 0.9,
    "operational_utility": 0.9,
    "evidence_strength": 0.8,
    "judge_confidence": 0.9,
}
JUDGE_REPLY = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded."})
NOTE_RE = re.compile(
    r"^this answer repeats the answer to an identical call made at "
    r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ); no new model call was made$"
)


class CountingClient:
    """A fake model client: counts calls; a reply may be an exception to raise.

    hold, when given, is an Event the first call waits on, so a test can keep
    the first call inside the model while a second identical call arrives.
    """

    def __init__(self, replies, model, hold=None):
        self.model = model
        self._replies = list(replies)
        self.calls = 0
        self.entered = threading.Event()
        self._hold = hold

    def complete(self, system, user):
        self.calls += 1
        self.entered.set()
        if self._hold is not None and self.calls == 1:
            assert self._hold.wait(10), "the test never released the held call"
        reply = self._replies[min(self.calls, len(self._replies)) - 1]
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _dump(build_id="build-a"):
    return {
        "build": {"build_id": build_id},
        "nodes": [{"id": NORM["source_node_id"], "text": NORM["source_text"]}],
        "edges": [],
    }


class World:
    """The server over mock data: one accepted norm, fake clients, a fresh store."""

    def __init__(self, monkeypatch, tmp_path):
        self._monkeypatch = monkeypatch
        self.now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
        self.waiting = threading.Event()
        self.store = replay.ReplayStore(
            window_seconds=600, clock=lambda: self.now, on_wait=self.waiting.set
        )
        monkeypatch.setattr(server, "_REPLAY", self.store)
        monkeypatch.setattr(evidence_rules, "DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
        self.parameters = "parameters-a"
        self.set_build("build-a")
        self.set_clients([GENERATOR_REPLY], [JUDGE_REPLY])

    def set_build(self, build_id):
        loaded = LoadedBuild(
            _dump(build_id), {"norms": [dict(NORM)]}, {"assertions": []}, build_id, "legacy", None
        )
        self._monkeypatch.setattr(server, "_active", lambda: loaded)

    def set_clients(self, generator_replies, judge_replies, hold=None):
        self.generator = CountingClient(generator_replies, "fake-generator", hold=hold)
        self.judge = CountingClient(judge_replies, "fake-judge")
        self._monkeypatch.setattr(
            server,
            "_paid_clients_or_envelope",
            lambda: server.PaidClients(self.generator, self.judge, self.parameters),
        )

    def evaluate(self, content=CONTENT):
        return server.evaluate_project_evidence(
            norm_id=NORM_ID, artifact_type="risk_management_plan", content=content
        )


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.delenv("TERE4AI_MCP_REPLAY_WINDOW_SECONDS", raising=False)
    return World(monkeypatch, tmp_path)


def _replay_note(envelope):
    notes = [n for n in envelope["legal_status_notes"] if NOTE_RE.match(n)]
    return NOTE_RE.match(notes[0]).group(1) if len(notes) == 1 else None


def test_a_repeat_within_the_window_makes_no_model_call_and_carries_the_note(world):
    first = world.evaluate()
    assert first["status"] == "satisfied_with_evidence"
    assert world.generator.calls == 1 and world.judge.calls == 1
    assert _replay_note(first) is None

    world.now += timedelta(seconds=599)
    second = world.evaluate()
    assert world.generator.calls == 1 and world.judge.calls == 1, "no second model call"
    assert _replay_note(second) == "2026-10-02T12:00:00Z", "the first call's completion time"
    assert second["answer"] == first["answer"]
    assert second["status"] == first["status"]
    assert second["legal_status_notes"][:-1] == first["legal_status_notes"]


def test_a_returned_answer_changed_by_its_caller_does_not_change_what_is_kept(world):
    first = world.evaluate()
    first["answer"]["assessment"] = "changed by the caller"
    first["legal_status_notes"].append("added by the caller")
    second = world.evaluate()
    assert second["answer"]["assessment"] == "satisfied"
    assert "added by the caller" not in second["legal_status_notes"]
    third = world.evaluate()
    assert len([n for n in third["legal_status_notes"] if NOTE_RE.match(n)]) == 1


def test_a_different_argument_pays_again(world):
    world.evaluate()
    world.evaluate(content=CONTENT + " Reviewed quarterly.")
    assert world.generator.calls == 2


def test_a_different_build_pays_again(world):
    world.evaluate()
    world.set_build("build-b")
    world.evaluate()
    assert world.generator.calls == 2


def test_different_model_parameters_pay_again(world):
    world.evaluate()
    world.parameters = "parameters-b"
    world.evaluate()
    assert world.generator.calls == 2


def test_a_different_caller_pays_again(world):
    world.evaluate()
    token = replay.CALLER.set("key0000000a")
    try:
        assert replay.current_caller() == "key0000000a"
        world.evaluate()
        assert world.generator.calls == 2
        world.evaluate()
        assert world.generator.calls == 2, "the same key repeats its own answer"
    finally:
        replay.CALLER.reset(token)
    assert replay.current_caller() == "local"


def test_the_window_expiring_pays_again(world):
    world.evaluate()
    world.now += timedelta(seconds=600)
    again = world.evaluate()
    assert world.generator.calls == 2
    assert _replay_note(again) is None


def test_the_window_comes_from_the_environment(world, monkeypatch):
    store = replay.ReplayStore(clock=lambda: world.now)
    monkeypatch.setattr(server, "_REPLAY", store)
    monkeypatch.setenv("TERE4AI_MCP_REPLAY_WINDOW_SECONDS", "30")
    world.evaluate()
    world.now += timedelta(seconds=29)
    world.evaluate()
    assert world.generator.calls == 1
    world.now += timedelta(seconds=1)
    world.evaluate()
    assert world.generator.calls == 2
    monkeypatch.delenv("TERE4AI_MCP_REPLAY_WINDOW_SECONDS")
    assert replay.window_seconds() == 600


@pytest.mark.parametrize("bad", ["ten", "-1", "", "nan", "inf"])
def test_an_unusable_window_is_refused_by_name(monkeypatch, bad):
    monkeypatch.setenv("TERE4AI_MCP_REPLAY_WINDOW_SECONDS", bad)
    with pytest.raises(ValueError, match="TERE4AI_MCP_REPLAY_WINDOW_SECONDS"):
        replay.window_seconds()


def test_a_provider_failure_is_not_kept_and_the_retry_pays(world):
    world.set_clients([RuntimeError("provider unavailable"), GENERATOR_REPLY], [JUDGE_REPLY])
    with pytest.raises(RuntimeError, match="provider unavailable"):
        world.evaluate()
    answer = world.evaluate()
    assert world.generator.calls == 2
    assert answer["status"] == "satisfied_with_evidence"
    assert _replay_note(answer) is None
    world.evaluate()
    assert world.generator.calls == 2, "the successful retry is kept"


def test_a_degraded_answer_after_the_model_call_is_not_kept(world):
    world.set_clients(["not json"], [JUDGE_REPLY])
    first = world.evaluate()
    assert first["answer"]["refused"] is True and first["judge_verdict"] == "not_run"
    calls = world.generator.calls
    world.evaluate()
    assert world.generator.calls == 2 * calls, "the retry pays again"
    assert len(world.store) == 0


def test_a_refusal_before_the_model_call_is_not_kept(world, monkeypatch):
    world.evaluate(content="   ")
    monkeypatch.setattr(
        server,
        "_paid_clients_or_envelope",
        lambda: {"answer": None, "missing_facts": ["missing model configuration"]},
    )
    world.evaluate()
    assert world.generator.calls == 0
    assert len(world.store) == 0


def test_two_concurrent_identical_calls_make_one_model_call(world):
    release = threading.Event()
    world.set_clients([GENERATOR_REPLY], [JUDGE_REPLY], hold=release)
    results = {}

    def call(name):
        results[name] = world.evaluate()

    first = threading.Thread(target=call, args=("first",))
    first.start()
    assert world.generator.entered.wait(10), "the first call reached the model"
    second = threading.Thread(target=call, args=("second",))
    second.start()
    assert world.waiting.wait(10), "the second call waits for the first"
    release.set()
    first.join(10)
    second.join(10)
    assert not first.is_alive() and not second.is_alive()
    assert world.generator.calls == 1 and world.judge.calls == 1
    assert _replay_note(results["first"]) is None
    assert _replay_note(results["second"]) == "2026-10-02T12:00:00Z"
    assert results["second"]["answer"] == results["first"]["answer"]


def test_a_waiting_call_pays_itself_when_the_first_fails(world):
    release = threading.Event()
    world.set_clients(
        [RuntimeError("provider unavailable"), GENERATOR_REPLY], [JUDGE_REPLY], hold=release
    )
    results = {}

    def call(name):
        try:
            results[name] = world.evaluate()
        except RuntimeError as exc:
            results[name] = exc

    first = threading.Thread(target=call, args=("first",))
    first.start()
    assert world.generator.entered.wait(10)
    second = threading.Thread(target=call, args=("second",))
    second.start()
    assert world.waiting.wait(10)
    release.set()
    first.join(10)
    second.join(10)
    assert isinstance(results["first"], RuntimeError)
    assert results["second"]["status"] == "satisfied_with_evidence"
    assert _replay_note(results["second"]) is None
    assert world.generator.calls == 2


def test_the_store_keeps_at_most_256_answers_oldest_dropped():
    store = replay.ReplayStore(window_seconds=600)
    calls = []

    def answer(i):
        def compute():
            calls.append(i)
            return {"answer": {"i": i}, "judge_verdict": "accepted", "legal_status_notes": []}

        return compute

    for i in range(257):
        store.run(
            tool="t", arguments={"i": i}, build="b", model_parameters_sha256="p",
            compute=answer(i),
        )
    assert len(store) == 256
    store.run(tool="t", arguments={"i": 256}, build="b", model_parameters_sha256="p",
              compute=answer(256))
    store.run(tool="t", arguments={"i": 0}, build="b", model_parameters_sha256="p",
              compute=answer(0))
    assert calls == [*range(257), 0], "the newest is kept, the oldest was dropped"


def test_the_key_hashes_canonical_arguments_and_never_carries_them():
    one = replay.replay_key(
        caller="local", tool="t", arguments={"a": 1, "b": "secret words"},
        build="b", model_parameters_sha256="p",
    )
    two = replay.replay_key(
        caller="local", tool="t", arguments={"b": "secret words", "a": 1},
        build="b", model_parameters_sha256="p",
    )
    assert one == two and re.fullmatch(r"[0-9a-f]{64}", one)
    assert one != replay.replay_key(
        caller="local", tool="u", arguments={"a": 1, "b": "secret words"},
        build="b", model_parameters_sha256="p",
    )


@pytest.mark.parametrize(
    "envelope",
    [
        pytest.param(
            evidence_rules._degraded_envelope({"norm_id": NORM_ID}, "generator failed", "b"),
            id="evidence-degraded",
        ),
        pytest.param(
            backlog_rules._degraded_envelope("judge failed", "b", judge_verdict="judge_error"),
            id="backlog-judge-error",
        ),
        pytest.param(
            {"answer": None, "judge_verdict": elicit_rules.ELICITATION_JUDGE_VERDICT},
            id="elicitation-failed",
        ),
        pytest.param(
            {
                "answer": {"results": [
                    {"judge_verdict": "accepted", "answer": {"assessment": "satisfied"}},
                    {"judge_verdict": "not_run", "answer": {"refused": True}},
                ]},
                "judge_verdict": "needs_human_review",
            },
            id="batch-with-a-failed-norm",
        ),
        pytest.param(None, id="no-envelope"),
    ],
)
def test_failed_answers_are_not_kept(envelope):
    assert replay.is_kept_answer(envelope) is False


@pytest.mark.parametrize(
    "envelope",
    [
        {"answer": {"assessment": "satisfied"}, "judge_verdict": "accepted"},
        {"answer": {"assessment": "satisfied"}, "judge_verdict": "rejected"},
        {"answer": {"features": {}}, "judge_verdict": elicit_rules.ELICITATION_JUDGE_VERDICT},
        {
            "answer": {"results": [{"judge_verdict": "rejected", "answer": {"x": 1}}]},
            "judge_verdict": "needs_human_review",
        },
    ],
)
def test_judged_answers_are_kept(envelope):
    assert replay.is_kept_answer(envelope) is True


# Every paid tool runs through the guard. The rules function stands in for
# the model call and counts its calls.


def _paid_tool_calls():
    return [
        ("evaluate_project_evidence", evidence_rules, "evaluate_project_evidence",
         lambda: server.evaluate_project_evidence(NORM_ID, "plan", CONTENT)),
        ("evaluate_project_evidence_batch", evidence_rules, "evaluate_evidence_batch",
         lambda: server.evaluate_project_evidence_batch("eu-ai-act:article-9", "plan", CONTENT)),
        ("generate_control_backlog", backlog_rules, "generate_control_backlog",
         lambda: server.generate_control_backlog([NORM_ID], "A hiring screening service.")),
        ("elicit_features", elicit_rules, "elicit_envelope",
         lambda: server.elicit_features("A hiring screening service that ranks applicants.")),
    ]


@pytest.mark.parametrize("tool, module, function, call", _paid_tool_calls(),
                         ids=[c[0] for c in _paid_tool_calls()])
def test_every_paid_tool_runs_through_the_guard(world, monkeypatch, tool, module, function, call):
    model_calls = []

    def fake(*args, **kwargs):
        model_calls.append(1)
        return {"answer": {"tool": tool}, "judge_verdict": "accepted", "legal_status_notes": []}

    monkeypatch.setattr(module, function, fake)
    first = call()
    second = call()
    assert len(model_calls) == 1
    assert _replay_note(first) is None
    assert _replay_note(second) == "2026-10-02T12:00:00Z"
    assert keys.TOOL_SCOPES[tool].endswith("_paid")


# The caller: the key middleware names it, and fastmcp's thread pool (sync
# tools run in a worker thread under fastmcp 4.0.10) carries it to the tool.


class _Ctx:
    def __init__(self, tool):
        self.message = type("M", (), {"name": tool})()


def test_the_key_middleware_names_the_caller_by_key_id(tmp_path):
    plaintext, record = keys.create_key("lab", ["evidence_paid"], tmp_path / "keys.json")
    mw = keys.ScopedKeyMiddleware(keys_file=tmp_path / "keys.json",
                                  usage_file=tmp_path / "usage.jsonl")
    mw._credential = lambda: plaintext
    seen = []

    async def call_next(ctx):
        seen.append(replay.current_caller())
        return "ran"

    assert asyncio.run(mw.on_call_tool(_Ctx("evaluate_project_evidence"), call_next)) == "ran"
    assert seen == [record["key_id"]]
    assert replay.current_caller() == "local", "the caller is reset after the call"


def test_a_sync_tool_reads_the_caller_set_by_the_key_middleware(tmp_path):
    from fastmcp import Client, FastMCP

    plaintext, record = keys.create_key("lab", ["admin"], tmp_path / "keys.json")
    mw = keys.ScopedKeyMiddleware(keys_file=tmp_path / "keys.json",
                                  usage_file=tmp_path / "usage.jsonl")
    mw._credential = lambda: plaintext
    probe = FastMCP(name="probe")
    probe.add_middleware(mw)

    @probe.tool(name="evaluate_project_evidence")
    def caller_probe() -> dict:
        return {"caller": replay.current_caller(), "thread": threading.current_thread().name}

    async def go():
        async with Client(probe) as client:
            result = await client.call_tool("evaluate_project_evidence", {})
            return result.structured_content

    answer = asyncio.run(go())
    assert answer["caller"] == record["key_id"]
    assert answer["thread"] != threading.main_thread().name, "sync tools run in a worker thread"


def test_two_concurrent_calls_over_fastmcp_make_one_model_call(world):
    from fastmcp import Client

    release = threading.Event()
    world.set_clients([GENERATOR_REPLY], [JUDGE_REPLY], hold=release)
    arguments = {"norm_id": NORM_ID, "artifact_type": "risk_management_plan", "content": CONTENT}

    async def go():
        async with Client(server.mcp) as client:
            first = asyncio.create_task(
                client.call_tool("evaluate_project_evidence", arguments))
            assert await asyncio.to_thread(world.generator.entered.wait, 10)
            second = asyncio.create_task(
                client.call_tool("evaluate_project_evidence", arguments))
            assert await asyncio.to_thread(world.waiting.wait, 10)
            release.set()
            return [r.structured_content for r in await asyncio.gather(first, second)]

    first, second = asyncio.run(go())
    assert world.generator.calls == 1 and world.judge.calls == 1
    assert _replay_note(first) is None
    assert _replay_note(second) == "2026-10-02T12:00:00Z"


def test_the_server_starts_only_with_a_usable_window(monkeypatch):
    monkeypatch.setenv("TERE4AI_MCP_REPLAY_WINDOW_SECONDS", "ten")
    monkeypatch.setattr(server, "_check_dump_integrity_at_startup", lambda: None)
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: pytest.fail("server started"))
    with pytest.raises(SystemExit, match="TERE4AI_MCP_REPLAY_WINDOW_SECONDS"):
        server.main()
