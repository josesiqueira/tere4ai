# Demo Revamp Plan A: Backend and Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the demo revamp's backend: the paid /api/elicit facade endpoint, the read-only demo-session endpoints, session recording in the example consumer scripts, and the replay parity test.

**Architecture:** All server changes are thin facade or mcp_server wrappers over existing functions, envelope-disciplined via make_envelope. Session recording lives in examples/ (outside the tere4ai2 repo) as plain JSONL append. Spec: docs/superpowers/specs/2026-07-29-demo-revamp-design.md.

**Tech Stack:** Python 3.12, FastAPI facade (src/tere4ai/http_facade/app.py), pytest, existing fake-client test patterns.

## Global Constraints

- NEVER use em dashes anywhere; never use en dashes as a sentence break (commas, colons, parentheses, separate sentences instead).
- Banned terms (compliant, certified, legally approved) never appear in system-generated strings; verbatim quote fields are exempt (DEC-08 scope, architecture.md Section 8).
- Run tests with `.venv/bin/python -m pytest` from the tere4ai2 repo root. NEVER `uv run pytest` (a shell hook breaks it in this environment).
- Gates that must pass before any commit: `.venv/bin/python -m pytest -q` (expect 558+ passed), `.venv/bin/python -m ruff check src scripts tests`, `.venv/bin/python scripts/check_traceability.py`, `.venv/bin/python scripts/check_release_hygiene.py`.
- Never commit `uv.lock` (untracked leftover) and never delete it.
- graphify rule for any code exploration: run `graphify query "<question>"` from /home/jose/Dev/Trustworthy before grepping or reading source; include this rule in every subagent prompt.
- New modules carry `@implements` / `@grounded_by` tags only when they implement a Section 16 decision; engineering MUSTs need no literature grounding.
- The elicitor NEVER returns or influences a risk category (DEC-13). Tests must assert this.

---

### Task 1: Elicitation envelope wrapper (mcp_server/elicit.py)

**Files:**
- Modify: `src/tere4ai/elicit_features/elicitor.py` (add one public helper)
- Create: `src/tere4ai/mcp_server/elicit.py`
- Test: `tests/unit/test_elicit_envelope.py`

**Interfaces:**
- Consumes: `elicit_features(description: str, generator: Any, prompt_version: str = "v4") -> tuple[dict | None, list[str]]` (existing, src/tere4ai/elicit_features/elicitor.py:45); `make_envelope(answer, status, *, graph_version, confidence=1.0, ..., judge_verdict=...)` (existing, src/tere4ai/mcp_server/tools.py:137).
- Produces: `schema_flag_names() -> list[str]` in elicitor.py (sorted flag keys from the loaded system_features schema); `elicit_envelope(description: str, generator: Any, *, graph_version: str, prompt_version: str = "v4") -> dict[str, Any]` in mcp_server/elicit.py. Task 2 imports `elicit_envelope`.

- [ ] **Step 1: Write the failing test**

```python
"""Elicitation envelope: proposals only, never a classification.

The elicited facts are proposals until a human confirms them, so the
envelope status is requires_human_review by construction (DEC-13 keeps
the deterministic ladder the only decision path).
"""

from tere4ai.elicit_features.elicitor import schema_flag_names
from tere4ai.mcp_server.elicit import elicit_envelope
from tere4ai.mcp_server.tools import SECTION_8_ENVELOPE_FIELDS

import json


class FakeGenerator:
    def __init__(self, payload):
        self._payload = payload

    def complete(self, system, user):
        return self._payload


def test_schema_flag_names_lists_all_34_flags():
    names = schema_flag_names()
    assert len(names) == 34
    assert names == sorted(names)
    assert "social_scoring" in names
    assert "creditworthiness_evaluation" in names


def test_elicit_envelope_is_a_section8_proposal():
    gen = FakeGenerator(json.dumps({
        "domain": "email security",
        "flags": {"social_scoring": False, "interacts_with_natural_persons": False},
    }))
    env = elicit_envelope("A spam filter for a small company's inboxes.",
                          gen, graph_version="build-test")
    assert set(env.keys()) == set(SECTION_8_ENVELOPE_FIELDS)
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.5
    assert env["answer"]["features"]["flags"]["social_scoring"] is False
    assert "risk_category" not in json.dumps(env["answer"])
    unspecified = env["missing_facts"]
    assert "flag not elicited: subliminal_or_manipulative" in unspecified
    assert not any("social_scoring" in m for m in unspecified)


def test_elicit_envelope_degrades_when_elicitation_fails():
    env = elicit_envelope("Too vague.", FakeGenerator("not json"),
                          graph_version="build-test")
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.0
    assert env["answer"] is None
    assert env["missing_facts"] == ["elicitation failed; fill the facts manually"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_elicit_envelope.py -v`
Expected: FAIL with ImportError (schema_flag_names and tere4ai.mcp_server.elicit do not exist).

- [ ] **Step 3: Add schema_flag_names to elicitor.py**

Append after the existing module-level schema/validator setup (reuse the already-loaded schema object; if the module holds only `_validator`, load the schema dict the same way the validator was built, do not duplicate file paths):

```python
def schema_flag_names() -> list[str]:
    """Sorted names of every flag in system_features.schema.json."""
    return sorted(_schema["properties"]["flags"]["properties"].keys())
```

If the module has no `_schema` variable, introduce it next to `_validator` from the same schema file it already reads. Do not hardcode the flag list.

- [ ] **Step 4: Create src/tere4ai/mcp_server/elicit.py**

```python
"""Elicitation envelope wrapper for the demo facade.

@implements: DEC-13
Engineering MUST (architecture.md Section 13, no silent degradation).
The elicitor proposes schema-valid facts with textual support; it never
classifies. This wrapper packages the proposal as a Section 8 envelope
whose status is requires_human_review by construction: elicited facts
are proposals until a human confirms or edits them, and only the
deterministic ladder ever assigns a risk category.
"""

from typing import Any

from tere4ai.elicit_features.elicitor import elicit_features, schema_flag_names
from tere4ai.mcp_server.tools import make_envelope

ELICITATION_JUDGE_VERDICT = "not_judged_elicitation_proposal"


def elicit_envelope(
    description: str,
    generator: Any,
    *,
    graph_version: str,
    prompt_version: str = "v4",
) -> dict[str, Any]:
    """One paid generator call; returns a facts PROPOSAL envelope."""
    features, notes = elicit_features(
        description, generator, prompt_version=prompt_version
    )
    if features is None:
        return make_envelope(
            answer=None,
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            legal_status_notes=notes,
            missing_facts=["elicitation failed; fill the facts manually"],
            judge_verdict=ELICITATION_JUDGE_VERDICT,
        )
    elicited = set((features.get("flags") or {}).keys())
    missing = [
        f"flag not elicited: {name}"
        for name in schema_flag_names()
        if name not in elicited
    ]
    return make_envelope(
        answer={"features": features, "notes": notes},
        status="requires_human_review",
        graph_version=graph_version,
        confidence=0.5,
        legal_status_notes=[
            "elicited facts are proposals; confirm or edit them before "
            "classification, the deterministic ladder alone decides"
        ],
        missing_facts=missing,
        judge_verdict=ELICITATION_JUDGE_VERDICT,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_elicit_envelope.py -v`
Expected: 3 PASS. If `_schema` naming differs, adapt Step 3 to the module's actual structure, never the test.

- [ ] **Step 6: Verify the no-model-import guard still holds**

Run: `.venv/bin/python -m pytest tests/unit -k "model_import or import_guard" -v`
Expected: PASS (elicit.py imports no model clients; it receives the generator as an argument).

- [ ] **Step 7: Commit**

```bash
git add src/tere4ai/elicit_features/elicitor.py src/tere4ai/mcp_server/elicit.py tests/unit/test_elicit_envelope.py
git commit -m "Demo revamp A1: elicitation proposal envelope (facts only, never a class)"
```

---

### Task 2: POST /api/elicit facade route

**Files:**
- Modify: `src/tere4ai/http_facade/app.py` (new request model + route, mirror the /api/evidence pattern at app.py:445-483; also add the route to the llms.txt text and the /.well-known/tere4ai.json tool listing, same as /api/trace/batch did)
- Test: `tests/unit/test_http_facade.py` (extend)

**Interfaces:**
- Consumes: `elicit_envelope` from Task 1; existing `_unavailable(request)`, `_build_paid_clients()`, `_graph_version(request)`, `PAID_HEADER`, `ModelConfigError`.
- Produces: `POST /api/elicit` accepting `{"description": "<str, min 30 chars>"}` returning a Section 8 envelope with the PAID header; 503 with `{"error": ...}` when model config is absent; 422 on short/missing description (FastAPI validation).

- [ ] **Step 1: Write the failing tests** (follow the file's existing fake-client and TestClient fixtures; the fake generator fixture pattern already exists from the banned-term work)

```python
def test_elicit_returns_a_proposal_envelope(client_with_fake_paid_clients):
    resp = client_with_fake_paid_clients.post(
        "/api/elicit",
        json={"description": "A spam filter for a small team inbox, "
                             "quarantines mail retrievably."},
    )
    assert resp.status_code == 200
    env = resp.json()
    assert env["status"] == "requires_human_review"
    assert "features" in (env["answer"] or {})
    assert resp.headers.get("x-tere4ai-paid") == "true"


def test_elicit_degrades_without_model_config(client):
    resp = client.post(
        "/api/elicit",
        json={"description": "A spam filter for a small team inbox, "
                             "quarantines mail retrievably."},
    )
    assert resp.status_code == 503
    assert "error" in resp.json()


def test_elicit_rejects_short_description(client):
    resp = client.post("/api/elicit", json={"description": "hi"})
    assert resp.status_code == 422
```

Note: use the exact PAID_HEADER constant name from app.py in the header assertion; read it from the module instead of hardcoding if the string differs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_http_facade.py -k elicit -v`
Expected: FAIL with 404 (route does not exist).

- [ ] **Step 3: Implement the route in app.py**

```python
class ElicitRequest(BaseModel):
    description: str = Field(min_length=30)


@app.post("/api/elicit")
def elicit(request: Request, body: ElicitRequest) -> JSONResponse:
    # PAID: one generator call, no judge. DEC-13: proposes facts,
    # never a risk category.
    unavailable = _unavailable(request)
    if unavailable is not None:
        return unavailable
    try:
        generator, _judge = _build_paid_clients()
    except ModelConfigError as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    try:
        envelope = elicit_tool.elicit_envelope(
            body.description, generator, graph_version=_graph_version(request)
        )
    except Exception as exc:  # noqa: BLE001 - clean payload, never a traceback
        return JSONResponse(
            status_code=502, content={"error": f"model call failed: {exc}"}
        )
    return JSONResponse(content=envelope, headers={PAID_HEADER: "true"})
```

Import `from tere4ai.mcp_server import elicit as elicit_tool` next to the existing tool imports. Add one line each to the llms.txt route text and the .well-known tool listing describing /api/elicit as paid fact-proposal elicitation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_http_facade.py -k elicit -v`
Expected: 3 PASS.

- [ ] **Step 5: Extend the scoped banned-term scan**

The existing DEC-08 scoped scan in test_http_facade.py iterates endpoint responses; add the elicit response (from the fake-client fixture) to the scanned set using `strip_verbatim_quote_fields` from tere4ai.mcp_server.tools.

Run: `.venv/bin/python -m pytest tests/unit/test_http_facade.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tere4ai/http_facade/app.py tests/unit/test_http_facade.py
git commit -m "Demo revamp A2: POST /api/elicit facade route (paid, proposal envelope)"
```

---

### Task 3: Demo session endpoints

**Files:**
- Modify: `src/tere4ai/http_facade/app.py`
- Test: `tests/unit/test_http_facade.py` (extend)

**Interfaces:**
- Consumes: nothing new; stdlib os/pathlib.
- Produces: `GET /api/demo/sessions` returning `{"sessions": ["<name>.jsonl", ...]}` or 404 when disabled; `GET /api/demo/sessions/{name}` returning the raw JSONL (media type application/jsonl) or 400 on a rejected name or 404. Env var: `TERE4AI_DEMO_SESSIONS_DIR`. Task C (UI) consumes both.

- [ ] **Step 1: Write the failing tests**

```python
def _sessions_env(monkeypatch, tmp_path):
    (tmp_path / "s1-spamguard.jsonl").write_text('{"seq": 1}\n')
    monkeypatch.setenv("TERE4AI_DEMO_SESSIONS_DIR", str(tmp_path))


def test_demo_sessions_disabled_without_env(client, monkeypatch):
    monkeypatch.delenv("TERE4AI_DEMO_SESSIONS_DIR", raising=False)
    assert client.get("/api/demo/sessions").status_code == 404


def test_demo_sessions_lists_jsonl_files(client, monkeypatch, tmp_path):
    _sessions_env(monkeypatch, tmp_path)
    resp = client.get("/api/demo/sessions")
    assert resp.status_code == 200
    assert resp.json() == {"sessions": ["s1-spamguard.jsonl"]}


def test_demo_session_serves_raw_jsonl(client, monkeypatch, tmp_path):
    _sessions_env(monkeypatch, tmp_path)
    resp = client.get("/api/demo/sessions/s1-spamguard.jsonl")
    assert resp.status_code == 200
    assert resp.text == '{"seq": 1}\n'


def test_demo_session_rejects_escape_and_unknown(client, monkeypatch, tmp_path):
    _sessions_env(monkeypatch, tmp_path)
    assert client.get(
        "/api/demo/sessions/..%2F..%2Fetc%2Fpasswd"
    ).status_code in (400, 404)
    assert client.get("/api/demo/sessions/nope.jsonl").status_code == 404
    assert client.get("/api/demo/sessions/evil.txt").status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_http_facade.py -k demo_session -v`
Expected: FAIL with 404 everywhere EXCEPT the disabled test, which passes trivially; that is acceptable, the other three drive the implementation.

- [ ] **Step 3: Implement the routes**

```python
def _demo_sessions_dir() -> Path | None:
    raw = os.environ.get("TERE4AI_DEMO_SESSIONS_DIR", "").strip()
    if not raw:
        return None
    base = Path(raw).resolve()
    return base if base.is_dir() else None


@app.get("/api/demo/sessions")
def demo_sessions() -> JSONResponse:
    # Read-only demo replay data; enabled only via env (spec: disableable).
    base = _demo_sessions_dir()
    if base is None:
        return JSONResponse(
            status_code=404,
            content={"error": "demo sessions not enabled "
                     "(TERE4AI_DEMO_SESSIONS_DIR unset or not a directory)"},
        )
    return JSONResponse(
        content={"sessions": sorted(p.name for p in base.glob("*.jsonl"))}
    )


@app.get("/api/demo/sessions/{name}")
def demo_session(name: str) -> Response:
    base = _demo_sessions_dir()
    if base is None:
        return JSONResponse(status_code=404, content={"error": "demo sessions not enabled"})
    if "/" in name or "\\" in name or name != Path(name).name or not name.endswith(".jsonl"):
        return JSONResponse(status_code=400, content={"error": "session name rejected"})
    candidate = (base / name).resolve()
    if candidate.parent != base or not candidate.is_file():
        return JSONResponse(status_code=404, content={"error": "unknown session"})
    return PlainTextResponse(
        candidate.read_text(encoding="utf-8"), media_type="application/jsonl"
    )
```

Use the module's existing imports (os, Path, Response types); add any missing ones at the top with the existing import block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_http_facade.py -k demo_session -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tere4ai/http_facade/app.py tests/unit/test_http_facade.py
git commit -m "Demo revamp A3: read-only demo session endpoints, env-gated and path-guarded"
```

---

### Task 4: Session recording in examples plus replay parity test

**Files:**
- Create: `/home/jose/Dev/Trustworthy/examples/_shared/session_recorder.py`
- Modify: `/home/jose/Dev/Trustworthy/examples/1-minimalrisk-spamguard/scripts/classify_manual.py`
- Create (generated, then copied): `tests/fixtures/demo_sessions/spamguard-classify.jsonl`
- Test: `tests/unit/test_demo_session_parity.py`

**Interfaces:**
- Consumes: the running example script (spawns the MCP server; no tere4ai2 imports in examples).
- Produces: session JSONL lines `{"seq": int, "ts": str, "tool": str, "request": dict, "envelope": dict, "repo_ref": str | null}`; the checked-in fixture; a parity test other sessions can copy.

- [ ] **Step 1: Create the recorder (examples side, no tere4ai2 imports)**

```python
"""Append MCP exchanges to a session JSONL for the demo replay page.

Shared by all example consumer scripts. Plain JSON lines, one exchange
per line: {seq, ts, tool, request, envelope, repo_ref}.
"""

import json
import time
from pathlib import Path
from typing import Any


def record_exchange(
    session_path: Path,
    seq: int,
    tool: str,
    request: dict[str, Any],
    envelope: dict[str, Any],
    repo_ref: str | None = None,
) -> None:
    line = {
        "seq": seq,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "request": request,
        "envelope": envelope,
        "repo_ref": repo_ref,
    }
    session_path.parent.mkdir(parents=True, exist_ok=True)
    with open(session_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
```

- [ ] **Step 2: Wire it into classify_manual.py**

In `main()` after the envelope is saved, add (with `import sys` and a path append for the shared folder, examples are not a package):

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from session_recorder import record_exchange  # noqa: E402

record_exchange(
    ARTIFACTS / "sessions" / "2026-07-29-classify-manual.jsonl",
    seq=1,
    tool="classify_ai_system",
    request={"features": FEATURES},
    envelope=envelope,
    repo_ref=None,
)
```

Move the `sys.path` line and import to the top of the file with the other imports.

- [ ] **Step 3: Re-run the example script and verify the session file**

Run: `cd /home/jose/Dev/Trustworthy/examples/1-minimalrisk-spamguard && /home/jose/Dev/Trustworthy/tere4ai2/.venv/bin/python scripts/classify_manual.py`
Expected: same classification as before (minimal_or_none, confidence 1.0) and a new `artifacts/sessions/2026-07-29-classify-manual.jsonl` with one line whose keys are exactly seq, ts, tool, request, envelope, repo_ref.

- [ ] **Step 4: Copy the session as a repo fixture**

```bash
mkdir -p tests/fixtures/demo_sessions
cp /home/jose/Dev/Trustworthy/examples/1-minimalrisk-spamguard/artifacts/sessions/2026-07-29-classify-manual.jsonl tests/fixtures/demo_sessions/spamguard-classify.jsonl
```

- [ ] **Step 5: Write the parity test**

```python
"""Replay honesty: a recorded session replays to the same envelopes.

Spec deviation, recorded deliberately: the spec says byte-equal, but
every envelope carries a fresh generated_at timestamp, so equality is
asserted on the full envelope with generated_at masked on both sides.
Everything else must match exactly, or replay would be showing the
audience something the live system did not say.
"""

import json
from pathlib import Path

from tere4ai.mcp_server.classify import classify_ai_system

FIXTURE = Path(__file__).parent.parent / "fixtures" / "demo_sessions" / "spamguard-classify.jsonl"


def _mask(envelope):
    masked = dict(envelope)
    masked["generated_at"] = "MASKED"
    return masked


def test_recorded_spamguard_session_replays_identically():
    lines = [json.loads(l) for l in FIXTURE.read_text().splitlines() if l.strip()]
    assert lines, "fixture must not be empty"
    for line in lines:
        assert set(line.keys()) == {"seq", "ts", "tool", "request", "envelope", "repo_ref"}
        if line["tool"] != "classify_ai_system":
            continue
        live = classify_ai_system(line["request"]["features"])
        assert _mask(live) == _mask(line["envelope"])
```

- [ ] **Step 6: Run the parity test**

Run: `.venv/bin/python -m pytest tests/unit/test_demo_session_parity.py -v`
Expected: PASS. If it fails on a field other than generated_at, the dump or code changed since recording: re-record the fixture (Step 3 and 4), never weaken the assertion.

- [ ] **Step 7: Commit (tere4ai2 side only; examples/ is outside this repo)**

```bash
git add tests/fixtures/demo_sessions/spamguard-classify.jsonl tests/unit/test_demo_session_parity.py
git commit -m "Demo revamp A4: session fixture and replay parity test (generated_at masked)"
```

---

### Task 5: Gates, task board, increment-2 promise

**Files:**
- Modify: `docs/TASKS.md`

**Interfaces:** none; bookkeeping.

- [ ] **Step 1: Run every gate**

Run, all from the tere4ai2 root, all must pass:
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src scripts tests
.venv/bin/python scripts/check_traceability.py
.venv/bin/python scripts/check_release_hygiene.py
```

- [ ] **Step 2: Add the task board rows**

Append to the B table in docs/TASKS.md (no em dashes):

```
| B30 | Demo revamp increment 1 IN PROGRESS (spec docs/superpowers/specs/2026-07-29-demo-revamp-design.md): Plan A backend DONE when this row's commit lands (elicit proposal envelope, /api/elicit, demo session endpoints, session recording, parity test); Plans B (UI shell) and C (centerpiece) follow | http_facade, mcp_server/elicit.py, examples | in progress |
| B31 | COMMITTED, NOT FORGOTTEN (increment 2 of the demo revamp spec): GitHub-repo input modality. A demo-harness agent clones a repo (curated list AND arbitrary URLs), proposes the 34 facts each with a supporting quote, proposals land editable in the fact panel, the deterministic ladder decides. Lives in the agent layer, never in TERE4AI core (repos are untrusted input, architecture.md Section 8) | demo harness + web fact panel | after increment 1 |
```

- [ ] **Step 3: Commit and push**

```bash
git add docs/TASKS.md
git commit -m "Demo revamp A5: task board rows B30 (increment 1) and B31 (GitHub modality, increment 2)"
git push origin main
```
