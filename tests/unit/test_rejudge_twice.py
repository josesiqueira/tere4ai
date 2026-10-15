"""B174 final review: a build the re-judge produced can be re-judged again.
The v6/v2 mock source is re-judged under the code's versions (v7/v3); its
kept mapping runs still record align_hleg v2 while the file header and the
newly aligned norm's runs record v3. Published as a source (its publication
manifest and activation pointer written as make_source_build writes them),
it is re-judged again: `norms` and `alignments` both run and the assertion
ids are kept. Scripted clients only, never a paid model call.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.rejudge_mock_build import (
    NEW_NAME,
    NORM_C,
    NORM_D,
    UNIT_OF,
    ScriptedGenerator,
    ScriptedJudge,
    fake_cfg,
    folder_state,
    make_source_build,
    patch_command,
    unit_key,
)

import tere4ai.rejudge.__main__ as cli
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import write_publication_manifest
from tere4ai.rejudge.alignments import alignments_refusal
from tere4ai.rejudge.norms import norms_refusal

SECOND_NAME = "2026-10-17-gpt-fake-high-fake-fake"
SECOND_CHAIN_ID = "f6e5d4c3b2a1"


def _argv(command: str, src: Path, new_dir: Path, name: str) -> list[str]:
    return [command, "--source", str(src), "--out-dir", str(new_dir), "--name", name, "--cost-stop", "1000"]


def _rejudge(monkeypatch, src: Path, new_dir: Path, name: str) -> ScriptedGenerator:
    """`norms` (a judge that rejects D, so C is newly accepted against the v6
    source), then `alignments`; returns the Layer 3 generator."""
    patch_command(monkeypatch, cli, ScriptedJudge({unit_key(UNIT_OF[NORM_D]): "rejected"}))
    assert cli.main(_argv("norms", src, new_dir, name)) == 0
    generator = ScriptedGenerator()
    patch_command(monkeypatch, cli, ScriptedJudge(), generator=generator)
    assert cli.main(_argv("alignments", src, new_dir, name)) == 0
    return generator


def _publish(new_dir: Path, name: str) -> None:
    """Publish a rejudge output as a source, as make_source_build publishes
    the mock source: the publication manifest naming its three files with
    their sha256, and the activation pointer."""
    files = {"layer1_dump": "layer1.json", "norms": f"norms_{name}.json", "alignments": f"alignments_{name}.json"}
    inputs = [{"input_kind": kind, "file": file, "sha256": sha256_of_file(new_dir / file)}
              for kind, file in files.items()]
    record_id = BuildRecordStore(new_dir).resolve(name)
    publication = {"chain_id": SECOND_CHAIN_ID, "build_id": f"rejudge+chain-{SECOND_CHAIN_ID}",
                   "published_at": "2026-10-16T12:00:00+00:00", "gating": {"layer2": "llm", "layer3": "llm"},
                   "label": "llm-gated", "gates": [], "postload_gates": [], "manifests": [], "build_number": 1}
    write_publication_manifest(new_dir, publication, record_id=record_id, inputs=inputs, files=files)
    (new_dir / "ACTIVE_MANIFEST.json").write_text(
        json.dumps({"chain_id": SECOND_CHAIN_ID, "activated_at": "2026-10-16T12:00:10+00:00"}, indent=1),
        encoding="utf-8")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def rejudged(tmp_path, monkeypatch):
    """The v6/v2 source re-judged under v7/v3, published as a source."""
    src = make_source_build(tmp_path)
    first = tmp_path / "first" / NEW_NAME
    generator = _rejudge(monkeypatch, src, first, NEW_NAME)
    assert [line for _s, user in generator.calls for line in user.splitlines() if line.startswith("Norm id:")] \
        == [f"Norm id: {NORM_C}"]
    _publish(first, NEW_NAME)
    return first


def test_the_first_rejudge_output_mixes_v2_and_v3_runs(rejudged):
    payload = _read(rejudged / f"alignments_{NEW_NAME}.json")
    assert payload["build"]["alignment_prompt_version"] == "v3"
    assert {run["prompt_version"] for run in payload["mapping_runs"]} == {"v2", "v3"}
    norms = _read(rejudged / f"norms_{NEW_NAME}.json")
    sha = sha256_of_file(rejudged / f"norms_{NEW_NAME}.json")
    assert norms_refusal(norms, fake_cfg().as_public_dict()) is None
    assert alignments_refusal(payload, fake_cfg().as_public_dict(), sha) is None


def test_a_rejudge_output_can_be_rejudged_again(rejudged, tmp_path, monkeypatch):
    before = folder_state(rejudged)
    second = tmp_path / "second" / SECOND_NAME
    # the second judge also rejects D, so no norm is newly accepted and the generator is never called
    generator = _rejudge_again(monkeypatch, rejudged, second)
    assert generator.calls == []
    first_ids = [a["id"] for a in _read(rejudged / f"alignments_{NEW_NAME}.json")["assertions"]]
    second_ids = [a["id"] for a in _read(second / f"alignments_{SECOND_NAME}.json")["assertions"]]
    assert first_ids and second_ids == first_ids
    assert folder_state(rejudged) == before


def _rejudge_again(monkeypatch, src: Path, new_dir: Path) -> ScriptedGenerator:
    patch_command(monkeypatch, cli, ScriptedJudge({unit_key(UNIT_OF[NORM_D]): "rejected"}))
    assert cli.main(_argv("norms", src, new_dir, SECOND_NAME)) == 0
    generator = ScriptedGenerator()
    patch_command(monkeypatch, cli, ScriptedJudge(), generator=generator)
    assert cli.main(_argv("alignments", src, new_dir, SECOND_NAME)) == 0
    return generator


def test_a_run_that_records_no_prompt_version_is_refused_naming_it(rejudged):
    sha = sha256_of_file(rejudged / f"norms_{NEW_NAME}.json")
    alignments = _read(rejudged / f"alignments_{NEW_NAME}.json")
    kept = next(run for run in alignments["mapping_runs"] if run["prompt_version"] == "v2")
    del kept["prompt_version"]
    assert alignments_refusal(alignments, fake_cfg().as_public_dict(), sha) == (
        f"the source's alignment runs include {kept['id']}, which records no prompt_version; its align_hleg "
        "prompt cannot be checked against the file in the repository")
    norms = _read(rejudged / f"norms_{NEW_NAME}.json")
    norms["judge_runs"][0]["prompt_version"] = None
    assert norms_refusal(norms, fake_cfg().as_public_dict()) == (
        f"the source's judge runs include {norms['judge_runs'][0]['id']}, which records no prompt_version; its "
        "judge_norms prompt cannot be checked against the file in the repository")
