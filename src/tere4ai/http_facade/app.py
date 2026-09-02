"""Thin HTTP facade for the M3 demo web UI.

@implements: DEC-08 (partial: also Section 8 hardening, rate limit and request log)
@grounded_by: REF-31

Loopback-only intent (architecture.md Section 9): the demo UI never touches
the database or model APIs directly. This facade calls the same pure
functions the MCP server exposes (classify_ai_system,
get_applicable_requirements, evaluate_project_evidence,
generate_control_backlog, elicit_features) over the versioned offline graph dumps.

Behavioral contract:
- The Layer 0+1 dump (layer1.json) and the judged norms payload
  (norms_core.json) are loaded once at startup. If either is missing, every
  endpoint returns a clean 503 JSON payload, never a traceback (no silent
  degradation, Section 13).
- /api/classify, /api/requirements, /api/explain, /api/trace,
  /api/trace/batch, and /api/span/{span_id} are deterministic and free.
  /api/explain and the trace endpoints additionally need
  alignments_core.json (503 with a clean payload when it is missing);
  /api/span verifies the snapshot checksum before slicing.
- /api/trace/batch is a thin bulk wrapper for the demo UI: one
  trace_alignment envelope per unique requested id, passed through
  unmodified, so the assess page can render HLEG alignment chips for all
  served norms with a single request instead of one call per norm.
- /api/evidence and /api/backlog perform PAID model calls (OpenAI generator
  plus Anthropic runtime grounding judge). /api/elicit performs a PAID
  generator call (fact elicitation, no judge). Model clients are built lazily
  per request; a missing key surfaces the ModelConfigError message as a
  clean JSON error. Paid responses carry the header X-TERE4AI-Paid-Call.
- GET /api/demo/sessions and /api/demo/sessions/{name}: read-only demo replay
  data, enabled only when TERE4AI_DEMO_SESSIONS_DIR is set.
- The backlog endpoint caps the norms used at MAX_BACKLOG_NORMS (10)
  regardless of the tool's own maximum; the cap is never silent (the tool
  notes the truncation in the answer).
- CORS is open only to the local demo UI origin (localhost:3111).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.judge.config import ModelConfigError, load_model_config
from tere4ai.mcp_server import backlog as backlog_tool
from tere4ai.mcp_server import classify as classify_tool
from tere4ai.mcp_server import elicit as elicit_tool
from tere4ai.mcp_server import evidence as evidence_tool
from tere4ai.mcp_server import explain as explain_tool
from tere4ai.mcp_server import requirements as requirements_tool
from tere4ai.mcp_server import trace as trace_tool
from tere4ai.mcp_server.spans import (
    SpanIntegrityError,
    SpanNotFoundError,
    resolve_span,
)
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
    coverage_report,
    make_envelope,
)
from tere4ai.report.ingest import ingest_inputs
from tere4ai.report.render import render_report

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DUMP_DIR = _PROJECT_ROOT / "data" / "graph_dumps"
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"
DUMP_DIR_ENV = "TERE4AI_DUMP_DIR"

# Default facade port for the demo flow (README, web/src/app/assess).
FACADE_PORT = 8008

# The demo UI's local origin; the facade is loopback-intended, so nothing else.
ALLOWED_ORIGINS = ("http://localhost:3111", "http://127.0.0.1:3111")

# Facade-level cap on backlog input norms, regardless of the tool's own max.
MAX_BACKLOG_NORMS = 10

# Cap on ids per /api/trace/batch request. The published build serves at most
# a few hundred accepted norms, so 500 covers every real assessment while
# keeping a single request bounded.
MAX_TRACE_BATCH_IDS = 500

PAID_HEADER = "X-TERE4AI-Paid-Call"

# Hardening (Section 8: rate limiting, request logging). Fixed-window
# per-client limit; 0 disables. The request log is body-free by design:
# request bodies can carry project evidence text, which Section 13 says to
# redact, so only method, path, status, latency, and client are recorded.
RATE_LIMIT_ENV = "TERE4AI_RATE_LIMIT_PER_MINUTE"
DEFAULT_RATE_LIMIT_PER_MINUTE = 120
REQUEST_LOG_ENV = "TERE4AI_REQUEST_LOG"
DEFAULT_REQUEST_LOG = _PROJECT_ROOT / "data" / "review_queue" / "facade_requests.jsonl"


class ClassifyRequest(BaseModel):
    features: dict[str, Any]


class RequirementsRequest(BaseModel):
    classification: dict[str, Any]
    actor: str | None = None


class ElicitRequest(BaseModel):
    description: str = Field(min_length=30)


class EvidenceRequest(BaseModel):
    norm_id: str
    artifact_type: str
    content: str
    artifact_id: str | None = None


class BacklogRequest(BaseModel):
    norm_ids: list[str] = Field(min_length=1)
    system_context: str


class ExplainRequest(BaseModel):
    norm_id: str


class TraceRequest(BaseModel):
    id: str


class TraceBatchRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_TRACE_BATCH_IDS)


class ReportRequest(BaseModel):
    session_jsonl: str = Field(min_length=1, max_length=10 * 1024 * 1024)


def _sanitize_non_finite(value: Any) -> Any:
    """Replace non-finite floats (NaN, Infinity, -Infinity) anywhere in a
    validation-error payload with an honest placeholder string.

    A request body containing one of these literals parses fine in Python's
    json module, but Pydantic then rejects the value and echoes it back
    inside the raw error detail, where the strict JSON encoder used for
    responses (allow_nan=False) would otherwise raise and turn a routine
    validation failure into an uncaught 500 (Section 13, no silent
    degradation, but also no unhandled crash). Recurses into lists and
    dicts so a non-finite value nested anywhere in the offending input is
    still caught; every other value, including normal finite floats and
    real validation detail, passes through unchanged.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return "non-finite number rejected"
    if isinstance(value, dict):
        return {key: _sanitize_non_finite(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_non_finite(v) for v in value]
    return value


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_hleg_nodes() -> list[dict[str, Any]]:
    """The seven HLEG requirement nodes for target-side span resolution;
    empty when the frozen HLEG text or its checksum is unavailable."""
    try:
        from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes

        return build_hleg_nodes()
    except Exception:  # noqa: BLE001 - degrade to dump-only span resolution
        return []


def _build_paid_clients() -> tuple[Any, Any]:
    """Construct the real generator and judge lazily, per paid request.

    Raises ModelConfigError when keys or model ids are missing; the caller
    turns that into a clean JSON error, never a traceback.
    """
    cfg = load_model_config()
    return OpenAIGenerator(cfg), AnthropicJudge(cfg)


def create_app(dump_dir: Path | str | None = None) -> FastAPI:
    """Facade app factory. dump_dir overrides the graph dump location
    (also settable via the TERE4AI_DUMP_DIR environment variable)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        base = Path(dump_dir or os.environ.get(DUMP_DIR_ENV) or DEFAULT_DUMP_DIR)
        app.state.dump = _load_json(base / "layer1.json")
        app.state.norms = _load_json(base / "norms_core.json")
        app.state.alignments = _load_json(base / "alignments_core.json")
        app.state.hleg_nodes = _load_hleg_nodes()
        schema_path = (
            _PROJECT_ROOT / "schema" / "json_schemas" / "system_features.schema.json"
        )
        try:
            raw = schema_path.read_bytes()
            app.state.features_schema = json.loads(raw)
            app.state.features_schema_sha256 = hashlib.sha256(raw).hexdigest()
        except OSError:
            app.state.features_schema = None
            app.state.features_schema_sha256 = None
        missing = [
            name
            for name, payload in (("layer1.json", app.state.dump), ("norms_core.json", app.state.norms))
            if payload is None
        ]
        # Name the files, not the absolute server directory (audit W4).
        app.state.load_error = (
            f"graph dumps unavailable: missing or unreadable {', '.join(missing)}; "
            "build them with python -m tere4ai.parse_legal_structure "
            "and python -m tere4ai.extract_norms"
            if missing
            else None
        )
        yield

    app = FastAPI(title="TERE4AI v2 demo facade", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=[PAID_HEADER],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Same {"detail": [...]} shape as FastAPI's default handler (clients
        # and existing tests see no difference), but with non-finite floats
        # sanitized before encoding. A NaN/Infinity/-Infinity JSON literal in
        # the request body parses fine, Pydantic rejects it and echoes the
        # value into exc.errors(), and the strict response encoder used
        # below would otherwise raise ValueError and surface as an uncaught
        # 500 (the bug this handler closes; Section 13, no silent
        # degradation, but never a raw 500 either).
        errors = _sanitize_non_finite(jsonable_encoder(exc.errors()))
        return JSONResponse(status_code=422, content={"detail": errors})

    # Section 8 hardening: fixed-window per-client rate limit and a body-free
    # JSON request log. In-process state is enough for the loopback demo
    # facade; the hosted Mode A gets a real gateway in Phase 2.
    rate_limit = int(os.environ.get(RATE_LIMIT_ENV, DEFAULT_RATE_LIMIT_PER_MINUTE))
    request_log_path = Path(os.environ.get(REQUEST_LOG_ENV, DEFAULT_REQUEST_LOG))
    app.state.rate_limit_per_minute = rate_limit
    app.state.rate_windows = {}

    @app.middleware("http")
    async def harden(request: Request, call_next):
        import time as _time

        client = request.client.host if request.client else "unknown"
        limit = request.app.state.rate_limit_per_minute
        if limit > 0:
            window = int(_time.time() // 60)
            windows = request.app.state.rate_windows
            key = (client, window)
            # Drop stale windows so the map cannot grow unbounded.
            for stale in [k for k in windows if k[1] != window]:
                del windows[stale]
            windows[key] = windows.get(key, 0) + 1
            if windows[key] > limit:
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate limit exceeded", "limit_per_minute": limit},
                    headers={"Retry-After": str(60 - int(_time.time() % 60))},
                )

        started = _time.perf_counter()
        response = await call_next(request)
        latency_ms = round((_time.perf_counter() - started) * 1000, 1)
        try:
            request_log_path.parent.mkdir(parents=True, exist_ok=True)
            with request_log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "ts": _time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                            "method": request.method,
                            "path": request.url.path,
                            "status": response.status_code,
                            "latency_ms": latency_ms,
                            "client": client,
                            "paid": PAID_HEADER in response.headers,
                        }
                    )
                    + "\n"
                )
        except OSError:
            # Logging must never take the service down (Section 13); the
            # request still succeeds if the log volume is read-only.
            pass
        return response

    def _unavailable(request: Request) -> JSONResponse | None:
        error = request.app.state.load_error
        if error is None:
            return None
        return JSONResponse(status_code=503, content={"error": error})

    def _graph_version(request: Request) -> str:
        dump = request.app.state.dump or {}
        return str(dump.get("build", {}).get("build_id", "unknown"))

    def _norms_by_id(request: Request) -> dict[str, dict[str, Any]]:
        payload = request.app.state.norms or {}
        return {
            n["norm_id"]: n
            for n in payload.get("norms", [])
            if isinstance(n, dict) and "norm_id" in n
        }

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms_txt() -> str:
        """Agent discovery: what this service is and how to consume it."""
        skill = _PROJECT_ROOT / "SKILL.md"
        header = (
            "# TERE4AI v2\n"
            "Evidence-gated EU AI Act engineering support. Deterministic risk "
            "classification (with Article 27(1) FRIA applicability in "
            "answer.fria), judged requirements with span-level citations, "
            "evidence evaluation behind a runtime grounding judge. Not legal "
            "advice; never claims compliance.\n\n"
            "Endpoints: POST /api/classify, /api/requirements, /api/explain, "
            "/api/trace, /api/trace/batch and GET /api/span/{span_id}, "
            "/api/demo/sessions, /api/demo/sessions/{name} "
            "(free, deterministic); "
            "POST /api/evidence, /api/backlog, /api/elicit (paid model calls, marked with "
            "X-TERE4AI-Paid-Call); GET /api/health.\n"
            "Input schema: schema/json_schemas/system_features.schema.json\n\n"
        )
        return header + (skill.read_text(encoding="utf-8") if skill.exists() else "")

    @app.get("/.well-known/tere4ai.json")
    def well_known(request: Request) -> JSONResponse:
        """Machine-readable discovery document."""
        return JSONResponse(
            content={
                "name": "tere4ai",
                "version": "2.0.0a0",
                "graph_version": _graph_version(request),
                "status_vocabulary": list(STATUS_VOCABULARY),
                "endpoints": {
                    "classify": {"method": "POST", "path": "/api/classify", "paid": False},
                    "requirements": {
                        "method": "POST",
                        "path": "/api/requirements",
                        "paid": False,
                    },
                    "explain": {"method": "POST", "path": "/api/explain", "paid": False},
                    "trace": {"method": "POST", "path": "/api/trace", "paid": False},
                    "trace_batch": {
                        "method": "POST",
                        "path": "/api/trace/batch",
                        "paid": False,
                    },
                    "span": {
                        "method": "GET",
                        "path": "/api/span/{span_id}",
                        "paid": False,
                    },
                    "demo_sessions": {
                        "method": "GET",
                        "path": "/api/demo/sessions",
                        "paid": False,
                    },
                    "demo_session": {
                        "method": "GET",
                        "path": "/api/demo/sessions/{name}",
                        "paid": False,
                    },
                    "schema_system_features": {
                        "method": "GET",
                        "path": "/api/schema/system_features",
                        "paid": False,
                    },
                    "coverage": {"method": "GET", "path": "/api/coverage", "paid": False},
                    "alignments": {"method": "GET", "path": "/api/alignments", "paid": False},
                    "report": {"method": "POST", "path": "/api/report", "paid": False},
                    "evidence": {"method": "POST", "path": "/api/evidence", "paid": True},
                    "backlog": {"method": "POST", "path": "/api/backlog", "paid": True},
                    "elicit": {"method": "POST", "path": "/api/elicit", "paid": True},
                    "health": {"method": "GET", "path": "/api/health", "paid": False},
                },
                "skill": "/llms.txt",
                "non_legal_advice_notice": (
                    "TERE4AI provides engineering and documentation support. It "
                    "does not certify EU AI Act compliance and does not replace "
                    "legal review, conformity assessment, or competent-authority "
                    "interpretation."
                ),
            }
        )

    @app.get("/api/health")
    def health(request: Request) -> JSONResponse:
        error = request.app.state.load_error
        if error is not None:
            return JSONResponse(status_code=503, content={"ok": False, "error": error})
        norms_build = str(
            (request.app.state.norms or {}).get("build", {}).get("build_id", "unknown")
        )
        return JSONResponse(
            content={
                "ok": True,
                "graph_version": _graph_version(request),
                "norms_build": norms_build,
            }
        )

    @app.get("/api/schema/system_features")
    def features_schema(request: Request) -> JSONResponse:
        # The dashboard validates project features against THIS document
        # (spec A8): serving it, rather than letting consumers vendor a
        # copy, is what keeps both sides of the wire on one contract.
        schema = request.app.state.features_schema
        if schema is None:
            return JSONResponse(
                status_code=503,
                content={"error": "features schema unavailable on this checkout"},
            )
        return JSONResponse(
            content={
                "schema": schema,
                "schema_sha256": request.app.state.features_schema_sha256,
                "graph_version": _graph_version(request),
            }
        )

    @app.get("/api/coverage")
    def coverage(request: Request) -> JSONResponse:
        # Deterministic and free: the M1 structural coverage view.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        payload = coverage_report(
            request.app.state.dump,
            norms_payload=request.app.state.norms,
            alignments_payload=request.app.state.alignments,
        )
        return JSONResponse(content=_sanitize_non_finite(payload))

    @app.post("/api/classify")
    def classify(request: Request, body: ClassifyRequest) -> JSONResponse:
        # Deterministic and free; invalid features come back as a
        # not_applicable envelope with the schema errors in missing_facts.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        envelope = classify_tool.classify_ai_system(body.features, request.app.state.dump)
        return JSONResponse(content=envelope)

    @app.post("/api/requirements")
    def requirements(request: Request, body: RequirementsRequest) -> JSONResponse:
        # Deterministic and free; consumes the /api/classify envelope.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        envelope = requirements_tool.get_applicable_requirements(
            body.classification,
            request.app.state.norms,
            request.app.state.dump,
            actor=body.actor,
        )
        return JSONResponse(content=envelope)

    def _alignments_unavailable(request: Request) -> JSONResponse | None:
        if request.app.state.alignments is not None:
            return None
        return JSONResponse(
            status_code=503,
            content={
                "error": "alignments payload unavailable: missing or unreadable "
                "alignments_core.json; build it with python -m tere4ai.align_hleg_altai"
            },
        )

    @app.get("/api/alignments")
    def alignments(request: Request) -> JSONResponse:
        # Corpus-wide accepted HLEG assertions plus the accepted norms
        # that have none: absence is also reviewable (spec, Reviewer).
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        missing_alignments = _alignments_unavailable(request)
        if missing_alignments is not None:
            return missing_alignments
        assertions = (request.app.state.alignments or {}).get("assertions", [])
        accepted = [a for a in assertions if a.get("judge_verdict") == "accepted"]
        aligned_norm_ids = {a.get("source_norm_id") for a in accepted}
        accepted_norms = [
            n.get("norm_id")
            for n in (request.app.state.norms or {}).get("norms", [])
            if n.get("judge_verdict") == "accepted"
        ]
        orphans = [nid for nid in accepted_norms if nid not in aligned_norm_ids]
        return JSONResponse(
            content=_sanitize_non_finite(
                {
                    "graph_version": _graph_version(request),
                    "accepted": accepted,
                    "norms_without_alignment": orphans,
                }
            )
        )

    @app.post("/api/explain")
    def explain(request: Request, body: ExplainRequest) -> JSONResponse:
        # Deterministic and free; unknown norm ids come back as a clean
        # not_applicable envelope, never an exception.
        unavailable = _unavailable(request) or _alignments_unavailable(request)
        if unavailable is not None:
            return unavailable
        envelope = explain_tool.explain_requirement(
            body.norm_id,
            request.app.state.dump,
            request.app.state.norms,
            request.app.state.alignments,
        )
        return JSONResponse(content=envelope)

    @app.post("/api/trace")
    def trace(request: Request, body: TraceRequest) -> JSONResponse:
        # Deterministic and free; id may be a norm_id or an HLEG id.
        unavailable = _unavailable(request) or _alignments_unavailable(request)
        if unavailable is not None:
            return unavailable
        envelope = trace_tool.trace_alignment(
            body.id, request.app.state.alignments, request.app.state.dump
        )
        return JSONResponse(content=envelope)

    @app.post("/api/trace/batch")
    def trace_batch(request: Request, body: TraceBatchRequest) -> JSONResponse:
        # Deterministic and free; one trace_alignment envelope per unique id,
        # passed through unmodified (same Section 8 envelope as /api/trace).
        # An unknown id degrades to its own not_applicable envelope; it never
        # fails the whole batch.
        unavailable = _unavailable(request) or _alignments_unavailable(request)
        if unavailable is not None:
            return unavailable
        envelopes = {
            item_id: trace_tool.trace_alignment(
                item_id, request.app.state.alignments, request.app.state.dump
            )
            for item_id in dict.fromkeys(body.ids)
        }
        # Section 8: the batch wrapper is itself a user-facing response, so the
        # top-level object carries the legal notice and graph_version alongside
        # the per-item envelopes (each inner envelope is already a full Section
        # 8 envelope and is passed through unchanged).
        return JSONResponse(
            content={
                "envelopes": envelopes,
                "graph_version": _graph_version(request),
                "non_legal_advice_notice": NON_LEGAL_ADVICE_NOTICE,
            }
        )

    @app.get("/api/span/{span_id:path}")
    def span(request: Request, span_id: str) -> JSONResponse:
        # Deterministic and free; the snapshot slice is checksum-verified.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        try:
            resolved = resolve_span(
                span_id,
                request.app.state.dump,
                SNAPSHOTS_DIR,
                extra_nodes=request.app.state.hleg_nodes,
            )
        except SpanNotFoundError as exc:
            return JSONResponse(
                status_code=404, content={"error": str(exc), "span_id": span_id}
            )
        except SpanIntegrityError as exc:
            return JSONResponse(
                status_code=503, content={"error": str(exc), "span_id": span_id}
            )
        # Section 8: the span route is user-facing, so wrap the verified slice
        # in the same envelope the MCP resolve_span tool returns (make_envelope,
        # so both surfaces agree on answer, status, and the legal notice), then
        # merge the flat span fields back at the top level so existing consumers
        # that read span_id / text / sha256 directly keep working.
        envelope = make_envelope(
            answer={**resolved, "found": True},
            status="satisfied_with_evidence",
            graph_version=_graph_version(request),
            source_spans=[
                {
                    "span_id": resolved["span_id"],
                    "snapshot_file": resolved["snapshot_file"],
                    "snapshot_sha256": resolved["sha256"],
                    "start": resolved["start"],
                    "end": resolved["end"],
                }
            ],
        )
        return JSONResponse(content={**envelope, **resolved})

    @app.post("/api/evidence")
    def evidence(request: Request, body: EvidenceRequest) -> JSONResponse:
        # PAID: one generator call plus one runtime grounding judge call.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        norm = _norms_by_id(request).get(body.norm_id)
        if norm is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"unknown norm_id {body.norm_id!r}: not present in the "
                    "judged norms payload (norms_core.json)",
                    "norm_id": body.norm_id,
                },
            )
        try:
            generator, judge = _build_paid_clients()
        except ModelConfigError as exc:
            return JSONResponse(status_code=503, content={"error": str(exc)})
        try:
            envelope = evidence_tool.evaluate_project_evidence(
                norm,
                {
                    "artifact_type": body.artifact_type,
                    "content": body.content,
                    "artifact_id": body.artifact_id,
                },
                generator,
                judge,
                graph_version=_graph_version(request),
            )
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - clean payload, never a traceback
            return JSONResponse(
                status_code=502, content={"error": f"model call failed: {exc}"}
            )
        return JSONResponse(content=envelope, headers={PAID_HEADER: "true"})

    @app.post("/api/backlog")
    def backlog(request: Request, body: BacklogRequest) -> JSONResponse:
        # PAID: one generator call plus one runtime grounding judge call.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        norms_by_id = _norms_by_id(request)
        unknown = [norm_id for norm_id in body.norm_ids if norm_id not in norms_by_id]
        if unknown:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "unknown norm_ids: not present in the judged norms "
                    "payload (norms_core.json)",
                    "unknown_norm_ids": unknown,
                },
            )
        norms = [norms_by_id[norm_id] for norm_id in body.norm_ids]
        try:
            generator, judge = _build_paid_clients()
        except ModelConfigError as exc:
            return JSONResponse(status_code=503, content={"error": str(exc)})
        try:
            envelope = backlog_tool.generate_control_backlog(
                norms,
                body.system_context,
                generator,
                judge,
                # Facade-level cap; the tool notes any truncation, never silent.
                max_norms=MAX_BACKLOG_NORMS,
                graph_version=_graph_version(request),
            )
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - clean payload, never a traceback
            return JSONResponse(
                status_code=502, content={"error": f"model call failed: {exc}"}
            )
        return JSONResponse(content=envelope, headers={PAID_HEADER: "true"})

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

    @app.post("/api/report")
    def report(request: Request, body: ReportRequest) -> Response:
        # The thin facade route B41 anticipated: session JSONL in, the
        # self-contained audit-grade HTML out. Pure rendering, no state.
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", encoding="utf-8", delete=False
        ) as handle:
            handle.write(body.session_jsonl)
            tmp_path = Path(handle.name)
        try:
            result = ingest_inputs([tmp_path])
            html = render_report(
                result.exchanges,
                result.problems,
                source_names=result.source_names,
                header_flags=result.header_flags,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        return Response(content=html, media_type="text/html")

    return app


# Default instance for `uvicorn tere4ai.http_facade.app:app --port 8008`.
app = create_app()
