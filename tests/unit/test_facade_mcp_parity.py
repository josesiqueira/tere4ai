"""Facade/MCP parity tests (#50): both surfaces return identical envelopes.

The HTTP facade must be a thin transport over the same functions the MCP
server exposes (architecture.md Section 9: same server code, only transport
varies). For every deterministic tool, calling the facade endpoint and the
underlying tool function with the same inputs must yield byte-identical
JSON envelopes: any divergence means one surface silently drifted.

Deterministic tools only; the paid evidence/backlog paths are covered in
test_http_facade.py with fake clients.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.http_facade.app import SNAPSHOTS_DIR
from tere4ai.mcp_server import classify as classify_tool
from tere4ai.mcp_server import explain as explain_tool
from tere4ai.mcp_server import requirements as requirements_tool
from tere4ai.mcp_server import trace as trace_tool
from tere4ai.mcp_server.spans import resolve_span

# The judged dumps are published build artifacts (gitignored), so a fresh
# clone has none; skip cleanly instead of failing, checking the same dump
# location the facade itself resolves (default dir or TERE4AI_DUMP_DIR).
_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not all(
        (_DUMP_DIR / name).is_file()
        for name in ("layer1.json", "norms_core.json", "alignments_core.json")
    ),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)

# Same triage scenario and norm id as test_http_facade.py (tests/unit is not
# a package, so the constants are restated rather than imported).
ACCEPTED_NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
TRIAGE_FEATURES = {
    "description": (
        "An AI triage assistant that prioritises emergency department "
        "patients by predicted urgency to support clinician decisions."
    ),
    "domain": "healthcare",
    "autonomy": "advisory",
    "flags": {
        "essential_services_access": True,
        "subliminal_or_manipulative": False,
        "exploits_vulnerabilities": False,
        "social_scoring": False,
        "predictive_policing_profiling": False,
        "facial_image_scraping": False,
        "emotion_recognition_workplace_or_education": False,
        "biometric_categorisation": False,
        "real_time_remote_biometric_public": False,
        "law_enforcement_use": False,
    },
}


@pytest.fixture(scope="module")
def client():
    with TestClient(facade.create_app()) as test_client:
        yield test_client


_VOLATILE_KEYS = {"generated_at"}


def _strip_volatile(payload):
    if isinstance(payload, dict):
        return {
            k: _strip_volatile(v)
            for k, v in payload.items()
            if k not in _VOLATILE_KEYS
        }
    if isinstance(payload, list):
        return [_strip_volatile(v) for v in payload]
    return payload


def _canon(payload):
    """Canonical JSON minus per-call timestamps; ordering can never mask a diff."""
    return json.dumps(_strip_volatile(payload), sort_keys=True)


def test_classify_parity(client):
    via_http = client.post("/api/classify", json={"features": TRIAGE_FEATURES}).json()
    direct = classify_tool.classify_ai_system(TRIAGE_FEATURES, client.app.state.dump)
    assert _canon(via_http) == _canon(direct)


def test_requirements_parity(client):
    classification = client.post(
        "/api/classify", json={"features": TRIAGE_FEATURES}
    ).json()
    via_http = client.post(
        "/api/requirements", json={"classification": classification}
    ).json()
    direct = requirements_tool.get_applicable_requirements(
        classification,
        client.app.state.norms,
        client.app.state.dump,
        actor=None,
    )
    assert _canon(via_http) == _canon(direct)


def test_explain_parity(client):
    via_http = client.post("/api/explain", json={"norm_id": ACCEPTED_NORM_ID}).json()
    direct = explain_tool.explain_requirement(
        ACCEPTED_NORM_ID,
        client.app.state.dump,
        client.app.state.norms,
        client.app.state.alignments,
    )
    assert _canon(via_http) == _canon(direct)


def test_trace_parity(client):
    via_http = client.post("/api/trace", json={"id": ACCEPTED_NORM_ID}).json()
    direct = trace_tool.trace_alignment(
        ACCEPTED_NORM_ID, client.app.state.alignments, client.app.state.dump
    )
    assert _canon(via_http) == _canon(direct)


def test_span_parity(client):
    # Use a span the accepted norm actually cites, resolved from the live dump.
    norm = next(
        n
        for n in client.app.state.norms["norms"]
        if n["norm_id"] == ACCEPTED_NORM_ID
    )
    span_id = norm["source_span_id"]
    via_http = client.get(f"/api/span/{span_id}").json()
    direct = resolve_span(
        span_id,
        client.app.state.dump,
        SNAPSHOTS_DIR,
        extra_nodes=client.app.state.hleg_nodes,
    )
    assert _canon(via_http) == _canon(direct)


def test_unknown_norm_parity_on_clean_envelope(client):
    """Even the not-found path must be identical across surfaces."""
    via_http = client.post("/api/explain", json={"norm_id": "norm:does-not-exist"}).json()
    direct = explain_tool.explain_requirement(
        "norm:does-not-exist",
        client.app.state.dump,
        client.app.state.norms,
        client.app.state.alignments,
    )
    assert _canon(via_http) == _canon(direct)
