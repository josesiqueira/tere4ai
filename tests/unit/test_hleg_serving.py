"""HLEG spans resolve only into the text the served build was made on (B143, spec G D-G75 (8)).

One loader, hleg_source.served_hleg, bound to the served layer1.json: it
refuses, naming both files, when that dump does not list the derived text and
its record, or lists either with another sha256 than the file on disk. Mock
data: a snapshots folder holding copies of the two files (one changed per
case) and a dump that lists them or not. Each case runs on the three paths:
the facade's span route, the MCP resolve_span tool and explain_requirement.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from tere4ai.align_hleg import hleg_source
from tere4ai.align_hleg.hleg_source import REFUSAL_PREFIX, served_hleg
from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.ingest.hleg_text import RECORD_FILE, SNAPSHOTS_DIR, TEXT_FILE

NORM_ID = "norm:eu-ai-act:article-15:paragraph-1:n1"
NORMS = {"build": {"build_id": "build-mock"}, "norms": [{
    "norm_id": NORM_ID, "source_node_id": "eu-ai-act:article-15:paragraph-1", "source_span_id": "span:015.001",
    "deontic_type": "obligation", "action": "achieve", "object": "accuracy", "judge_verdict": "accepted",
    "review_status": "accepted"}]}
ALIGNMENTS = {"build": {"build_id": "build-mock"}, "mapping_runs": [], "judge_runs": [], "assertions": [{
    "id": "align:x:1", "source_norm_id": NORM_ID, "target_id": "hleg:technical-robustness-and-safety",
    "relation_type": "supports", "final_score": 0.8, "judge_verdict": "accepted",
    "source_evidence_span_ids": ["span:015.001"], "target_evidence_span_ids": ["span:hleg:req2"]}]}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _listing(text_sha, record_sha):
    return [{"id": f"srcfile:{TEXT_FILE}", "layer": 0, "type": "SourceFile", "file": TEXT_FILE, "sha256": text_sha},
            {"id": f"srcfile:{RECORD_FILE}", "layer": 0, "type": "SourceFile", "file": RECORD_FILE, "sha256": record_sha}]


@pytest.fixture(params=["matching", "missing pair", "changed text", "changed record"])
def world(request, tmp_path, monkeypatch):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    for name in (TEXT_FILE, RECORD_FILE):
        (snapshots / name).write_bytes((SNAPSHOTS_DIR / name).read_bytes())
    listed = _listing(_sha(SNAPSHOTS_DIR / TEXT_FILE), _sha(SNAPSHOTS_DIR / RECORD_FILE))
    if request.param == "missing pair":
        listed = []
    elif request.param == "changed text":
        changed = (snapshots / TEXT_FILE).read_bytes().replace(b"Accuracy pertains", b"Accuracy pertain", 1)
        (snapshots / TEXT_FILE).write_bytes(changed)
    elif request.param == "changed record":
        record = json.loads((snapshots / RECORD_FILE).read_text(encoding="utf-8"))
        (snapshots / RECORD_FILE).write_text(json.dumps(record, indent=2), encoding="utf-8")
    dump = {"build": {"build_id": "build-mock", "snapshots": []}, "edges": [], "nodes": [
        *listed, {"id": "eu-ai-act:article-15:paragraph-1", "layer": 1, "type": "Paragraph", "text": "Accuracy.",
                  "source_span": {"span_id": "span:015.001", "snapshot_file": "x.html", "snapshot_sha256": "0" * 64,
                                  "start": 0, "end": 1}}]}
    monkeypatch.setattr(hleg_source, "SNAPSHOTS_DIR", snapshots)
    return request.param, snapshots, dump


def _refused(case):
    return case != "matching"


def test_the_loader(world):
    case, _, dump = world
    served = served_hleg(dump)
    if _refused(case):
        assert served.nodes == [] and served.refusal.startswith(REFUSAL_PREFIX)
        assert TEXT_FILE in served.refusal and RECORD_FILE in served.refusal
    else:
        assert served.refusal is None and len(served.nodes) == 7


def test_the_facade_span_route(world, tmp_path, monkeypatch):
    from tere4ai.http_facade import app as facade

    case, snapshots, dump = world
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    for name, payload in (("layer1.json", dump), ("norms_core.json", NORMS), ("alignments_core.json", ALIGNMENTS)):
        (dumps / name).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(facade, "SNAPSHOTS_DIR", snapshots)
    with TestClient(facade.create_app(dumps)) as client:
        response = client.get("/api/span/span:hleg:req2")
    if _refused(case):
        assert response.status_code == 503 and response.json()["error"].startswith(REFUSAL_PREFIX)
        assert TEXT_FILE in response.json()["error"] and RECORD_FILE in response.json()["error"]
    else:
        assert response.status_code == 200 and response.json()["text"].startswith("1.2 Technical robustness and safety")


def test_the_mcp_resolve_span_tool(world, monkeypatch):
    from tere4ai.mcp_server import server

    case, snapshots, dump = world
    monkeypatch.setattr(server, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(server, "_active", lambda: LoadedBuild(dump, NORMS, ALIGNMENTS, "build-mock", "legacy", None))
    envelope = server.resolve_span("span:hleg:req2")
    if _refused(case):
        assert envelope["status"] == "requires_human_review"
        assert any(f.startswith(REFUSAL_PREFIX) and RECORD_FILE in f for f in envelope["missing_facts"])
    else:
        assert envelope["status"] == "satisfied_with_evidence" and envelope["answer"]["snapshot_file"] == TEXT_FILE


def test_explain_requirement(world):
    from tere4ai.mcp_server.explain import explain_requirement

    case, _, dump = world
    envelope = explain_requirement(NORM_ID, dump, NORMS, ALIGNMENTS)
    entry = next(e for e in envelope["answer"]["span_trace"] if e["span_id"] == "span:hleg:req2")
    if _refused(case):
        assert entry["snapshot_file"] is None and envelope["status"] == "requires_human_review"
        assert any(f.startswith(REFUSAL_PREFIX) for f in envelope["missing_facts"])
    else:
        assert entry["snapshot_file"] == TEXT_FILE
        assert not any(f.startswith(REFUSAL_PREFIX) for f in envelope["missing_facts"])


def test_the_tracked_old_build_refuses_hleg_spans_on_every_path():
    """Review focus 2: today's data/graph_dumps/layer1.json lists the v1 copy and not
    the pair, so its HLEG spans are refused (D-G75 (9)) on the facade, the MCP tool and
    explain (review M7); the Layer 1 spans still resolve."""
    from tere4ai.graph_store.publication import load_active
    from tere4ai.http_facade import app as facade
    from tere4ai.mcp_server import server

    loaded = load_active(facade.DEFAULT_DUMP_DIR)
    if any(n.get("file") == TEXT_FILE for n in loaded.dump["nodes"] if n.get("type") == "SourceFile"):
        pytest.skip("the served build already lists the derived text (after B74)")
    assert served_hleg(loaded.dump).refusal.startswith(REFUSAL_PREFIX)
    with TestClient(facade.create_app()) as client:
        assert client.get("/api/span/span:hleg:req2").status_code == 503
        assert client.get("/api/span/span:009.001").status_code == 200
    envelope = server.resolve_span("span:hleg:req2")
    assert envelope["status"] == "requires_human_review"
    assert any(f.startswith(REFUSAL_PREFIX) for f in envelope["missing_facts"])
    explained = server.explain_requirement("norm:eu-ai-act:article-9:paragraph-1:n1")
    assert any(f.startswith(REFUSAL_PREFIX) for f in explained["missing_facts"])
    hleg = [e for e in explained["answer"]["span_trace"] if e["span_id"].startswith("span:hleg:")]
    assert hleg and all(e["snapshot_file"] is None for e in hleg)


def test_the_loader_never_raises_on_an_unreadable_file(world, monkeypatch):
    """Review M3: a read error becomes the named refusal, never an exception at facade startup."""
    case, snapshots, dump = world
    if case != "matching":
        pytest.skip("one case is enough")

    def unreadable(self):
        raise PermissionError("denied")

    monkeypatch.setattr(type(snapshots), "read_bytes", unreadable)  # every Path read fails in this test
    served = served_hleg(dump)
    assert served.nodes == [] and "PermissionError: denied" in served.refusal


def test_the_facade_and_the_mcp_server_import_no_pdf_library():
    import subprocess
    import sys

    code = ("import sys, tere4ai.http_facade.app, tere4ai.mcp_server.server; "
            "assert not {'pdfplumber', 'pypdf', 'pdfminer'} & set(sys.modules), sorted(sys.modules)")
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0
