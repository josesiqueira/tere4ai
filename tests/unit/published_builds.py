"""B177 (DEC-29): a published build in a temporary folder, from mock data the
test writes, for the tests of the served build (test_served_build.py) and of
the facade following it (test_facade_newest_build.py)."""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.graph_store.build_chain import build_chain
from tere4ai.graph_store.publication import activate, write_publication_manifest


def publish_build(folder: Path, published_at: str, marker: str = "", judges: dict[str, dict[str, str]] | None = None) -> str:
    """A published build in folder: the three dump files, the chain record,
    the publication manifest with published_at, and the activation pointer.
    Answers the chain id. judges, when given, is written into the norms
    and alignments files' build blocks (for example {"extraction_models":
    {"generator_model": "gpt-6-astra", "judge_model": "claude-opus-5-5"}}),
    where a published build records the models that made it."""
    folder.mkdir(parents=True, exist_ok=True)
    payloads = {
        "layer1.json": {"build": {"build_id": "build-b"}, "nodes": [], "edges": [], "marker": marker or folder.name},
        "norms_core.json": {"build": {"build_id": "build-b", **(judges or {})}, "norms": []},
        "alignments_core.json": {"build": {"build_id": "build-b", **(judges or {})}, "assertions": []},
    }
    for name, payload in payloads.items():
        (folder / name).write_text(json.dumps(payload), encoding="utf-8")
    chain = build_chain(folder / "layer1.json", folder / "norms_core.json",
                        alignments_path=folder / "alignments_core.json")
    publication = {"chain_id": chain["chain_id"], "build_id": f"build-{folder.name}+chain-{chain['chain_id']}",
                   "published_at": published_at, "gating": {"layer2": "llm", "layer3": "llm"},
                   "label": "llm-gated", "gates": [], "postload_gates": [], "manifests": []}
    write_publication_manifest(folder, publication, record_id="r", inputs=chain["inputs"],
                               files={"layer1_dump": "layer1.json", "norms": "norms_core.json",
                                      "alignments": "alignments_core.json"})
    activate(folder, chain["chain_id"])
    return chain["chain_id"]
