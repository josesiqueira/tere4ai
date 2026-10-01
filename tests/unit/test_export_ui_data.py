"""scripts/export_ui_data.py's review queue view (DEC-19, B65).

Hermetic: the script's pure function runs on a small mock payload, no dump.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_ui_data.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("export_ui_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_ui_data"] = module
    spec.loader.exec_module(module)
    return module


def test_the_review_queue_view_passes_the_type_on_when_the_norm_carries_it():
    export = _load_script()
    base = {"source_node_id": "eu-ai-act:article-19:paragraph-1", "deontic_type": "obligation",
            "judge_verdict": "needs_human_review", "action": "keep", "object": "the logs"}
    payload = {"norms": [{**base, "norm_id": "norm:a:n1", "requirement_type": "process"},
                         {**base, "norm_id": "norm:a:n2", "requirement_type": None},
                         {**base, "norm_id": "norm:a:n3"}]}
    items = export.build_review_queue({"nodes": [], "review_queue": []}, payload, None)["norms_needing_review"]
    by_id = {item["norm_id"]: item for item in items}
    assert by_id["norm:a:n1"]["requirement_type"] == "process"
    assert by_id["norm:a:n2"]["requirement_type"] is None
    assert "requirement_type" not in by_id["norm:a:n3"]
