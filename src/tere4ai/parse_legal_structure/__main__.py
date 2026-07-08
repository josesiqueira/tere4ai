"""Build entry point: python -m tere4ai.parse_legal_structure

@implements: DEC-01
@grounded_by: REF-27, REF-08

Builds the merged Layer 0 + Layer 1 dump from the frozen snapshot, runs the
deterministic cross-reference rule pass (DEC-02), and writes
data/graph_dumps/layer1.json including REFERS_TO edges and the review queue.
"""

import json

from tere4ai.parse_legal_structure.parser import DEFAULT_OUT_PATH, build_layer1
from tere4ai.resolve_crossrefs.resolver import resolve


def main() -> None:
    dump = build_layer1()
    dump = resolve(dump)
    DEFAULT_OUT_PATH.write_text(
        json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8"
    )
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
