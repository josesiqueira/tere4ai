"""B173 task 4: `python -m tere4ai.rejudge` end to end on the published astra
build (thesis/builds/2026-10-14-gpt-6-astra-high, read only), with scripted
clients, never a paid model call: `norms`, `alignments`, the publication
gates of scripts/publish_layer23.py (--gates-only) and `report`, at one call
in flight and at eight (final review: the files are the same either way).

The scripted Layer 2 judge answers each message with the verdict the source's
judge (gpt-6-sol) gave its norm, found by rebuilding every norm's message,
except six flips: the first three rejected norms are accepted and the first
three accepted norms with at least one assertion are rejected. The scripted
Layer 3 judge answers the source verdict of the assertion its message names
and accepts any candidate the source does not hold (the newly aligned
norms'). The scripted generator answers each newly accepted norm with one
candidate whose quotes are verbatim prefixes of the norm's source text and
of the hleg:accountability description. Skipped when the thesis checkout or
the build is absent.

B174: the build was judged under judge_norms v6 and judge_alignment v2; the
command judges it under the code's defaults, v7 and v3, whose system prompts
hold the paragraph on the Act in force, with the messages rebuilt under the
source's versions.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from tests.unit.rejudge_mock_build import (
    GENERATOR_MODEL,
    INPUT_TOKENS_PER_CALL,
    JUDGE_MODEL,
    OUTPUT_TOKENS_PER_CALL,
    fake_cfg,
    folder_state,
    judge_reply,
    patch_command,
    prices,
)
from tests.unit.test_judge_prompts_in_force import PARAGRAPH

import tere4ai.rejudge.__main__ as cli
import tere4ai.rejudge.report as report
from tere4ai.align_hleg.__main__ import _attach_source_text
from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.extract_norms.model_clients import USAGE_KEYS
from tere4ai.extract_norms.pipeline import (
    _index_nodes,
    candidate_of_norm,
    judge_message,
    load_prompt,
    unit_of_norm,
)
from tere4ai.graph_store.build_record import BuildRecordStore

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT.parent / "thesis" / "builds" / "2026-10-14-gpt-6-astra-high"
SOURCE_NAME = "2026-10-14-gpt-6-astra-high"
NAME = "2026-10-16-gpt-6-astra-high-fake"
TARGET_ID = "hleg:accountability"
FLIPS = 3
GATES = [f"PUBLICATION_GATE{i}" for i in range(1, 7)]

pytestmark = pytest.mark.skipif(
    not SRC.is_dir(), reason="the thesis checkout with builds/2026-10-14-gpt-6-astra-high is absent")


class _Scripted:
    """A client with the attributes the commands read and a usage record (each
    call INPUT_TOKENS_PER_CALL and OUTPUT_TOKENS_PER_CALL); answer(user) gives
    the reply."""

    def __init__(self, model: str, temperature: str, json_mode: str):
        self.model = model
        self.effort = "high"
        self.temperature = temperature
        self.sampling = temperature
        self.json_mode = json_mode
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self.calls: list[tuple[str, str]] = []
        # several calls run at once under --max-in-flight 8: the counts are kept under a lock
        self._lock = threading.Lock()

    def answer(self, user: str) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str) -> str:
        with self._lock:
            self.calls.append((system, user))
            for key, value in (("calls", 1), ("input_tokens", INPUT_TOKENS_PER_CALL),
                               ("output_tokens", OUTPUT_TOKENS_PER_CALL), ("requests_sent", 1),
                               ("replies_with_usage", 1)):
                self.usage[key] += value
        return self.answer(user)


class NormsJudge(_Scripted):
    """The Layer 2 judge: the verdict of the norm whose rebuilt message this is;
    any other message fails the test."""

    def __init__(self, verdict_of_message: dict[str, str]):
        super().__init__(JUDGE_MODEL, "0", "N/A")
        self.verdict_of_message = verdict_of_message

    def answer(self, user: str) -> str:
        if user not in self.verdict_of_message:
            raise AssertionError(f"a Layer 2 message that no stored norm rebuilds: {user.splitlines()[0]}")
        return judge_reply(self.verdict_of_message[user], 0.7, rationale="scripted")


class AlignmentJudge(_Scripted):
    """The Layer 3 judge: the source verdict of the assertion the message names
    (its norm, target and quotes), accepted for a candidate the source does not
    hold."""

    def __init__(self, source_verdicts: dict[tuple[str, str, str, str], str]):
        super().__init__(JUDGE_MODEL, "0", "N/A")
        self.source_verdicts = source_verdicts
        self.new_candidates = 0

    def answer(self, user: str) -> str:
        norm_id = user.split("\n", 1)[0].removeprefix("Norm id: ")
        candidate = json.loads(user.split("Candidate alignment (JSON):\n", 1)[1])
        key = (norm_id, candidate["target_id"], candidate["source_quote"], candidate["target_quote"])
        verdict = self.source_verdicts.get(key)
        if verdict is None:
            with self._lock:
                self.new_candidates += 1
            verdict = "accepted"
        return judge_reply(verdict, 0.7, rationale="scripted")


class Generator(_Scripted):
    """The Layer 3 generator: one candidate for each norm it has quotes for;
    any other norm fails the test."""

    def __init__(self, source_quotes: dict[str, str], target_quote: str):
        super().__init__(GENERATOR_MODEL, "N/A", "sent")
        self.source_quotes = source_quotes
        self.target_quote = target_quote

    def answer(self, user: str) -> str:
        norm_id = user.split("\n", 1)[0].removeprefix("Norm id: ")
        if norm_id not in self.source_quotes:
            raise AssertionError(f"the generator was called for {norm_id}, which is not newly accepted")
        return json.dumps({"alignments": [{
            "target_id": TARGET_ID, "relation_type": "supports", "source_quote": self.source_quotes[norm_id],
            "target_quote": self.target_quote, "rationale": "scripted: the norm supports accountability",
        }]})


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_files() -> tuple[dict, dict, dict]:
    pointer = _load(SRC / "ACTIVE_MANIFEST.json")
    files = _load(SRC / "publications" / f"{pointer['chain_id']}.json")["files"]
    return _load(SRC / files["layer1_dump"]), _load(SRC / files["norms"]), _load(SRC / files["alignments"])


def _argv(command: str, new_dir: Path, *extra: str) -> list[str]:
    return [command, "--source", str(SRC), "--out-dir", str(new_dir), "--name", NAME, *extra]


@pytest.mark.parametrize("in_flight", ["1", "8"])
def test_rejudge_end_to_end_on_the_astra_build(tmp_path, monkeypatch, in_flight):
    before = folder_state(SRC)
    dump, source_norms_payload, source_alignments_payload = _source_files()
    source_norms = source_norms_payload["norms"]
    source_assertions = source_alignments_payload["assertions"]
    prompt_version = source_norms_payload["build"]["prompt_version"]
    assertions_of: dict[str, list[str]] = {}
    for assertion in source_assertions:
        assertions_of.setdefault(assertion["source_norm_id"], []).append(assertion["id"])

    # every norm's message rebuilt; the six flips chosen among unique messages
    nodes = _index_nodes(dump)
    message_of = {n["norm_id"]: judge_message(dump, nodes, unit_of_norm(dump, n),
                                              candidate_of_norm(n, prompt_version), prompt_version)
                  for n in source_norms}
    times = Counter(message_of.values())
    unique = [n for n in source_norms if times[message_of[n["norm_id"]]] == 1]
    newly_accepted = [n["norm_id"] for n in unique if n["judge_verdict"] == "rejected"][:FLIPS]
    newly_rejected = [n["norm_id"] for n in unique
                      if n["judge_verdict"] == "accepted" and assertions_of.get(n["norm_id"])][:FLIPS]
    assert len(newly_accepted) == len(newly_rejected) == FLIPS
    flipped = {**dict.fromkeys(newly_accepted, "accepted"), **dict.fromkeys(newly_rejected, "rejected")}
    verdict_of_message = {message_of[n["norm_id"]]: flipped.get(n["norm_id"], n["judge_verdict"])
                          for n in source_norms if times[message_of[n["norm_id"]]] == 1}
    verdict_of_message.update({message_of[n["norm_id"]]: n["judge_verdict"] for n in source_norms
                               if times[message_of[n["norm_id"]]] > 1})

    source_models = source_norms_payload["build"]["extraction_models"]
    cfg = fake_cfg(**{key: source_models[key] for key in ("generator_model", "generator_effort",
                                                          "generator_temperature", "generator_json_mode")})
    mock_prices = prices()
    price_rows = {JUDGE_MODEL: mock_prices[JUDGE_MODEL], source_models["generator_model"]: mock_prices[GENERATOR_MODEL]}
    new_dir = tmp_path / NAME

    # Layer 2: 480 judge calls, every message the rebuilt one, no generator built
    norms_judge = NormsJudge(verdict_of_message)
    patch_command(monkeypatch, cli, norms_judge, cfg=cfg, price_rows=price_rows)
    assert cli.main(_argv("norms", new_dir, "--cost-stop", "1000", "--max-in-flight", in_flight)) == 0
    assert len(norms_judge.calls) == len(source_norms) == 480
    assert Counter(user for _system, user in norms_judge.calls) == Counter(message_of.values())
    norms_payload = _load(new_dir / f"norms_{NAME}.json")
    # B174: a v6 source judged under v7, whose system prompt holds the paragraph
    assert prompt_version == "v6" and source_alignments_payload["build"]["alignment_prompt_version"] == "v2"
    assert {system for system, _user in norms_judge.calls} == {load_prompt("judge_norms", "v7")}
    assert PARAGRAPH in load_prompt("judge_norms", "v7")
    assert {r["prompt_version"] for r in norms_payload["judge_runs"]} == {"v7"}
    assert norms_payload["build"]["prompt_version"] == "v7"
    assert norms_payload["rejudge"]["source_prompt_version"] == "v6"
    assert norms_payload["build"]["extraction_usage"]["generator"]["calls"] == 0
    changed = {n["norm_id"]: n["judge_verdict"] for n, s in zip(norms_payload["norms"], source_norms, strict=True)
               if n["judge_verdict"] != s["judge_verdict"]}
    assert changed == flipped

    # Layer 3: the generator is called for exactly the three newly accepted norms
    to_align = json.loads(json.dumps([n for n in source_norms if n["norm_id"] in newly_accepted]))
    _attach_source_text(to_align, dump)
    accountability = next(node for node in build_hleg_nodes(load_pair()) if node["id"] == TARGET_ID)
    generator = Generator({n["norm_id"]: n["source_text"][:80] for n in to_align}, accountability["description"][:60])
    alignment_judge = AlignmentJudge({(a["source_norm_id"], a["target_id"], a["source_quote"], a["target_quote"]):
                                      a["judge_verdict"] for a in source_assertions})
    patch_command(monkeypatch, cli, alignment_judge, cfg=cfg, price_rows=price_rows, generator=generator)
    assert cli.main(_argv("alignments", new_dir, "--cost-stop", "1000", "--max-in-flight", in_flight)) == 0
    called = [user.split("\n", 1)[0].removeprefix("Norm id: ") for _system, user in generator.calls]
    assert sorted(called) == sorted(newly_accepted)
    alignments = _load(new_dir / f"alignments_{NAME}.json")
    stats = alignments["stats"]
    # B174: a v2 source judged under v3, whose system prompt holds the paragraph
    assert {system for system, _user in alignment_judge.calls} == {load_prompt("judge_alignment", "v3")}
    assert PARAGRAPH in load_prompt("judge_alignment", "v3")
    assert {r["prompt_version"] for r in alignments["judge_runs"] if r["judge_model"] == JUDGE_MODEL} == {"v3"}
    assert alignments["build"]["alignment_prompt_version"] == "v3"
    assert alignments["build"]["alignment_rejudge"]["source_prompt_version"] == "v2"
    assert sorted(stats["newly_aligned_norms"]) == sorted(newly_accepted)
    dropped = [aid for norm_id in newly_rejected for aid in assertions_of[norm_id]]
    assert sorted(stats["dropped_assertions"]) == sorted(dropped)
    source_ids = {a["id"] for a in source_assertions}
    new_ids = [a["id"] for a in alignments["assertions"] if a["id"] not in source_ids]
    assert len(new_ids) == FLIPS == alignment_judge.new_candidates
    assert {a["id"] for a in alignments["assertions"]} == (source_ids - set(dropped)) | set(new_ids)
    assert all(a["judge_verdict"] == "accepted" for a in alignments["assertions"] if a["id"] in new_ids)

    # the publication gates, as the main session runs them
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "publish_layer23.py"), "--norms", str(new_dir / f"norms_{NAME}.json"),
         "--alignments", str(new_dir / f"alignments_{NAME}.json"), "--dump", str(new_dir / "layer1.json"),
         "--record", NAME, "--gates-only"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    store = BuildRecordStore(new_dir)
    publish = store.read(store.resolve(NAME))["executions"][-1]
    assert publish["command"] == "publish_layer23" and publish["status"] == "done"
    assert [(g["name"], g["ok"]) for g in publish["gates"]] == [(name, True) for name in GATES]

    # the report lists exactly the changes: the six norms, no changed kept
    # assertion, the dropped assertions of the newly rejected norms, the new ones
    monkeypatch.setattr(report, "load_model_prices", lambda: price_rows)
    assert cli.main(_argv("report", new_dir)) == 0
    with (new_dir / "changed_verdicts.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    unit_of = {n["norm_id"]: n["source_node_id"] for n in source_norms}
    source_by_id = {a["id"]: a for a in source_assertions}
    assert rows == [
        ["layer", "id", "source_unit_or_norm", "source_verdict", "new_verdict"],
        *(["layer2", n["norm_id"], unit_of[n["norm_id"]], n["judge_verdict"], flipped[n["norm_id"]]]
          for n in source_norms if n["norm_id"] in flipped),
        *(["layer3", aid, source_by_id[aid]["source_norm_id"], source_by_id[aid]["judge_verdict"],
           "dropped, norm not accepted"] for aid in stats["dropped_assertions"]),
        *(["layer3", a["id"], a["source_norm_id"], "new, norm newly accepted", "accepted"]
          for a in alignments["assertions"] if a["id"] in new_ids),
    ]
    assert len(rows) == 1 + 2 * FLIPS + len(dropped) + FLIPS
    readme = (new_dir / "README.md").read_text(encoding="utf-8")
    assert f"## Verdicts that changed against {source_models['judge_model']}" in readme
    assert all(f"| `{norm_id}` | `{unit_of[norm_id]}` |" in readme for norm_id in flipped)
    assert "\u2014" not in readme and "\u2013" not in readme

    # the source folder: its file list and every sha256 unchanged
    assert folder_state(SRC) == before
