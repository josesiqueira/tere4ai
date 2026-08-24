"""DEC-15: requirement-to-code traceability, scanner and matrix.

Contracts under test, from architecture.md DEC-15:
- the scanner is deterministic and finds tags with exact locations;
- only judge-accepted norm ids join the matrix, with review-queue, rejected,
  and unknown ids reported in invalid_tags with a reason;
- the matrix covers every applicable accepted norm, traced or untraced;
- a trace never raises an evidence status (the envelope status equals the
  requirements engine's own status for the same classification);
- tags citing accepted norms that are not applicable to this classification
  land in out_of_scope_tags, never in the matrix.
"""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.requirements import get_applicable_requirements
from tere4ai.mcp_server.trace_code import trace_implementation
from tere4ai.trace_scan import scan_tags

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = ROOT / "data" / "graph_dumps" / "alignments_core.json"

pytestmark = pytest.mark.skipif(
    not (DUMP_PATH.is_file() and NORMS_PATH.is_file() and ALIGNMENTS_PATH.is_file()),
    reason="graph dumps not built",
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alignments() -> dict:
    return json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def transparency_classification() -> dict:
    """A settled transparency_only classification answer (ShopBot shape)."""
    return {
        "risk_category": "transparency_only",
        "prohibited": False,
        "confidence": 1.0,
    }


def _accepted_article_50_norm_id(norms: dict) -> str:
    for n in norms["norms"]:
        if (
            n["norm_id"].startswith("norm:eu-ai-act:article-50:")
            and n.get("judge_verdict") == "accepted"
            and n.get("review_status") == "accepted"
        ):
            return n["norm_id"]
    pytest.fail("no accepted Article 50 norm in the dump; build changed?")


def _non_accepted_norm_id(norms: dict) -> str:
    for n in norms["norms"]:
        if n.get("judge_verdict") != "accepted":
            return n["norm_id"]
    pytest.fail("dump has no non-accepted norm; negative case impossible")


# --- scanner -----------------------------------------------------------------


def test_scanner_finds_tags_with_locations(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        '"""Disclosure.\n\n@implements: norm:eu-ai-act:article-50:paragraph-1:n2\n"""\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "b.ts").write_text(
        "// @implements: norm:eu-ai-act:article-9:paragraph-1:n1\nexport {};\n",
        encoding="utf-8",
    )
    # Not scanned: binary-ish suffix and a skipped directory.
    (tmp_path / "src" / "c.bin").write_bytes(b"@implements: norm:fake")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "d.py").write_text(
        "# @implements: norm:should-not-appear\n", encoding="utf-8"
    )

    records = scan_tags(tmp_path)
    assert records == [
        {
            "norm_id": "norm:eu-ai-act:article-50:paragraph-1:n2",
            "path": "src/a.py",
            "line": 3,
        },
        {
            "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
            "path": "src/b.ts",
            "line": 1,
        },
    ]


def test_scanner_is_deterministic(tmp_path):
    for name in ("z.py", "a.py", "m.py"):
        (tmp_path / name).write_text(
            "# @implements: norm:eu-ai-act:article-50:paragraph-1:n2\n",
            encoding="utf-8",
        )
    assert scan_tags(tmp_path) == scan_tags(tmp_path)


# --- matrix ------------------------------------------------------------------


def test_matrix_covers_every_applicable_norm_traced_or_untraced(
    transparency_classification, norms, alignments, dump
):
    norm_id = _accepted_article_50_norm_id(norms)
    env = trace_implementation(
        transparency_classification,
        [{"norm_id": norm_id, "path": "src/shopbot/chat.py", "line": 12}],
        norms,
        alignments,
        dump,
    )
    answer = env["answer"]
    rows = answer["matrix"]
    req_env = get_applicable_requirements(transparency_classification, norms, dump)
    served = sum(
        len(v) for v in req_env["answer"]["requirements_by_article"].values()
    )
    assert len(rows) == served, "matrix must cover exactly the applicable set"
    traced = [r for r in rows if r["trace_status"] == "traced"]
    assert [r["norm_id"] for r in traced] == [norm_id]
    assert traced[0]["trace_locations"] == [
        {"path": "src/shopbot/chat.py", "line": 12}
    ]
    assert traced[0]["source_span_id"], "every row carries its source span"
    untraced = [r for r in rows if r["trace_status"] == "untraced"]
    assert len(untraced) == served - 1
    assert answer["summary"] == {
        "applicable_norms": served,
        "traced": 1,
        "untraced": served - 1,
        "invalid_tags": 0,
        "out_of_scope_tags": 0,
    }


def test_non_accepted_and_unknown_ids_are_rejected_with_reasons(
    transparency_classification, norms, alignments, dump
):
    review_id = _non_accepted_norm_id(norms)
    env = trace_implementation(
        transparency_classification,
        [
            {"norm_id": review_id, "path": "a.py", "line": 1},
            {"norm_id": "norm:eu-ai-act:article-999:n1", "path": "b.py", "line": 2},
        ],
        norms,
        alignments,
        dump,
    )
    answer = env["answer"]
    assert answer["summary"]["traced"] == 0
    reasons = {t["norm_id"]: t["reason"] for t in answer["invalid_tags"]}
    assert "not judge-accepted" in reasons[review_id]
    assert "no norm with this id exists" in reasons["norm:eu-ai-act:article-999:n1"]
    # A rejected tag never appears as a trace location anywhere in the matrix.
    assert all(r["trace_locations"] == [] for r in answer["matrix"])


def test_out_of_scope_tags_are_reported_not_joined(
    transparency_classification, norms, alignments, dump
):
    # An accepted Article 9 norm is real, but not applicable to a
    # transparency_only system; the tag must land in out_of_scope_tags.
    article_9_id = next(
        n["norm_id"]
        for n in norms["norms"]
        if n["norm_id"].startswith("norm:eu-ai-act:article-9:")
        and n.get("judge_verdict") == "accepted"
        and n.get("review_status") == "accepted"
    )
    env = trace_implementation(
        transparency_classification,
        [{"norm_id": article_9_id, "path": "x.py", "line": 5}],
        norms,
        alignments,
        dump,
    )
    answer = env["answer"]
    assert answer["summary"]["out_of_scope_tags"] == 1
    assert answer["out_of_scope_tags"][0]["norm_id"] == article_9_id
    assert all(r["trace_locations"] == [] for r in answer["matrix"])


def test_traces_never_raise_the_evidence_status(
    transparency_classification, norms, alignments, dump
):
    norm_id = _accepted_article_50_norm_id(norms)
    req_env = get_applicable_requirements(transparency_classification, norms, dump)
    env = trace_implementation(
        transparency_classification,
        [{"norm_id": norm_id, "path": "a.py", "line": 1}],
        norms,
        alignments,
        dump,
    )
    assert env["status"] == req_env["status"], (
        "a trace is a claim, not evidence; tagging code must not change the "
        "envelope status the requirements engine assigns"
    )
    assert "not evidence" in env["answer"]["trace_note"]


def test_hleg_alignments_ride_on_matrix_rows(
    transparency_classification, norms, alignments, dump
):
    env = trace_implementation(
        transparency_classification, [], norms, alignments, dump
    )
    answer = env["answer"]
    rows_with_hleg = [r for r in answer["matrix"] if r["hleg_alignments"]]
    assert rows_with_hleg, "at least one Article 50 norm carries an accepted alignment"
    sample = rows_with_hleg[0]["hleg_alignments"][0]
    assert set(sample) == {"target_id", "relation_type", "final_score", "assertion_id"}
    assert sample["target_id"].startswith("hleg:")
    assert "not expert-validated" in answer["hleg_caveat"]


def test_malformed_tag_records_degrade_never_crash(
    transparency_classification, norms, alignments, dump
):
    for bad in ("not-a-list", [{"norm_id": ""}], [{"norm_id": "norm:x", "path": "a", "line": 0}], [42]):
        env = trace_implementation(
            transparency_classification, bad, norms, alignments, dump
        )
        assert env["status"] == "requires_human_review"
        assert env["confidence"] == 0.0
        assert env["missing_facts"], "the problem must be named, never silent"
