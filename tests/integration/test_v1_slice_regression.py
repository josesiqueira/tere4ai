"""v1-slice regression fixture (architecture.md Section 14, M2).

The old v1 poster's flagship claim was the mapping of the Chapter III core
articles to their HLEG requirements. Instead of migrating v1's unvalidated
LLM mappings (deferred by user decision), the judged pipeline regenerated the
slice; this test pins the semantic invariants so any future pipeline change
that breaks them fails loudly. Skips when no alignments dump is present
(the dump is a build artifact, not tracked in git).
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALIGNMENTS = ROOT / "data" / "graph_dumps" / "alignments_core.json"
FIXTURE = ROOT / "tests" / "fixtures" / "v1_slice_expectations.json"

pytestmark = pytest.mark.skipif(
    not ALIGNMENTS.exists(), reason="no alignments_core.json build artifact present"
)


def _accepted_by_article():
    data = json.loads(ALIGNMENTS.read_text(encoding="utf-8"))
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for assertion in data["assertions"]:
        if assertion.get("judge_verdict") != "accepted":
            continue
        match = re.search(r"(article-\d+)(?=:|$)", assertion["source_norm_id"])
        if match:
            per[match.group(1)][assertion["target_id"]] += 1
    return per


def test_v1_slice_dominant_targets_hold():
    expectations = json.loads(FIXTURE.read_text(encoding="utf-8"))["expectations"]
    per = _accepted_by_article()
    failures = []
    for article, expect in expectations.items():
        targets = per.get(article, {})
        total = sum(targets.values())
        if total < expect["min_accepted"]:
            failures.append(
                f"{article}: {total} accepted assertions, expected >= {expect['min_accepted']}"
            )
            continue
        dominant = max(targets, key=targets.get)
        if dominant != expect["dominant_target"]:
            failures.append(
                f"{article}: dominant target {dominant}, expected {expect['dominant_target']}"
            )
        for must in expect.get("must_also_hit", []):
            if targets.get(must, 0) < 1:
                failures.append(f"{article}: expected at least one hit on {must}")
    assert not failures, failures


def test_all_accepted_assertions_have_two_sided_evidence():
    data = json.loads(ALIGNMENTS.read_text(encoding="utf-8"))
    for assertion in data["assertions"]:
        if assertion.get("judge_verdict") == "accepted":
            assert assertion.get("source_evidence_span_ids"), assertion["id"]
            assert assertion.get("target_evidence_span_ids"), assertion["id"]
