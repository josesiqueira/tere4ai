"""Thin HTTP facade for the MILESTONE3 demo web UI.

@implements: DEC-08 (partial: also Section 8 hardening, rate limit and request log)
@implements: DEC-17
@implements: DEC-19
@implements: DEC-23
@implements: DEC-24
@implements: DEC-25
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
- GET /api/schema/system_features serves the dashboard's feature-input JSON
  Schema plus a sha256 digest of the on-disk file and the graph_version, so
  a consumer can detect drift (503 when the schema file is missing or
  unreadable).
- GET /api/coverage and GET /api/alignments are deterministic and free: the
  MILESTONE1 structural coverage view and the corpus-wide accepted HLEG assertions
  plus the accepted norms that have none (alignments additionally needs
  alignments_core.json, same clean 503 as /api/explain).
- GET /api/units is deterministic and free: the Layer 2 annotation queue,
  every core source unit (dump order) with every candidate norm and its
  judge run, whatever their verdict. 503 when core_nodes.txt is missing
  (B77 plan 1).
- POST /api/report is a pure, stateless render: session JSONL in, the
  self-contained audit-grade HTML report out (422 on empty or oversized
  input).
- /api/evidence and /api/backlog perform PAID model calls (OpenAI generator
  plus Anthropic runtime grounding judge). /api/elicit performs a PAID
  generator call (fact elicitation, no judge). Model clients are built lazily
  per request; a missing key surfaces the ModelConfigError message as a
  clean JSON error. Paid responses carry the header X-TERE4AI-Paid-Call.
- GET /api/demo/sessions and /api/demo/sessions/{name}: read-only demo replay
  data, enabled only when TERE4AI_DEMO_SESSIONS_DIR is set.
- The backlog endpoint passes every norm through; there is no cap
  (2026-09-08, B71).
- DEC-24: POST /api/backlog/judge (PAID: one demo judge call) takes the
  request's fields with a signed record and its signature; it verifies the
  signature, refuses a demo judge equal to the record's generator, a loaded
  build other than the signed one and any field that differs from the
  record (409 or 422, model_called false), then runs the runtime grounding
  judge as the inline path would on the verified core and returns the
  judge's part only, judge_setting "demo".
- DEC-24: /api/backlog takes judge "inline" (the default,
  the answer above byte for byte) or "on_demand": the generator and the
  tool's mechanical checks run, no judge request is made, and the answer
  (status requires_human_review, judge_verdict "not_checked") carries a
  record signed with TERE4AI_ANSWER_SIGNING_KEY for its caller and
  generation. An on-demand request names the norms build it expects
  (another loaded build: 409) and its caller. Each mode loads only what it
  calls; every refusal before any model call carries model_called false;
  /api/health reports each route's readiness apart (routes).
- CORS is open only to the local demo UI origin (localhost:3111).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, model_validator

from tere4ai.align_hleg.hleg_source import served_hleg
from tere4ai.eval.evaluation_record import RECORD_FILE_STEM as _EVAL_REF_RE
from tere4ai.eval.evaluation_record import EvaluationRecordStore, reduce_paths
from tere4ai.eval.present_evaluation import (
    ORDER_SENTENCE,
    group_summaries,
    present_evaluation,
    synthesise_legacy_evaluations,
    unreadable_row,
)
from tere4ai.eval.present_evaluation import summary_of as evaluation_summary_of
from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIDemoJudge, OpenAIGenerator
from tere4ai.extract_norms.recorded import extraction_generator_settings
from tere4ai.extract_norms.requirement_type import JUDGE_VIEW_FIELDS, carried
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import (
    exception_reason,
    present_record,
    summary_of,
    synthesise_legacy_records,
    unreadable,
)
from tere4ai.graph_store.publication import load_active, read_target_state
from tere4ai.http_facade.signed import RecordError, build_record, sha256_text, sign, verify
from tere4ai.judge.config import (
    ModelConfigError,
    load_demo_judge_config,
    load_dotenv_once,
    load_generator_config,
    load_model_config,
    load_signing_key,
    route_readiness,
    runtime_judge_declaration,
)
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
from tere4ai.report.render import render_report_from_paths

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DUMP_DIR = _PROJECT_ROOT / "data" / "graph_dumps"
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"
DUMP_DIR_ENV = "TERE4AI_DUMP_DIR"
FEATURES_SCHEMA_PATH = (
    _PROJECT_ROOT / "schema" / "json_schemas" / "system_features.schema.json"
)

# Default facade port for the demo flow (README, web/src/app/assess).
FACADE_PORT = 8008

# The demo UI's local origin; the facade is loopback-intended, so nothing else.
ALLOWED_ORIGINS = ("http://localhost:3111", "http://127.0.0.1:3111")

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


# Section 13 guard shared by every request model (B63). JSON allows an
# escaped lone UTF-16 surrogate such as "\ud800"; it parses to a Python str
# that cannot be encoded as UTF-8, so it passes Pydantic untouched and only
# fails later, in the response encoder or in the error-detail encoder, as an
# uncaught UnicodeEncodeError (a raw 500). Same class as the NaN/Infinity
# hole closed by _sanitize_non_finite. The guard walks the raw body once,
# before field validation, so a surrogate nested in a free dict or a list is
# caught the same way as one in a top-level string field.
UNENCODABLE_STRING_MESSAGE = "string is not UTF-8 encodable (lone surrogate rejected)"


def _is_utf8_encodable(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


MAX_BODY_DEPTH = 100
TOO_DEEP_MESSAGE = f"the request body is nested more than {MAX_BODY_DEPTH} levels deep"


def _reject_unencodable(value: Any) -> None:
    """Raise ValueError if any string anywhere in value is not UTF-8, or if
    the value is nested more than MAX_BODY_DEPTH levels (a deeper body would
    exhaust the recursion limit of later steps: a 422, never a 500, R68).
    Iterative, so the guard itself cannot run out of recursion depth."""
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, str):
            if not _is_utf8_encodable(item):
                raise ValueError(UNENCODABLE_STRING_MESSAGE)
        elif isinstance(item, (dict, list, tuple)):
            if depth >= MAX_BODY_DEPTH:
                raise ValueError(TOO_DEEP_MESSAGE)
            if isinstance(item, dict):
                for key, child in item.items():
                    stack.append((key, depth + 1))
                    stack.append((child, depth + 1))
            else:
                stack.extend((child, depth + 1) for child in item)


class _Utf8GuardedModel(BaseModel):
    """Base for every facade request model: rejects unencodable strings at
    the door so they surface as a 422 with the other validation errors."""

    @model_validator(mode="before")
    @classmethod
    def _guard_utf8(cls, data: Any) -> Any:
        _reject_unencodable(data)
        return data


class ClassifyRequest(_Utf8GuardedModel):
    features: dict[str, Any]


class RequirementsRequest(_Utf8GuardedModel):
    classification: dict[str, Any]
    actor: str | None = None


class ElicitRequest(_Utf8GuardedModel):
    # The MCP tool elicit_features applies the same floor (B10).
    description: str = Field(min_length=elicit_tool.MIN_DESCRIPTION_CHARS)


class Caller(_Utf8GuardedModel):
    """DEC-24: who asked for a generator-only answer: the dashboard's
    project, its repository run and, for evidence, the document."""

    project: str = Field(min_length=1, max_length=200)
    repository_run: str = Field(min_length=1, max_length=200)
    document: str | None = Field(default=None, max_length=200)


class _JudgeMode(_Utf8GuardedModel):
    """DEC-24: inline (the default, today's answer) or on_demand, which names
    the norms build it expects and its caller."""

    judge: Literal["inline", "on_demand"] = "inline"
    expected_norms_build: str | None = Field(default=None, max_length=200)
    caller: Caller | None = None

    @model_validator(mode="after")
    def _on_demand_names_its_build_and_caller(self) -> _JudgeMode:
        if self.judge == "on_demand" and (self.expected_norms_build is None or self.caller is None):
            raise ValueError("judge on_demand needs expected_norms_build and caller")
        return self


class EvidenceRequest(_Utf8GuardedModel):
    norm_id: str
    artifact_type: str
    content: str
    artifact_id: str | None = None


class BacklogRequest(_JudgeMode):
    norm_ids: list[str] = Field(min_length=1)
    system_context: str


class _Signed(_Utf8GuardedModel):
    """DEC-24: the signed record and signature an on-demand answer carried."""

    signed_record: dict[str, Any]
    signature: str = Field(max_length=200)


class BacklogJudgeRequest(_Signed):
    norm_ids: list[str] = Field(min_length=1)
    system_context: str


class ExplainRequest(_Utf8GuardedModel):
    norm_id: str
    # B132: the source unit's 2024 wording beside the in-force text, on request.
    earlier_version: bool = False


class TraceRequest(_Utf8GuardedModel):
    id: str


class TraceBatchRequest(_Utf8GuardedModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_TRACE_BATCH_IDS)


class ReportRequest(_Utf8GuardedModel):
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


def _sanitize_unencodable(value: Any) -> Any:
    """Replace strings that are not UTF-8 encodable anywhere in a
    validation-error payload with an honest placeholder.

    Pydantic echoes the offending input back in the error detail, so a lone
    surrogate rejected by _Utf8GuardedModel (or by any other validator)
    would otherwise crash the response encoder exactly as it crashed the
    route. Dict keys are sanitized too, since the raw body's keys are part
    of the echoed input.
    """
    if isinstance(value, str):
        return value if _is_utf8_encodable(value) else "unencodable string rejected"
    if isinstance(value, dict):
        return {_sanitize_unencodable(key): _sanitize_unencodable(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_unencodable(v) for v in value]
    return value


def _build_paid_clients() -> tuple[Any, Any]:
    """Construct the real generator and judge lazily, per paid request.

    Raises ModelConfigError when keys or model ids are missing; the caller
    turns that into a clean JSON error, never a traceback.
    """
    cfg = load_model_config()
    return OpenAIGenerator(cfg), AnthropicJudge(cfg)


def create_app(dump_dir: Path | str | None = None, eval_root: Path | str | None = None) -> FastAPI:
    """Facade app factory. dump_dir overrides the graph dump location
    (also settable via the TERE4AI_DUMP_DIR environment variable). eval_root
    overrides the checkout root the evaluation routes read eval/ and docs/
    legacy files from (also settable via TERE4AI_EVAL_ROOT)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        base = Path(dump_dir or os.environ.get(DUMP_DIR_ENV) or DEFAULT_DUMP_DIR)
        # One loader for the facade and the MCP server (D-G21): the activated
        # publication when ACTIVE_MANIFEST.json exists (verified, a drifted
        # file refusing service), else the legacy files under the directory's
        # chain (B74). Loaded once here: a restart is the only way the facade
        # changes builds.
        loaded = load_active(base)
        app.state.dump, app.state.norms, app.state.alignments = loaded.dump, loaded.norms, loaded.alignments
        app.state.served_source = loaded.source
        app.state.dump_dir = base
        app.state.eval_root = Path(eval_root or os.environ.get("TERE4AI_EVAL_ROOT") or _PROJECT_ROOT)
        core_path = base / "core_nodes.txt"
        app.state.core_nodes = (
            [n.strip() for n in core_path.read_text(encoding="utf-8").split(",") if n.strip()]
            if core_path.is_file()
            else None
        )
        app.state.served_hleg = served_hleg(loaded.dump)
        try:
            raw = FEATURES_SCHEMA_PATH.read_bytes()
            app.state.features_schema = json.loads(raw)
            # Digest over the on-disk file bytes, not the served JSON body: a
            # version token for consumers to detect drift, not something
            # reproducible by re-hashing the response's "schema" field.
            app.state.features_schema_sha256 = hashlib.sha256(raw).hexdigest()
        except (OSError, json.JSONDecodeError):
            app.state.features_schema = None
            app.state.features_schema_sha256 = None
        missing = [
            name
            for name, payload in (("layer1.json", app.state.dump), ("norms_core.json", app.state.norms))
            if payload is None
        ]
        # Name the files, not the absolute server directory (audit W4).
        app.state.load_error = loaded.error or (
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
        # and unencodable strings sanitized before encoding. A NaN/Infinity/-Infinity JSON literal in
        # the request body parses fine, Pydantic rejects it and echoes the
        # value into exc.errors(), and the strict response encoder used
        # below would otherwise raise ValueError and surface as an uncaught
        # 500 (the bug this handler closes; Section 13, no silent
        # degradation, but never a raw 500 either).
        # Unencodable strings (lone surrogates, B63) get the same treatment:
        # the echoed input would crash the encoder just like a NaN would.
        try:
            errors = _sanitize_unencodable(_sanitize_non_finite(jsonable_encoder(exc.errors())))
        except RecursionError:
            # A deeply nested body echoed as the error's input would exhaust
            # the encoder: answer without the echoed input (R68).
            errors = [{"type": e.get("type"), "loc": [str(x) for x in e.get("loc", ())], "msg": e.get("msg")}
                      for e in exc.errors()]
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
                    # B138 fix wave W4: answered before any model call, and
                    # said, so a paid caller records it as not billed.
                    content={"error": "rate limit exceeded", "limit_per_minute": limit, "model_called": False},
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

    def _norms_build(request: Request) -> str:
        return str((request.app.state.norms or {}).get("build", {}).get("build_id", "unknown"))

    def _before_any_model_call(status: int, content: dict[str, Any]) -> JSONResponse:
        """DEC-24 (spec G D-G74 (2), ruling S69): a refusal of an on-demand
        or judge request before any model call says so."""
        return JSONResponse(status_code=status, content={**content, "model_called": False})

    def _build_refusal(request: Request, body: _JudgeMode) -> JSONResponse | None:
        """On demand, the expected norms build first, before any norm is
        looked up (ruling R69): a norm unknown to another build reads as the
        build it is."""
        loaded = _norms_build(request)
        if body.judge != "on_demand" or body.expected_norms_build == loaded:
            return None
        return _before_any_model_call(409, {
            "error": f"the facade has loaded norms build {loaded}, not the expected {body.expected_norms_build}",
            "loaded_norms_build": loaded, "expected_norms_build": body.expected_norms_build})

    def _on_demand_refusal(request: Request, body: _JudgeMode) -> tuple[JSONResponse | None, Any, bytes]:
        """The on-demand preconditions after the build: the generator's
        configuration, the signing key; the generator client and the key
        when both hold."""
        try:
            generator = OpenAIGenerator(load_generator_config())
            key = load_signing_key()
        except ModelConfigError as exc:
            return _before_any_model_call(503, {"error": str(exc)}), None, b""
        return None, generator, key

    def _signed(request: Request, envelope: dict[str, Any], *, route: str, caller: Caller, norm_ids: list[str],
                untrusted_text: str, core: dict[str, Any], key: bytes) -> dict[str, Any]:
        """A not-checked answer gains its signed record and signature
        (spec G D-G74 (3)); a degraded one is returned as it is."""
        if envelope.get("judge_verdict") != evidence_tool.NOT_CHECKED:
            return envelope
        answer = envelope["answer"]
        try:
            record = build_record(
                route=route, caller=caller.model_dump(), norm_ids=norm_ids, graph_version=_graph_version(request),
                norms_build=_norms_build(request), generator_model=answer["generator_model"],
                generator_prompt={"name": answer["generator_prompt"], "version": answer["generator_prompt_version"]},
                judge_prompt={"name": answer["judge_prompt"], "version": answer["judge_prompt_version"]},
                untrusted_text=untrusted_text, core=core)
            signature = sign(record, key)
        except (RecordError, RecursionError, KeyError, TypeError, ValueError) as exc:
            # Ruling R68: the generator was called and billed; its answer is
            # returned as it is, unsigned, so it cannot be judged, never a
            # 500 the caller would read as a refusal before any model call.
            answer["unsigned_reason"] = f"the facade could not sign this answer: {exception_reason(exc)}"
            return envelope
        answer["signed_record"] = record
        answer["signature"] = signature
        return envelope

    @app.get("/llms.txt", response_class=PlainTextResponse)
    def llms_txt() -> str:
        """Agent discovery: what this service is and how to consume it."""
        skill = _PROJECT_ROOT / "SKILL.md"
        header = (
            "# TERE4AI v2\n"
            "Evidence-gated EU AI Act engineering support. Deterministic risk "
            "classification (with Article 27(1) FRIA applicability in "
            "answer.fria), judged requirements with span-level citations, "
            "evidence evaluation behind a runtime grounding judge. "
            + NON_LEGAL_ADVICE_NOTICE
            + "\n\n"
            "Endpoints: POST /api/classify, /api/requirements, /api/explain, "
            "/api/trace, /api/trace/batch, /api/report and GET /api/span/{span_id}, "
            "/api/coverage, /api/alignments, /api/schema/system_features, "
            "/api/demo/sessions, /api/demo/sessions/{name} "
            "(free, deterministic); "
            "POST /api/evidence, /api/backlog, /api/elicit (paid model calls, marked with "
            "X-TERE4AI-Paid-Call); GET /api/health.\n"
            "POST /api/backlog with judge on_demand: the generator alone, a signed answer; "
            "POST /api/backlog/judge: a demo judge of the generator's family on that signed "
            "answer (paid, DEC-24)\n"
            "GET /api/builds, GET /api/builds/{ref}: the build records, free, read per request\n"
            "GET /api/evaluations, GET /api/evaluations/{ref}: the evaluation records (E1, E6), "
            "free, read per request\n"
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
                    "units": {"method": "GET", "path": "/api/units", "paid": False},
                    "builds": {"method": "GET", "path": "/api/builds", "paid": False},
                    "build": {"method": "GET", "path": "/api/builds/{ref}", "paid": False},
                    "evaluations": {"method": "GET", "path": "/api/evaluations", "paid": False},
                    "evaluation": {"method": "GET", "path": "/api/evaluations/{ref}", "paid": False},
                    "report": {"method": "POST", "path": "/api/report", "paid": False},
                    "evidence": {"method": "POST", "path": "/api/evidence", "paid": True},
                    "backlog": {"method": "POST", "path": "/api/backlog", "paid": True},
                    "backlog_judge": {"method": "POST", "path": "/api/backlog/judge", "paid": True},
                    "elicit": {"method": "POST", "path": "/api/elicit", "paid": True},
                    "health": {"method": "GET", "path": "/api/health", "paid": False},
                },
                "skill": "/llms.txt",
                "non_legal_advice_notice": NON_LEGAL_ADVICE_NOTICE,
            }
        )

    @app.get("/api/health")
    def health(request: Request) -> JSONResponse:
        load_dotenv_once()
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
                # spec F D-F29: the runtime judge's model id from the
                # environment, after the same .env load the paid path makes,
                # and its declared effort and temperature from
                # config/model_parameters.json, read on every poll; null
                # values with the refusal sentence when the table does not
                # declare it. The dashboard's judge runner compares them with
                # its own price table row for the same model id.
                "runtime_judge": runtime_judge_declaration(os.environ.get("TERE4AI_JUDGE_MODEL") or None),
                # DEC-24 (spec G D-G74 (2), ruling S68): each route's
                # readiness apart; the signing key present or missing, never
                # its value.
                "routes": route_readiness(),
            }
        )

    @app.get("/api/schema/system_features")
    def features_schema(request: Request) -> JSONResponse:
        # The dashboard validates project features against THIS document
        # (spec B revision A8): serving it, rather than letting consumers
        # vendor a copy, is what keeps both sides of the wire on one contract.
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
        # Deterministic and free: the MILESTONE1 structural coverage view.
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
                "alignments_core.json; build it with python -m tere4ai.align_hleg"
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

    @app.get("/api/units")
    def units(request: Request) -> JSONResponse:
        # B77 plan 1: the Layer 2 annotation queue. Every core source unit in
        # the Act's order with EVERY candidate norm and its judge run,
        # rejected and pending included: the annotators' object of work is
        # the model's proposal, so this is the one endpoint that serves
        # judge opinions to the dashboard on purpose (spec G Section 4).
        # Deterministic and free.
        unavailable = _unavailable(request)
        if unavailable is not None:
            return unavailable
        core = request.app.state.core_nodes
        if not core:
            return JSONResponse(status_code=503, content={"error": "core node list unavailable"})
        from tere4ai.extract_norms.pipeline import expand_source_units

        dump = request.app.state.dump or {}
        norms_payload = request.app.state.norms or {}
        runs = {r.get("id"): r for r in norms_payload.get("judge_runs", []) if isinstance(r, dict)}
        by_unit: dict[str, list[dict[str, Any]]] = {}
        for norm in norms_payload.get("norms", []):
            if not isinstance(norm, dict):
                continue
            run = runs.get(norm.get("judge_run_id")) or {}
            candidate = {
                key: norm.get(key)
                for key in (
                    "norm_id", "deontic_type", "modal", "actor_explicit", "actor_inferred",
                    "actor_inference_source_node_id", "action", "object", "conditions",
                    "exceptions", "lifecycle_phase_ids", "extractor_model",
                    "extractor_prompt_version", "judge_verdict", "review_status",
                )
            }
            # DEC-19: the type when the norm carries it (a build before DEC-19
            # has none, and no reader invents a null for it).
            candidate.update(carried(norm, ("requirement_type",)))
            # Spec F D-F22, D-F29: the extractor named with its effort and
            # temperature, from the dump's build block; null when unrecorded.
            candidate["extractor_effort"], candidate["extractor_temperature"] = extraction_generator_settings(norms_payload, norm)
            candidate["judge"] = {
                "run_id": norm.get("judge_run_id"),
                "model": run.get("judge_model"),
                # B84 (spec F D-F22): the judge effort outcome, null for a
                # pre-B84 dump, never invented.
                "effort": run.get("judge_effort"),
                # B99 (spec F D-F29): the declared temperature, null for a dump made before it
                "temperature": run.get("judge_temperature"),
                "prompt_version": run.get("prompt_version"),
                "verdict": run.get("verdict"),
                "scores": run.get("scores"),
                "rationale": run.get("rationale"),
                # D-G39: the lineage hop names the judge run's time and, where
                # the dump records it (since B74), its prompt hash; null
                # otherwise, never invented.
                "completed_at": run.get("completed_at"),
                "prompt_sha256": run.get("prompt_sha256"),
                "prompt_sha256_reason": trace_tool.prompt_hash_reason(run),
                # DEC-19: the judge's recorded view of the type, served here
                # with the judge's other opinions; spec G D-G54 keeps it from
                # the annotators' screen in every mode.
                **carried(run, JUDGE_VIEW_FIELDS),
            }
            by_unit.setdefault(str(norm.get("source_node_id")), []).append(candidate)
        units_out = []
        for unit in expand_source_units(dump, core):
            node_id = unit["node_id"]
            units_out.append({
                "id": node_id,
                "type": unit["node_type"],
                "span_id": unit.get("span_id"),
                "article_id": ":".join(node_id.split(":")[:2]),
                "text": unit.get("text") or "",
                "candidates": by_unit.get(node_id, []),
            })
        return JSONResponse(content=_sanitize_non_finite({
            "graph_version": _graph_version(request),
            "core_nodes": core,
            "units": units_out,
        }))

    _BUILD_REF_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

    def _served_chain(request: Request) -> str | None:
        gv = _graph_version(request)
        return gv.split("+chain-", 1)[1] if "+chain-" in gv else None

    def _synthesised(request: Request) -> list[dict[str, Any]]:
        return synthesise_legacy_records(request.app.state.dump_dir)

    @app.get("/api/builds")
    def builds(request: Request) -> JSONResponse:
        # Spec G 3.1, D-G19, D-G25: the build records read per request,
        # never cached, every figure dated; nothing is created on a read.
        dump_dir = request.app.state.dump_dir
        now = datetime.now(UTC)
        served = _served_chain(request)
        store = BuildRecordStore(dump_dir, create=False)
        summaries: list[dict[str, Any]] = []
        # Spec 7(b): one unreadable record or artefact never fails the list;
        # it is its own unreadable row with the reason.
        for record in [*store.list_records(), *_synthesised(request)]:
            if record.get("unreadable"):
                summaries.append(summary_of(record))
                continue
            try:
                summaries.append(summary_of(present_record(record, dump_dir, now, served, store)))
            except Exception as exc:  # noqa: BLE001 - reported as the record's row, never a 500
                summaries.append(summary_of(unreadable(record["record_id"], exception_reason(exc))))
        return JSONResponse(content=_sanitize_non_finite({
            "schema_version": "builds_list.v1", "graph_version": _graph_version(request),
            "observed_at": now.isoformat(), "served_chain_id": served,
            "publication_target": read_target_state(dump_dir), "builds": summaries,
        }))

    @app.get("/api/builds/{ref}")
    def build_detail(ref: str, request: Request) -> JSONResponse:
        if not _BUILD_REF_RE.match(ref):
            return JSONResponse(status_code=422, content={"error": "build reference has characters outside [A-Za-z0-9._-]"})
        dump_dir = request.app.state.dump_dir
        store = BuildRecordStore(dump_dir, create=False)
        now = datetime.now(UTC)
        served = _served_chain(request)
        # B81 item 17: the reason names the file, never its path on the server
        try:
            record_id = store.resolve(ref)
            record = store.read(record_id) if record_id is not None else None
        except Exception as exc:  # noqa: BLE001 - an unreadable record or alias index is reported, never a 500
            return JSONResponse(status_code=404, content={"error": f"build record {ref} is unreadable: {exception_reason(exc)}"})
        if record is not None:
            return _presented_or_404(ref, record, dump_dir, now, served, store)
        for record in _synthesised(request):
            if record["record_id"] == ref or ref in record.get("aliases", []):
                if record.get("unreadable"):
                    return JSONResponse(status_code=404, content={"error": f"build record {ref} is unreadable: {record['reason']}"})
                return _presented_or_404(ref, record, dump_dir, now, served, store)
        return JSONResponse(status_code=404, content={"error": f"no build record {ref}"})

    def _presented_or_404(ref, record, dump_dir, now, served, store) -> JSONResponse:
        try:
            presented = present_record(record, dump_dir, now, served, store)
        except Exception as exc:  # noqa: BLE001 - an unpresentable record is reported, never a 500
            return JSONResponse(status_code=404, content={"error": f"build record {ref} is unreadable: {exception_reason(exc)}"})
        return JSONResponse(content=_sanitize_non_finite(presented))

    def _evaluation_store(request: Request) -> EvaluationRecordStore:
        # read-only (D-G34): a GET never creates evaluation_records/
        return EvaluationRecordStore(request.app.state.dump_dir, create=False)

    @app.get("/api/evaluations")
    def evaluations(request: Request) -> JSONResponse:
        # Spec G D-G33, D-G34: the evaluation records read per request, never
        # cached, grouped by build identity, every row dated; nothing is
        # created on a read; an outage is an outage, never an empty list.
        now = datetime.now(UTC)
        store = _evaluation_store(request)
        try:
            stored = store.list_records()
        except OSError as exc:
            return JSONResponse(status_code=503, content={"error": f"evaluation records unavailable: {exception_reason(exc)}"})
        rows: list[dict[str, Any]] = []
        for record in [*stored, *synthesise_legacy_evaluations(request.app.state.eval_root, store)]:
            if record.get("unreadable"):
                rows.append(unreadable_row(record["record_id"], reduce_paths(record["reason"])))
                continue
            try:
                rows.append(evaluation_summary_of(present_evaluation(record, store, now)))
            except Exception as exc:  # noqa: BLE001 - reported as the record's row, never a 500
                rows.append(unreadable_row(record["record_id"], exception_reason(exc)))
        return JSONResponse(content=_sanitize_non_finite({
            "schema_version": "evaluations_list.v1", "observed_at": now.isoformat(),
            "served_build_id": _graph_version(request), "order": ORDER_SENTENCE, "groups": group_summaries(rows),
        }))

    @app.get("/api/evaluations/{ref}")
    def evaluation_detail(ref: str, request: Request) -> JSONResponse:
        if not _EVAL_REF_RE.match(ref):
            return JSONResponse(status_code=422, content={"error": "evaluation record reference outside the id syntax"})
        store = _evaluation_store(request)
        now = datetime.now(UTC)
        if (store.dir / f"{ref}.json").is_file():
            return _evaluation_or_404(ref, lambda: store.read(ref), store, now)
        for record in synthesise_legacy_evaluations(request.app.state.eval_root, store):
            if record["record_id"] == ref:
                if record.get("unreadable"):
                    return JSONResponse(status_code=404, content={"error": f"evaluation record {ref} is unreadable: {reduce_paths(record['reason'])}"})
                return _evaluation_or_404(ref, lambda record=record: record, store, now)
        return JSONResponse(status_code=404, content={"error": f"no evaluation record {ref}"})

    def _evaluation_or_404(ref, read, store, now) -> JSONResponse:
        # read and present inside one boundary (G6): presenting hashes the
        # output copies, so an unreadable copy is a 404, never a 500
        try:
            presented = present_evaluation(read(), store, now)
        except Exception as exc:  # noqa: BLE001 - an unreadable record is reported, never a 500
            return JSONResponse(status_code=404, content={"error": f"evaluation record {ref} is unreadable: {exception_reason(exc)}"})
        return JSONResponse(content=_sanitize_non_finite(presented))

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
            earlier_version=body.earlier_version,
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
                extra_nodes=request.app.state.served_hleg.nodes,
                extra_refusal=request.app.state.served_hleg.refusal,
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

    def _backlog_on_demand(request: Request, body: BacklogRequest, norms: list[dict[str, Any]]) -> JSONResponse:
        # PAID: one generator call, no judge (DEC-24). B138 fix wave W4, W8:
        # the refusals before any model call are asked first and answered
        # with model_called false and no paid header; once the generator is
        # reached, every failure is a paid one, whatever its exception.
        refusal = backlog_tool.on_demand_refusal(norms, body.system_context)
        if refusal is not None:
            return _before_any_model_call(422, {"error": refusal})
        refused, generator, key = _on_demand_refusal(request, body)
        if refused is not None:
            return refused
        try:
            envelope = backlog_tool.generate_control_backlog_on_demand(
                norms, body.system_context, generator, graph_version=_graph_version(request))
        except Exception as exc:  # noqa: BLE001 - clean payload, never a traceback
            return JSONResponse(status_code=502, content={"error": f"model call failed: {exc}", "model_called": True})
        assert body.caller is not None  # the request model requires it on demand
        envelope = _signed(request, envelope, route="/api/backlog", caller=body.caller, norm_ids=list(body.norm_ids),
                           untrusted_text=body.system_context, core={"items": envelope["answer"].get("items")}, key=key)
        return JSONResponse(content=envelope, headers={PAID_HEADER: "true"})

    def _judge_refusal(request: Request, body: _Signed, route: str, sent: dict[str, Any]) -> tuple[JSONResponse | None, Any]:
        """The judge route's checks, all before any model call (spec G D-G74
        (3), (4), rulings S52, S69, S84): the demo judge's configuration and
        the signing key, the signature, a judge other than the record's
        generator, the loaded build, then every field sent apart from the
        record against it. The demo judge client when all hold."""
        try:
            key = load_signing_key()
            judge_cfg = load_demo_judge_config()
        except ModelConfigError as exc:
            return _before_any_model_call(503, {"error": str(exc)}), None
        record = body.signed_record
        if not verify(record, body.signature, key):
            return _before_any_model_call(422, {"error": "the answer's signature does not verify", "field": "signature"}), None
        if judge_cfg.model.strip().lower() == str(record["generator_model"]).strip().lower():
            return _before_any_model_call(422, {
                "error": f"the demo judge {judge_cfg.model!r} is the model that generated the answer", "field": "generator_model"}), None
        loaded = {"graph_version": _graph_version(request), "norms_build": _norms_build(request)}
        for field, value in loaded.items():
            if record[field] != value:
                return _before_any_model_call(409, {
                    "error": f"the answer was signed on {field} {record[field]}, and the facade has loaded {value}",
                    "field": field}), None
        if record["judge_prompt"]["name"] != "runtime_grounding":
            return _before_any_model_call(422, {"error": "the record names a judge prompt this route does not run", "field": "judge_prompt"}), None
        expected = {"route": route, **sent}
        actual = {"route": record["route"], **{field: (record["untrusted_sha256"] if field == "untrusted_sha256" else
                                                       record["norm_ids"] if field == "norm_ids" else record["core"].get(field))
                                               for field in sent}}
        for field in expected:
            if expected[field] != actual[field]:
                name = {"untrusted_sha256": "content" if route == "/api/evidence" else "system_context",
                        "norm_ids": "norm_id" if route == "/api/evidence" else "norm_ids"}.get(field, field)
                return _before_any_model_call(422, {"error": f"the {name} sent is not the one the answer was signed for", "field": name}), None
        return None, OpenAIDemoJudge(judge_cfg)

    def _judge_part_response(record: dict[str, Any], run: Any) -> JSONResponse:
        try:
            part = run()
        except Exception as exc:  # noqa: BLE001 - a failure before any judge request
            return _before_any_model_call(503, {"error": f"the judge could not start: {exception_reason(exc)}"})
        return JSONResponse(content={**part, "generation_id": record["generation_id"], "model_called": True},
                            headers={PAID_HEADER: "true"})

    @app.post("/api/backlog/judge")
    def backlog_judge(request: Request, body: BacklogJudgeRequest) -> JSONResponse:
        # PAID: one demo judge call on a signed generator-only backlog (DEC-24).
        unavailable = _unavailable(request)
        if unavailable is not None:
            return _before_any_model_call(503, json.loads(unavailable.body))
        refused, judge = _judge_refusal(request, body, "/api/backlog", {
            "untrusted_sha256": sha256_text(body.system_context), "norm_ids": sorted(body.norm_ids)})
        if refused is not None:
            return refused
        norms_by_id = _norms_by_id(request)
        unknown = [norm_id for norm_id in body.norm_ids if norm_id not in norms_by_id]
        if unknown:
            return _before_any_model_call(404, {"error": "unknown norm_ids", "unknown_norm_ids": unknown})
        record = body.signed_record
        return _judge_part_response(record, lambda: backlog_tool.judge_backlog_on_demand(
            [norms_by_id[norm_id] for norm_id in body.norm_ids], record["core"]["items"], body.system_context, judge,
            prompt_version=record["judge_prompt"]["version"]))

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
            if body.judge == "on_demand":
                return _before_any_model_call(503, json.loads(unavailable.body))
            return unavailable
        build = _build_refusal(request, body)
        if build is not None:
            return build
        norms_by_id = _norms_by_id(request)
        unknown = [norm_id for norm_id in body.norm_ids if norm_id not in norms_by_id]
        if unknown:
            content = {
                "error": "unknown norm_ids: not present in the judged norms "
                "payload (norms_core.json)",
                "unknown_norm_ids": unknown,
            }
            if body.judge == "on_demand":
                return _before_any_model_call(404, content)
            return JSONResponse(status_code=404, content=content)
        norms = [norms_by_id[norm_id] for norm_id in body.norm_ids]
        refusals = backlog_tool.deleted_source_refusals(norms, request.app.state.dump)
        if refusals:
            # B132: never a backlog from wording the Omnibus deleted; no model call.
            content = {"error": "; ".join(refusals.values()), "refused_norm_ids": list(refusals)}
            if body.judge == "on_demand":
                return _before_any_model_call(422, content)
            return JSONResponse(status_code=422, content=content)
        if body.judge == "on_demand":
            return _backlog_on_demand(request, body, norms)
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
            # B10: the prompt quotes the Act from the build this request
            # serves, and the answer names that build.
            envelope = elicit_tool.elicit_envelope(
                body.description,
                generator,
                dump=request.app.state.dump,
                snapshots_dir=SNAPSHOTS_DIR,
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
        # A stable basename (not a random temp name) so the rendered
        # report's provenance header and any description fallback read
        # "posted-session.jsonl", never a throwaway tmpXXXX name.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "posted-session.jsonl"
            tmp_path.write_text(body.session_jsonl, encoding="utf-8")
            html = render_report_from_paths([tmp_path])
        return Response(content=html, media_type="text/html")

    return app


# Default instance for `uvicorn tere4ai.http_facade.app:app --port 8008`.
app = create_app()
