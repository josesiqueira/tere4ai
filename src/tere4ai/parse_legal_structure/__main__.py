"""Build entry point: python -m tere4ai.parse_legal_structure

@implements: DEC-01
@grounded_by: REF-27, REF-08

Builds the merged Layer 0 + Layer 1 dump from the frozen snapshot, runs the
deterministic cross-reference rule pass (DEC-02), validates the result against
the Section 13 critical gates, and publishes data/graph_dumps/layer1.json only
when every gate passes (a build that fails critical validation is not
published).
"""

import json
import sys

from tere4ai.parse_legal_structure.parser import DEFAULT_OUT_PATH, build_layer1
from tere4ai.resolve_crossrefs.resolver import resolve
from tere4ai.validate_graph.gates import validate_build


def main() -> None:
    tmp_path = DEFAULT_OUT_PATH.with_suffix(".building.json")
    dump = build_layer1(out_path=tmp_path)
    dump = resolve(dump)

    report = validate_build(dump)
    if not report.passed:
        for failure in report.failures[:20]:
            print(f"GATE FAIL {failure}", file=sys.stderr)
        tmp_path.unlink(missing_ok=True)
        print("build NOT published: critical validation failed", file=sys.stderr)
        raise SystemExit(1)

    DEFAULT_OUT_PATH.write_text(
        json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    tmp_path.unlink(missing_ok=True)
    by_type: dict[str, int] = {}
    for node in dump["nodes"]:
        by_type[node["type"]] = by_type.get(node["type"], 0) + 1
    print(f"wrote {DEFAULT_OUT_PATH}")
    print(f"build_id: {dump['build']['build_id']}")
    print(f"nodes: {len(dump['nodes'])}, edges: {len(dump['edges'])}")
    for node_type in sorted(by_type):
        print(f"  {node_type}: {by_type[node_type]}")


if __name__ == "__main__":
    main()
