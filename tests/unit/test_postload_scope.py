"""Post-load gate POSTLOAD_GATE5 counts only Layer 2 and 3 edges (B143, spec G D-G75 (4), ruling R4).

Layer 0 now holds two DERIVED_FROM edges (from the derived HLEG text and its
record to the PDF), stamped with the parse's build id, which never equals a
published chained id; POSTLOAD_GATE5 must not count them. The database half is in
tests/integration/test_postload_gates.py.
"""

from tere4ai.validate_graph import postload


def test_postload_gate5_names_the_layer2_and_3_edges_only():
    query = postload._STALE_BUILD_EDGES
    assert "a:NormativeStatement" in query and "type(r) = 'DERIVED_FROM'" in query
    assert "['ASSERTS_ALIGNMENT_OF', 'ASSERTS_ALIGNMENT_TO']" in query
    assert "type(r) IN ['DERIVED_FROM'" not in query, "a bare DERIVED_FROM test would count Layer 0's edges"
    assert "$build_id" in query


def test_postload_gate5_runs_with_the_published_build_id():
    seen = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, query, params):
            seen.append((query, params))

            class Result:
                def single(self):
                    return [0]

            return Result()

    class Driver:
        def session(self):
            return Session()

    report = postload.validate_postload(Driver(), build_id="build-x+chain-1", expected_norms=0, expected_assertions=0)
    assert report.passed
    assert (postload._STALE_BUILD_EDGES, {"build_id": "build-x+chain-1"}) in seen
