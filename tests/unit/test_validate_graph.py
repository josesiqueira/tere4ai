"""Tests for the Section 13 critical validation gates."""

import json
from pathlib import Path

from tere4ai.validate_graph import gates as gates_module
from tere4ai.validate_graph.gates import validate_build

ROOT = Path(__file__).resolve().parents[2]
DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"


def _real_dump():
    return json.loads(DUMP.read_text(encoding="utf-8"))


def test_real_build_passes_all_gates():
    report = validate_build(_real_dump())
    assert report.passed, report.failures[:5]
    assert report.stats["orphans"] == 0


def test_orphan_detection():
    dump = _real_dump()
    dump["nodes"].append({"id": "eu-ai-act:article-999", "layer": 1, "type": "Article", "number": 999})
    report = validate_build(dump)
    assert any("PUBLICATION_GATE1" in f and "article-999" in f for f in report.failures)


def test_norm_gates():
    dump = _real_dump()
    norms = [
        {"norm_id": "norm:x:n1", "source_span_id": "", "source_node_id": "eu-ai-act:article-9:paragraph-1"},
        {"norm_id": "norm:x:n2", "source_span_id": "span:ok", "source_node_id": "eu-ai-act:recital-12"},
    ]
    report = validate_build(dump, norms=norms)
    assert any("PUBLICATION_GATE3" in f and "norm:x:n1" in f for f in report.failures)
    assert any("PUBLICATION_GATE5" in f and "norm:x:n2" in f for f in report.failures)


def test_accepted_alignment_needs_two_sided_evidence():
    dump = _real_dump()
    alignments = [
        {
            "id": "align:bad",
            "judge_verdict": "accepted",
            "source_evidence_span_ids": ["span:a"],
            "target_evidence_span_ids": [],
        },
        {
            "id": "align:pending-ok",
            "judge_verdict": "pending",
            "source_evidence_span_ids": [],
            "target_evidence_span_ids": [],
        },
    ]
    report = validate_build(dump, alignments=alignments)
    assert any("PUBLICATION_GATE4" in f and "align:bad" in f for f in report.failures)
    assert not any("align:pending-ok" in f for f in report.failures)


def test_version_pin_gate():
    # B132: the published build merges the Omnibus, with the record of its
    # checks; without that record the merge is a silent replacement.
    dump = _real_dump()
    omnibus = next(n for n in dump["nodes"] if n["id"] == "src:omnibus-com-2025-836")
    assert omnibus["merged_into_base"] is True
    dump["build"].pop("amendments")
    report = validate_build(dump)
    assert any("PUBLICATION_GATE6" in f and "silent replacement" in f for f in report.failures)


def test_version_pin_gate_missing_merge_marker():
    # An in-force amending instrument must SAY merged_into_base False; an
    # absent marker is treated as silent replacement, not as innocence.
    dump = _real_dump()
    for n in dump["nodes"]:
        if n["id"] == "src:omnibus-com-2025-836":
            n["legal_status"] = "in_force"
            n.pop("merged_into_base", None)
    report = validate_build(dump)
    assert any("PUBLICATION_GATE6" in f and "silent replacement" in f for f in report.failures)


# B132 (spec G D-G68 (3)): a gate refuses a norm, an alignment or a test-set
# item whose source unit the Omnibus deleted.

DELETED_UNIT = "eu-ai-act:article-10:paragraph-5"


def test_a_norm_or_an_alignment_on_a_deleted_unit_fails_publication_gate3_and_gate4():
    dump = _real_dump()
    norms = [{"norm_id": f"norm:{DELETED_UNIT}:n1", "source_span_id": "span:010.005",
              "source_node_id": DELETED_UNIT}]
    alignments = [{"id": "align:x", "source_norm_id": f"norm:{DELETED_UNIT}:n1", "judge_verdict": "rejected"}]
    failures = validate_build(dump, norms=norms, alignments=alignments).failures
    assert any(f.startswith("PUBLICATION_GATE3 norm on a unit the Omnibus deleted") and DELETED_UNIT in f for f in failures)
    assert any(f.startswith("PUBLICATION_GATE4 alignment of a norm on a unit the Omnibus deleted: align:x") for f in failures)


def test_the_published_dev_norms_and_alignments_stand_on_no_deleted_unit():
    """D9: the dev dumps keep only norms and alignments on units unchanged in force."""
    norms = json.loads((DUMP.parent / "norms_core.json").read_text(encoding="utf-8"))["norms"]
    alignments = json.loads((DUMP.parent / "alignments_core.json").read_text(encoding="utf-8"))["assertions"]
    dump = _real_dump()
    report = validate_build(dump, norms=norms, alignments=alignments)
    assert not [f for f in report.failures if "deleted" in f], report.failures[:5]
    units = {n["id"]: n.get("amendment") for n in dump["nodes"]}
    assert {units[n["source_node_id"]] for n in norms} == {"unchanged"}


def test_the_published_dev_norms_keep_no_clause_of_a_dropped_norm():
    """Final review (opus Minor 4): every Condition and Exception record in the
    dev norms dump is the clause of a kept norm; the clauses of the norms D9
    dropped go with them."""
    norms = json.loads((DUMP.parent / "norms_core.json").read_text(encoding="utf-8"))
    referenced_conditions = {c for n in norms["norms"] for c in n["condition_ids"]}
    referenced_exceptions = {e for n in norms["norms"] for e in n["exception_ids"]}
    conditions = {c["id"] for c in norms["conditions"]}
    exceptions = {e["id"] for e in norms["exceptions"]}
    assert sorted(conditions - referenced_conditions) == []
    assert sorted(exceptions - referenced_exceptions) == []
    assert referenced_conditions <= conditions and referenced_exceptions <= exceptions
    # The counts the file states are those of the records it holds.
    assert norms["canonicalization"]["condition_nodes"] == len(norms["conditions"])
    assert norms["canonicalization"]["exception_nodes"] == len(norms["exceptions"])
    dropped = norms["stats"]["b132_dropped"]
    assert dropped["conditions"] + len(norms["conditions"]) == 364
    assert dropped["exceptions"] + len(norms["exceptions"]) == 27

def test_a_test_set_item_citing_a_deleted_unit_is_named():
    from tere4ai.eval.harness import load_gold_items
    from tere4ai.validate_graph.gates import deleted_unit_citations

    dump = _real_dump()
    assert deleted_unit_citations(dump, load_gold_items()) == []
    item = {"id": "gold:x", "kind": "retrieval", "gold": {"node_id": DELETED_UNIT}, "gold_citations": []}
    assert deleted_unit_citations(dump, [item]) == [
        f"test-set item gold:x cites a unit the Omnibus deleted: {DELETED_UNIT}"]


def test_every_failure_string_of_the_gates_module_starts_with_a_gate_name():
    # Review Focus 1: gate_entries matches by prefix, so every f-string the module can emit must open with a name in GATES
    import re
    from pathlib import Path

    from tere4ai.graph_store.publication import GATES
    root = Path(gates_module.__file__).resolve().parents[3]
    for rel in ("src/tere4ai/validate_graph/gates.py", "scripts/publish_layer23.py"):
        src = (root / rel).read_text(encoding="utf-8")
        prefixes = set(re.findall(r'f?"([A-Z][A-Z_0-9]*) ', src))
        assert not {p for p in prefixes if re.fullmatch(r"[GP][1-6]", p)}, rel
        assert {p for p in prefixes if "_GATE" in p} <= set(GATES), rel
