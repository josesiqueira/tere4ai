"""Thin HTTP facade for the M3 demo web UI.

@implements: DEC-08 (partial: also Section 8 hardening, rate limit and request log)
@grounded_by: REF-31

Loopback-only intent (architecture.md Section 9): the demo UI never touches
the database or model APIs directly. This facade calls the same pure
functions the MCP server exposes (classify_ai_system,
get_applicable_requirements, evaluate_project_evidence,
generate_control_backlog) over the versioned offline graph dumps.

Behavioral contract:
- The Layer 0+1 dump (layer1.json) and the judged norms payload
  (norms_core.json) are loaded once at startup. If either is missing, every
  endpoint returns a clean 503 JSON payload, never a traceback (no silent
  degradation, Section 13).
- /api/classify, /api/requirements, /api/explain, /api/trace, and
  /api/span/{span_id} are deterministic and free. /api/explain and /api/trace
  additionally need alignments_core.json (503 with a clean payload when it is
  missing); /api/span verifies the snapshot checksum before slicing.
- /api/evidence and /api/backlog perform PAID model calls (OpenAI generator
  plus Anthropic runtime grounding judge). Model clients are built lazily
  per request; a missing key surfaces the ModelConfigError message as a
  clean JSON error. Paid responses carry the header X-TERE4AI-Paid-Call.
- The backlog endpoint caps the norms used at MAX_BACKLOG_NORMS (10)
  regardless of the tool's own maximum; the cap is never silent (the tool
  notes the truncation in the answer).
- CORS is open only to the local demo UI origin (localhost:3111).
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.judge.config import ModelConfigError, load_model_config
from tere4ai.mcp_server import backlog as backlog_tool
from tere4ai.mcp_server import classify as classify_tool
from tere4ai.mcp_server import evidence as evidence_tool
from tere4ai.mcp_server import explain as explain_tool
from tere4ai.mcp_server import requirements as requirements_tool
from tere4ai.mcp_server import trace as trace_tool
from tere4ai.mcp_server.spans import (
    SpanIntegrityError,
    SpanNotFoundError,
    resolve_span,
)
from tere4ai.mcp_server.tools import STATUS_VOCABULARY

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
            "/api/trace and GET /api/span/{span_id} (free, deterministic); "
            "POST /api/evidence, /api/backlog (paid model calls, marked with "
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
                    "span": {
                        "method": "GET",
                        "path": "/api/span/{span_id}",
                        "paid": False,
                    },
                    "evidence": {"method": "POST", "path": "/api/evidence", "paid": True},
                    "backlog": {"method": "POST", "path": "/api/backlog", "paid": True},
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
        return JSONResponse(content=resolved)

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

    return app


# Default instance for `uvicorn tere4ai.http_facade.app:app --port 8008`.
app = create_app()
