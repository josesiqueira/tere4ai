"""Regenerate the build record contract fixtures from synthetic inputs.

@implements: DEC-16
@grounded_by: REF-27, ADD-20

The five fixtures handed to the dashboard (plan 2b) are the presenter's real
output over deterministic synthetic dumps, never hand-written JSON: record
and run ids and timestamps are pinned, every file is written with fixed
bytes, and the byte-stability test in tests/unit/test_build_record_contract.py
fails when the presenter and the committed fixtures part ways. Stored records
(scenarios a and b) and the legacy dumps (scenarios c and d) live in separate
temporary directories, so a stored alias never suppresses a legacy synthesis.

Run from the repo root: python -m tests.fixtures.build_records.regenerate
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tere4ai.graph_store import build_record
from tere4ai.graph_store.build_chain import build_chain, sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import present_record, summary_of, synthesise_legacy_records
from tere4ai.graph_store.publication import read_target_state

FIXTURE_DIR = Path(__file__).resolve().parent
FIXED_IDS = ["r1parse00000", "run1parse000", "r2align00000", "run2prev0000", "run2align000"]
FIXED_NOW = "2026-09-19T00:00:00+00:00"
NOW = datetime(2026, 9, 19, tzinfo=UTC)
BASE = "build-b"
GENERATOR_PROMPT = "4" * 64
JUDGE_PROMPT = "5" * 64
PARSE_GATES = [
    {"name": "G1", "ok": True, "detail": "article count matches the frozen snapshot"},
    {"name": "G2", "ok": True, "detail": "recital count matches the frozen snapshot"},
    {"name": "G3", "ok": True, "detail": "annex count matches the frozen snapshot"},
    {"name": "G4", "ok": True, "detail": "no orphan legal node"},
    {"name": "G5", "ok": True, "detail": "cross references resolve within the parsed structure"},
    {"name": "G6", "ok": True, "detail": "merged_into_base marker present on the Omnibus source"},
]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def _write(path: Path, obj: Any) -> Path:
    path.write_text(_dumps(obj), encoding="utf-8")
    return path


def _layer1(n_articles: int) -> dict[str, Any]:
    nodes = [{"id": f"eu-ai-act:article-{i}", "type": "Article"} for i in range(1, n_articles + 1)]
    nodes.append({"id": "eu-ai-act:recital-1", "type": "Recital"})
    return {"build": {"build_id": BASE}, "nodes": nodes, "edges": [], "review_queue": [{"id": "rq:1"}]}


def _stored_scenarios(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """(a) a parse record as the parse command writes it; (b) a record whose
    failed align execution was resumed by a second, done, execution."""
    store = BuildRecordStore(root)
    manifest = _write(root / "manifest.json", {"snapshots": [{"file": "a.html", "sha256": "0" * 64}]})
    layer1 = _write(root / "layer1.json", _layer1(1))
    parse = store.create_record("parse-20260919T000000", None, None)
    run = store.start_execution(
        parse, command="parse_legal_structure", covers_steps=["L0.1", "L1.1"],
        argv=["--manifest", "manifest.json"],
        inputs=[{"role": "manifest", "file": manifest.name, "sha256": sha256_of_file(manifest)}],
        config={"manifest_files_count": 1}, expected_total=None, work_unit=None, checkpoint_file=None,
    )
    layer1_digest = sha256_of_file(layer1)
    store.finish_execution(
        parse, run, status="done", gates=PARSE_GATES,
        counts={"nodes": 2, "edges": 0, "nodes_by_type": {"Article": 1, "Recital": 1}, "review_queue": 1,
                "manifest_files": [{"file": "a.html", "sha256": "0" * 64}], "manifest_files_count": 1},
        outputs=[{"role": "layer1_dump", "file": layer1.name, "sha256": layer1_digest}],
    )
    store.set_layer1_digest(parse, layer1_digest)
    store.set_base_build_id(parse, BASE)
    store.add_alias(parse, f"layer1-{layer1_digest[:12]}")

    norms = _write(root / "norms_align-test.json", {"build": {"build_id": BASE}, "norms": []})
    inputs = [{"role": "norms", "file": norms.name, "sha256": sha256_of_file(norms)},
              {"role": "layer1_dump", "file": layer1.name, "sha256": layer1_digest}]
    rid = store.create_record("align-test", BASE, layer1_digest)
    common = {"command": "align_hleg_altai", "covers_steps": ["L3.1", "L3.2", "L3.3"], "inputs": inputs,
              "config": {"batch_size": 20, "prompt_version": "v1"}, "expected_total": 5, "work_unit": "batches",
              "checkpoint_file": "alignments_align-test.checkpoint.jsonl",
              "models": {"generator_model": "g", "judge_model": "j"},
              "prompt_sha256": {"generator": GENERATOR_PROMPT, "judge": JUDGE_PROMPT},
              "sampling": {"generator": "0", "judge": "0"}}
    done_before = ["batch:0:norm-a", "batch:1:norm-b", "batch:2:norm-c"]
    prev = store.start_execution(rid, argv=["--norms", norms.name], **common)
    store.finish_execution(
        rid, prev, status="failed", completed_keys=done_before,
        usage={"generator": {"calls": 3, "input_tokens": 1200, "output_tokens": 340},
               "judge": {"calls": 3, "input_tokens": 900, "output_tokens": 210}},
        error="TimeoutError: the alignment model did not answer on batch:3:norm-d",
    )
    resumed = store.start_execution(rid, argv=["--norms", norms.name, "--resume"], resumes_run_id=prev,
                                    inherited_keys=done_before, inherited_from=prev, **common)
    alignments = _write(root / "alignments_align-test.json", {"build": {"build_id": BASE}, "assertions": []})
    store.finish_execution(
        rid, resumed, status="done", completed_keys=["batch:3:norm-d", "batch:4:norm-e"],
        outputs=[{"role": "alignments", "file": alignments.name, "sha256": sha256_of_file(alignments)}],
        counts={"norms_total": 5, "norms_skipped_not_accepted": 0, "zero_alignment_norms": 0, "candidates": 7,
                "verdicts": {"accepted": 5, "rejected": 2}, "mechanical_rejects_count": 0},
        usage={"generator": {"calls": 2, "input_tokens": 800, "output_tokens": 230},
               "judge": {"calls": 2, "input_tokens": 600, "output_tokens": 140}},
        sampling={"generator": "0", "judge": "0"},
        work_failures={"nodes_failed": 0, "norms_failed": 0},
    )
    return (present_record(store.read(parse), root, NOW, None, store),
            present_record(store.read(rid), root, NOW, None, store))


def _legacy_scenarios(root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(c) the published legacy core build; (d) its b74 rerun, alignment
    interrupted with only a legacy checkpoint on disk. Returns both
    presented records and the chain id computed over (c)'s files."""
    _write(root / "layer1.json", _layer1(2))
    models = {"generator_model": "g", "judge_model": "j"}
    _write(root / "norms_core.json", {
        "build": {"build_id": BASE, "extraction_models": models, "prompt_version": "v1"},
        "norms": [], "judge_runs": [{"prompt_sha256": JUDGE_PROMPT}],
        "stats": {"source_units": 405, "candidates": 442, "verdicts": {"accepted": 339, "rejected": 54,
                                                                      "needs_human_review": 41},
                  "nodes_failed": 0, "invalid_norms": 8},
    })
    _write(root / "alignments_core.json", {
        "build": {"build_id": BASE, "alignment_models": models, "alignment_prompt_version": "v1"},
        "assertions": [], "mapping_runs": [], "judge_runs": [],
        "stats": {"norms_total": 434, "candidates": 636, "mechanical_rejects": 16,
                  "verdicts": {"accepted": 475, "rejected": 145, "needs_human_review": 0}},
    })
    _write(root / "norms_core.b74.json", {
        "build": {"build_id": BASE, "extraction_models": {"generator_model": "g2", "judge_model": "j2"},
                  "extraction_sampling": {"generator": "provider default", "judge": "provider default"},
                  "extraction_usage": {"generator": {"calls": 405, "input_tokens": 475017, "output_tokens": 108202},
                                       "judge": {"calls": 505, "input_tokens": 905340, "output_tokens": 409218}},
                  "prompt_version": "v1"},
        "norms": [], "judge_runs": [{"prompt_sha256": JUDGE_PROMPT}],
        "stats": {"source_units": 405, "candidates": 450, "verdicts": {"accepted": 350}, "nodes_failed": 0,
                  "invalid_norms": 3},
    })
    (root / "alignments_core.b74.json").write_bytes(b"")
    (root / "alignments_core.b74.checkpoint.jsonl").write_text(
        "".join(json.dumps({"batch": f"batch:{i}:norm-{i:04d}", "result": {"assertions": []}}, sort_keys=True) + "\n"
                for i in range(0, 300, 20)),
        encoding="utf-8",
    )
    older = build_chain(root / "layer1.json", root / "norms_core.json")
    _write(root / f"build_chain_{older['chain_id']}.json", {"build_id": f"{BASE}+chain-{older['chain_id']}", **older})
    full = build_chain(root / "layer1.json", root / "norms_core.json", alignments_path=root / "alignments_core.json")
    _write(root / f"build_chain_{full['chain_id']}.json", {"build_id": f"{BASE}+chain-{full['chain_id']}", **full})
    records = {r["aliases"][0]: r for r in synthesise_legacy_records(root)}
    served = full["chain_id"]
    return (present_record(records["core"], root, NOW, served, None),
            present_record(records["core.b74"], root, NOW, served, None), served)


def main(out_dir: Path | None = None) -> dict[str, str]:
    original_new_id, original_now = build_record._new_id, build_record._now
    build_record._new_id = iter(FIXED_IDS).__next__
    build_record._now = lambda: FIXED_NOW
    try:
        with tempfile.TemporaryDirectory() as stored_dir, tempfile.TemporaryDirectory() as legacy_dir:
            parse, resumed = _stored_scenarios(Path(stored_dir))
            core, b74, served = _legacy_scenarios(Path(legacy_dir))
            target = read_target_state(legacy_dir)
    finally:
        build_record._new_id, build_record._now = original_new_id, original_now
    listing = {
        "schema_version": "builds_list.v1",
        "graph_version": f"{BASE}+chain-{served}",
        "observed_at": NOW.isoformat(),
        "served_chain_id": served,
        "publication_target": target,
        "builds": [summary_of(p) for p in (parse, resumed, core, b74)],
    }
    produced = {
        "parse.json": _dumps(parse),
        "resumed_align.json": _dumps(resumed),
        "legacy_core.json": _dumps(core),
        "legacy_core_b74.json": _dumps(b74),
        "list.json": _dumps(listing),
    }
    if out_dir is not None:
        for name, text in produced.items():
            (Path(out_dir) / name).write_text(text, encoding="utf-8")
    return produced


if __name__ == "__main__":
    for written in main(FIXTURE_DIR):
        print(f"wrote {FIXTURE_DIR / written}")
