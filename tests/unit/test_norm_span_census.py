"""Citation-integrity census: every accepted norm's span resolves.

USER.md: a wrong or unverifiable citation is worse than a missing one.
The span resolver is checksum-verified and spot-tested, but until now no
test iterated the whole published population, so an offset regression
affecting a subset of spans could pass the suite. This census resolves
the source span of EVERY judge-accepted norm through the production
resolver (checksum verification included) and asserts each yields
non-empty source text and an existing source node. Runs in about one
second: the 339 accepted norms share 155 unique spans, and results are
cached per span id.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tere4ai.mcp_server.spans import resolve_span

ROOT = Path(__file__).resolve().parents[2]
_DUMP_DIR = Path(os.environ.get("TERE4AI_DUMP_DIR") or ROOT / "data" / "graph_dumps")
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

pytestmark = pytest.mark.skipif(
    not (
        (_DUMP_DIR / "layer1.json").is_file()
        and (_DUMP_DIR / "norms_core.json").is_file()
        and (SNAPSHOTS_DIR / "MANIFEST.json").is_file()
    ),
    reason="graph dumps or snapshots not present (see README quick start)",
)


@pytest.fixture(scope="module")
def census():
    dump = json.loads((_DUMP_DIR / "layer1.json").read_text(encoding="utf-8"))
    norms_payload = json.loads(
        (_DUMP_DIR / "norms_core.json").read_text(encoding="utf-8")
    )
    accepted = [
        n for n in norms_payload["norms"] if n.get("review_status") == "accepted"
    ]
    node_ids = {n["id"] for n in dump["nodes"]}
    resolved: dict[str, dict | Exception] = {}
    for norm in accepted:
        span_id = norm["source_span_id"]
        if span_id not in resolved:
            try:
                resolved[span_id] = resolve_span(span_id, dump, SNAPSHOTS_DIR)
            except Exception as exc:  # collected, asserted below
                resolved[span_id] = exc
    return norms_payload, accepted, node_ids, resolved


def test_census_covers_every_published_accepted_norm(census):
    norms_payload, accepted, _, _ = census
    assert len(accepted) == norms_payload["stats"]["verdicts"]["accepted"], (
        "accepted norms in the dump disagree with the dump's own stats block"
    )
    assert accepted, "census would be vacuous: no accepted norms found"


def test_every_accepted_norm_source_node_exists(census):
    _, accepted, node_ids, _ = census
    missing = [n["norm_id"] for n in accepted if n["source_node_id"] not in node_ids]
    assert not missing, f"{len(missing)} accepted norms cite unknown nodes: {missing[:5]}"


def test_every_accepted_norm_span_resolves_to_verified_text(census):
    _, accepted, _, resolved = census
    failures = []
    for norm in accepted:
        result = resolved[norm["source_span_id"]]
        if isinstance(result, Exception):
            failures.append(
                f"{norm['norm_id']} -> {norm['source_span_id']}: "
                f"{type(result).__name__}: {result}"
            )
        elif not (result.get("text") or "").strip():
            failures.append(
                f"{norm['norm_id']} -> {norm['source_span_id']}: empty text slice"
            )
    assert not failures, (
        f"{len(failures)} of {len(accepted)} accepted norms failed span "
        f"resolution:\n" + "\n".join(failures[:10])
    )
