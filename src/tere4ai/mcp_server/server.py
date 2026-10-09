"""FastMCP server exposing the read-only TERE4AI tools over the offline dumps.

Wraps the pure functions in tools.py, classify.py, requirements.py,
evidence.py, and backlog.py as read-only MCP tools (no write surface,
architecture.md Section 8). The Layer 0+1 dump is read from
data/graph_dumps/layer1.json and the judged norms payload from
data/graph_dumps/norms_core.json (versioned build artifacts); no running
Neo4j is required. If a dump has not been built, the tools return a
degraded envelope instead of failing silently (Section 13).

evaluate_project_evidence, evaluate_project_evidence_batch and
generate_control_backlog perform PAID model calls (OpenAI generator plus
Anthropic runtime grounding judge), and elicit_features one PAID generator
call (fact elicitation, no judge); their descriptions say so, and a missing
model configuration surfaces as a clean degraded envelope, never a
traceback. The four run their model part through replay.py: an identical
call inside the replay window (TERE4AI_MCP_REPLAY_WINDOW_SECONDS, default
600) returns the first answer with a note and pays nothing (C3 ruling R3).

Transport: stdio by default (Mode B, architecture.md Section 9). The
streamable HTTP transport for remote consumers sits behind an explicit
flag, TERE4AI_MCP_TRANSPORT=http, binding TERE4AI_MCP_HOST (default
127.0.0.1) and TERE4AI_MCP_PORT (default 8765). HTTP requests must carry
a scoped t4a_ API key as a Bearer token (keys.py; mint and revoke with
scripts/manage_mcp_keys.py); stdio stays keyless unless
TERE4AI_MCP_REQUIRE_KEY=1. Every tool call is metered body-free.

@implements: DEC-08, DEC-10
@implements: DEC-23
@implements: DEC-25
@grounded_by: REF-16, REF-17, REF-15, REF-31
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, NamedTuple

import mcp.types as mcp_types
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware
from mcp import MCPError

from tere4ai.align_hleg.hleg_source import served_hleg
from tere4ai.graph_store.build_chain import stamp_served_build
from tere4ai.graph_store.publication import (
    ACTIVE_POINTER,
    LoadedBuild,
    active_manifest,
    load_active,
)
from tere4ai.judge.config import ModelConfigError, load_model_config
from tere4ai.mcp_server import backlog as backlog_rules
from tere4ai.mcp_server import classify as classify_rules
from tere4ai.mcp_server import elicit as elicit_rules
from tere4ai.mcp_server import evidence as evidence_rules
from tere4ai.mcp_server import explain as explain_rules
from tere4ai.mcp_server import replay, tools
from tere4ai.mcp_server import requirements as requirements_rules
from tere4ai.mcp_server import spans as spans_rules
from tere4ai.mcp_server import trace as trace_rules
from tere4ai.mcp_server import trace_code as trace_code_rules

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DUMP_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "alignments_core.json"
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"

_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
# Paid tools stay read-only against the graph but reach external model APIs.
_READ_ONLY_PAID = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}

mcp = FastMCP(
    name="tere4ai",
    instructions=(
        "TERE4AI v2 tools over the EU AI Act graph: structural tools "
        "(coverage_report, source_trace) plus explanation and trace tools "
        "(explain_requirement, trace_alignment, resolve_span) plus "
        "runtime tools (classify_ai_system, get_applicable_requirements, "
        "trace_implementation, evaluate_project_evidence, "
        "evaluate_project_evidence_batch, generate_control_backlog) plus "
        "elicit_features, which proposes the facts classify_ai_system reads "
        "from a plain-text description. "
        "Read-only; evaluate_project_evidence, evaluate_project_evidence_batch, "
        "generate_control_backlog and elicit_features perform paid model calls. "
        + tools.NON_LEGAL_ADVICE_NOTICE
    ),
)


class _DeterministicToolOrder(Middleware):
    """Serve tools/list in alphabetical order, independent of registration.

    The 2026-07-28 MCP revision makes deterministic tools/list ordering a
    spec SHOULD, and Section 13 makes determinism a MUST here anyway; the
    order must not shift when server.py is refactored (B49).
    """

    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        return sorted(tools, key=lambda tool: tool.name)


mcp.add_middleware(_DeterministicToolOrder())


class _NoMcpLogging(Middleware):
    """Advertise no MCP logging capability and refuse logging/setLevel.

    The MCP Python SDK derives the logging capability from a registered
    logging/setLevel handler, and fastmcp 4.0.10 registers one on every
    server with no constructor option to leave it out. MCP logging is
    deprecated in the 2026-07-28 revision, and no TERE4AI tool ever sent an
    MCP log message: the server's diagnostics are Python logging on stderr
    (C3 ruling R4). This middleware is the narrowest override through
    fastmcp's public Middleware hooks, scoped to this server instance (no
    private attribute and no module patch): it removes the capability from
    the legacy initialize result and the 2026-07-28 server/discover result,
    and answers logging/setLevel with method not found, so what is served
    matches what is advertised.
    """

    async def on_initialize(self, context, call_next):
        result = await call_next(context)
        if result is None:
            return result
        return result.model_copy(
            update={"capabilities": result.capabilities.model_copy(update={"logging": None})}
        )

    async def on_discover(self, context, call_next):
        result = await call_next(context)
        if not isinstance(result, mcp_types.DiscoverResult):
            return result
        return result.model_copy(
            update={"capabilities": result.capabilities.model_copy(update={"logging": None})}
        )

    async def on_request(self, context, call_next):
        if context.method == "logging/setLevel":
            raise MCPError(
                mcp_types.METHOD_NOT_FOUND,
                "logging/setLevel is not served: this server sends no MCP log "
                "messages (its diagnostics go to stderr)",
            )
        return await call_next(context)


mcp.add_middleware(_NoMcpLogging())


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # A dump is served under the publication chain of the directory it was
    # read from (B74), so graph_version names the published build, not
    # merely the legal snapshot every rebuild shares.
    return stamp_served_build(payload, path.parent)


def _active() -> LoadedBuild:
    """One LoadedBuild per tool call (D-G21): the activated publication when
    ACTIVE_MANIFEST.json exists (verified on every call, a drifted file
    refusing service), else the legacy dumps. Read fresh, so the server
    follows a new activation at its next call."""
    return load_active(DUMP_PATH.parent)


def _read_dump(dump_path: Path = DUMP_PATH) -> dict[str, Any] | None:
    return _active().dump


def _attach_source_text(norms: list[dict[str, Any]], dump: dict[str, Any]) -> None:
    """Resolve each norm's verbatim source_text from its Layer 1 source node.

    The runtime grounding judge and the evidence/backlog generators need the
    norm's exact legal wording to detect paraphrase drift, but the served
    norms payload does not carry source_text, so resolve it here from the
    dump before the model ever sees the norm (audit 2026-07-20 D4/F6).
    """
    nodes = {
        n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n
    }
    for norm in norms:
        if norm.get("source_text"):
            continue
        node = nodes.get(norm.get("source_node_id", ""))
        if node is not None and node.get("text"):
            norm["source_text"] = node["text"]


def _empty_content_envelope(field: str, dump: dict[str, Any]) -> dict[str, Any]:
    """Degrade (never raise) when a paid tool is called with empty content.

    Mirrors the HTTP facade's guard so both transports return a Section 8
    envelope instead of a raw exception on the MCP path (audit D9)."""
    return tools.make_envelope(
        answer={"found": False},
        status="not_applicable",
        graph_version=_graph_version(dump),
        confidence=0.0,
        missing_facts=[
            f"'{field}' must be a non-empty string; no evidence was provided "
            "to evaluate, so no model call was made"
        ],
    )


def _invalid_input_envelope(detail: str, dump: dict[str, Any] | None = None) -> dict[str, Any]:
    """Degrade (never raise) when a tool argument is unusable (Section 13).

    Boundary guard for the no-silent-degradation MUST: hostile or malformed
    arguments (None, wrong type, blank required ids) come back as a Section 8
    envelope naming the invalid argument in missing_facts, never as a raw
    exception surfacing to the consumer (live audit 2026-07-21). On paid
    tools this guard runs before any model client is constructed, so an
    unusable input can never trigger a model call.
    """
    return tools.make_envelope(
        answer=None,
        status="requires_human_review",
        graph_version=_graph_version(dump) if dump is not None else "unavailable",
        confidence=0.0,
        missing_facts=[detail],
    )


def _dump_missing_envelope(detail: str | None = None) -> dict[str, Any]:
    # A refused activated build (drifted file, unreadable pointer or
    # manifest, D-G21) names its reason, never the rebuild hint, which
    # would be the wrong remedy (Section 13: no silent degradation).
    if detail:
        return tools.dump_unavailable_envelope(detail)
    # Name the file, not the absolute server path (audit W4: no filesystem
    # layout disclosure to the consumer).
    return tools.dump_unavailable_envelope(
        f"graph dump '{DUMP_PATH.name}' not available; build it with "
        "python -m tere4ai.parse_legal_structure"
    )


def _norms_missing_envelope() -> dict[str, Any]:
    return tools.dump_unavailable_envelope(
        f"judged norms payload '{NORMS_PATH.name}' not available; build it "
        "with python -m tere4ai.extract_norms"
    )


def _alignments_missing_envelope() -> dict[str, Any]:
    return tools.dump_unavailable_envelope(
        f"judged alignments payload '{ALIGNMENTS_PATH.name}' not available; "
        "build it with python -m tere4ai.align_hleg"
    )


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _norm_by_id(norms_payload: dict[str, Any], norm_id: str) -> dict[str, Any] | None:
    return next(
        (
            n
            for n in norms_payload.get("norms", [])
            if isinstance(n, dict) and n.get("norm_id") == norm_id
        ),
        None,
    )


class PaidClients(NamedTuple):
    generator: Any
    judge: Any
    # load_model_config's public dict names it; part of the replay key.
    model_parameters_sha256: str


# The paid tools' replay window (replay.py, C3 ruling R3): one per process.
_REPLAY = replay.ReplayStore()


def _paid_clients_or_envelope() -> PaidClients | dict[str, Any]:
    """Real generator and judge, or a clean degraded envelope on config error."""
    try:
        from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator

        cfg = load_model_config()
        return PaidClients(
            OpenAIGenerator(cfg),
            AnthropicJudge(cfg),
            cfg.as_public_dict()["model_parameters_sha256"],
        )
    except ModelConfigError as exc:
        return tools.make_envelope(
            answer=None,
            status="requires_human_review",
            graph_version="unavailable",
            confidence=0.0,
            missing_facts=[str(exc)],
        )


@mcp.tool(annotations=_READ_ONLY)
def coverage_report() -> dict[str, Any]:
    """Structural coverage of the Act's graph and its judged layers, against
    the frozen source. The Layer 0+1 graph is checked against what the Act
    in force holds (119 articles, 180 recitals, 14 annexes, chapters I to
    XIII, the high-risk core present), with per-chapter article listing and
    layer 2/3 status. Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    # B62: pass the judged payloads like GET /api/coverage does, so the
    # layer 2 and 3 blocks report real counts instead of dump-derived zeros.
    # They are optional for the tool, so a missing payload degrades that
    # block rather than the whole report.
    return tools.coverage_report(
        dump,
        norms_payload=loaded.norms,
        alignments_payload=loaded.alignments,
    )


@mcp.tool(annotations=_READ_ONLY)
def source_trace(node_id: str) -> dict[str, Any]:
    """Trace a graph node to its frozen source snapshot: file, sha256, span
    start/end, HTML anchor, and a text excerpt. Start and end count Unicode
    code points in the snapshot decoded as UTF-8, not bytes; sha256 is over
    the file's bytes. The excerpt is capped at 500
    characters for payload size; when it is shorter than the full provision,
    answer.excerpt_truncated is true and answer.excerpt_chars /
    answer.span_chars report exactly how much of the text was returned, so a
    partial quote is never mistaken for a complete one. Get the full
    verbatim text via resolve_span on the same span_id (or GET
    /api/span/{span_id} on the HTTP facade). Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    return tools.source_trace(dump, node_id, snapshots_dir=SNAPSHOTS_DIR)


@mcp.tool(annotations=_READ_ONLY)
def explain_requirement(norm_id: str, earlier_version: bool = False) -> dict[str, Any]:
    """Explain one judged requirement (a normative statement) in depth. The
    answer holds its deontic decomposition (actor, modal, action, object,
    conditions, exceptions), full source unit text, Article 3 definitions
    occurring in its action/object, accepted HLEG alignment targets with
    relation types and final scores, and a span trace. Non-accepted norms
    are explained too, with their review status stated prominently. The
    source text is the Act in force (Regulation (EU) 2024/1689 as amended by
    Regulation (EU) 2026/1744); earlier_version=true adds the unit's 2024
    wording where the amendment changed it, or says why it has none.
    Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    alignments_payload = loaded.alignments
    if alignments_payload is None:
        return _alignments_missing_envelope()
    return explain_rules.explain_requirement(
        norm_id, dump, norms_payload, alignments_payload, earlier_version=earlier_version
    )


@mcp.tool(annotations=_READ_ONLY)
def trace_alignment(id: str) -> dict[str, Any]:
    """Every EU-to-HLEG alignment for a norm or an HLEG requirement, with
    its judge verdict and evidence. Given a norm_id, the assertions from
    that norm; given an HLEG requirement id, the assertions targeting it.
    Every assertion is rendered with relation type, scores, judge verdict
    and rationale, alignment and judge runs (models, prompt versions), and
    evidence span ids on both sides; never a bare edge. The alignments are
    LLM-generated and not expert-validated. Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    alignments_payload = loaded.alignments
    if alignments_payload is None:
        return _alignments_missing_envelope()
    return trace_rules.trace_alignment(id, alignments_payload, dump)


@mcp.tool(annotations=_READ_ONLY)
def resolve_span(span_id: str) -> dict[str, Any]:
    """The exact source text behind a span id, checked against the
    snapshot's checksum: snapshot file, sha256, start, end, and the text.
    Start and end
    count Unicode code points in the snapshot decoded as UTF-8, not bytes;
    sha256 is over the file's bytes. Unknown span ids and checksum drift
    come back as clean degraded envelopes, never an exception.
    Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    served = served_hleg(dump)
    return spans_rules.resolve_span_envelope(
        span_id, dump, SNAPSHOTS_DIR, extra_nodes=served.nodes, extra_refusal=served.refusal
    )


@mcp.tool(annotations=_READ_ONLY)
def classify_ai_system(features: dict[str, Any]) -> dict[str, Any]:
    """Deterministic EU AI Act risk classification of a described AI system.

    Consumes structured system features (system_features.schema.json) and
    returns risk_category (unacceptable_risk, high_risk, limited_risk,
    minimal_risk, undetermined) with cited Article 5 / Article 6 / Annex III
    / Article 50 nodes. undetermined is not a legal risk level: facts the rules
    need are missing. The answer's unacceptable_risk field is true (an Article 5
    prohibition is proven), false (every Article 5 path is ruled out) or null
    (unknown: an Article 5 fact is missing). transparency_duties lists the
    Article 50 paragraphs triggered by a known fact, on a high-risk answer
    too (Article 50(6)); a listed paragraph is triggered, not proven, and an
    empty list means none is triggered by a known fact. A fixed rule ladder
    decides, never a model; unknown facts that could make the system
    unacceptable risk or high-risk (Article 5, the Article 6(1) route, Annex III)
    surface in missing_facts; where they could change the level the status
    is requires_human_review, and with no rule firing the level is
    undetermined, never minimal_risk. The answer also carries a fria block:
    whether the Article 27(1) fundamental rights impact assessment
    obligation applies to the deployer (applies, does_not_apply, unknown),
    decided by the same deterministic rules from the flags and the optional
    deployer facts (deployer.body_governed_by_public_law,
    deployer.private_entity_providing_public_services); it is unknown, not
    does_not_apply, while an unknown Annex III fact could still make the
    system high-risk under Article 6(2) and the assessment apply, and it
    names that fact. Free, no model calls."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    return classify_rules.classify_ai_system(features, dump)



@mcp.tool(annotations=_READ_ONLY)
def trace_implementation(
    classification: dict[str, Any],
    tags: list[dict[str, Any]],
    addressee: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Requirement-to-code traceability matrix for a classified system.

    classification is the classify_ai_system envelope (or bare answer). tags
    are `@implements: <norm-id>` records scanned CLIENT-SIDE from the
    consumer project (reference scanner: python -m tere4ai.trace_scan <dir>),
    each {"norm_id", "path", "line"}; this server never reads a consumer
    filesystem. Returns one row per applicable judge-accepted norm with its
    source span, accepted HLEG alignments, claiming code locations, and
    trace_status traced or untraced, plus invalid_tags for any tag citing an
    unknown or non-accepted norm id (review-queue norms never count). A trace
    is a developer claim, not evidence; it never raises an evidence status.
    addressee, as get_applicable_requirements takes it; the argument actor is
    retired and refused.
    Deterministic and free."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    alignments_payload = loaded.alignments
    if alignments_payload is None:
        return _alignments_missing_envelope()
    if not isinstance(classification, dict):
        return _invalid_input_envelope(
            "'classification' must be the classify_ai_system envelope or its "
            f"answer object; got {type(classification).__name__}",
            dump,
        )
    return trace_code_rules.trace_implementation(
        classification, tags, norms_payload, alignments_payload, dump, addressee, actor=actor
    )


@mcp.tool(annotations=_READ_ONLY)
def get_applicable_requirements(
    classification: dict[str, Any], addressee: str | None = None, actor: str | None = None
) -> dict[str, Any]:
    """Judge-accepted engineering requirements applicable to a classified
    system, grouped by source article.

    classification is the classify_ai_system envelope (or its bare answer).
    Only judge-ACCEPTED NormativeStatements are returned; unacceptable-risk systems
    get zero requirements, only the prohibition citation. The optional addressee
    names one party of the Act (schema/act_parties.json): one of the six AI Act
    roles (provider, product_manufacturer, deployer, authorised_representative,
    importer, distributor) or an authority, body, institution or person the Act
    names; the norms the facade serves to it are those whose stored addressee is
    that party, operators in general for an AI Act role, and the AI Office's for
    the Commission and the national competent authorities' for a notifying or
    market surveillance authority (Article 3(47), 3(48)). The argument actor is
    retired and refused.
    Deterministic selection over the judged build artifact; free, no model
    calls."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    if not isinstance(classification, dict):
        return _invalid_input_envelope(
            "'classification' must be a dict (the classify_ai_system envelope "
            f"or its bare answer); got {type(classification).__name__}",
            dump,
        )
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    return requirements_rules.get_applicable_requirements(
        classification, norms_payload, dump, addressee, actor=actor
    )


@mcp.tool(annotations=_READ_ONLY_PAID)
def evaluate_project_evidence(
    norm_id: str,
    artifact_type: str,
    content: str,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate ONE untrusted project evidence artifact against ONE
    judge-accepted norm from the graph.

    PAID: this tool performs paid model calls (one OpenAI generator call
    plus one Anthropic runtime grounding judge call) on every invocation.

    norm_id must be a judge-accepted NormativeStatement id from
    get_applicable_requirements. Returns the assessment (satisfied,
    partially_satisfied, missing, contradicted, cannot_assess), the
    surviving verbatim quotes, the gaps, and the judge verdict and
    rationale; a non-accepting judge verdict degrades the status to
    requires_human_review, never silently."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    norm = _norm_by_id(norms_payload, norm_id)
    if norm is None:
        return tools.make_envelope(
            answer={"norm_id": norm_id, "found": False},
            status="not_applicable",
            graph_version=_graph_version(dump),
            confidence=0.0,
            missing_facts=[
                f"norm_id '{norm_id}' is not present in the judged norms payload"
            ],
        )
    if not isinstance(content, str) or not content.strip():
        return _empty_content_envelope("content", dump)
    if not isinstance(artifact_type, str) or not artifact_type.strip():
        return _invalid_input_envelope(
            "'artifact_type' must be a non-empty string naming the artifact "
            f"kind; got {type(artifact_type).__name__}; the evidence was not "
            "evaluated and no model call was made",
            dump,
        )
    _attach_source_text([norm], dump)
    clients = _paid_clients_or_envelope()
    if isinstance(clients, dict):
        return clients
    return _REPLAY.run(
        tool="evaluate_project_evidence",
        arguments={
            "norm_id": norm_id,
            "artifact_type": artifact_type,
            "content": content,
            "artifact_id": artifact_id,
        },
        build=_graph_version(dump),
        model_parameters_sha256=clients.model_parameters_sha256,
        compute=lambda: evidence_rules.evaluate_project_evidence(
            norm,
            {"artifact_type": artifact_type, "content": content, "artifact_id": artifact_id},
            clients.generator,
            clients.judge,
            graph_version=_graph_version(dump),
        ),
    )


@mcp.tool(annotations=_READ_ONLY_PAID)
def evaluate_project_evidence_batch(
    article_node_id: str,
    artifact_type: str,
    content: str,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate ONE untrusted evidence artifact against EVERY judge-accepted
    norm of one article, in a single envelope with per-norm results.

    PAID: this tool performs paid model calls PER NORM (one generator call
    plus one runtime grounding judge call for each judge-accepted norm of
    the article), so an article with N accepted norms costs N times the
    single-norm tool.

    article_node_id is a Layer 1 article id such as eu-ai-act:article-9.
    The envelope status is the most conservative per-norm status and the
    judge_verdict is accepted only when every per-norm verdict is."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    if not isinstance(article_node_id, str) or not article_node_id.strip():
        # A blank id would prefix-match every accepted norm via startswith,
        # triggering one paid model call per norm; block it here too.
        return _invalid_input_envelope(
            "'article_node_id' must be a non-empty string Layer 1 article id "
            f"such as eu-ai-act:article-9; got {type(article_node_id).__name__}",
            dump,
        )
    norms = evidence_rules.accepted_norms_for_article(norms_payload, article_node_id)
    if not norms:
        return tools.make_envelope(
            answer={"article_node_id": article_node_id, "found": False},
            status="not_applicable",
            graph_version=_graph_version(dump),
            confidence=0.0,
            missing_facts=[
                f"no judge-accepted norms sourced from '{article_node_id}'"
            ],
        )
    if not isinstance(content, str) or not content.strip():
        return _empty_content_envelope("content", dump)
    if not isinstance(artifact_type, str) or not artifact_type.strip():
        return _invalid_input_envelope(
            "'artifact_type' must be a non-empty string naming the artifact "
            f"kind; got {type(artifact_type).__name__}; the evidence was not "
            "evaluated and no model call was made",
            dump,
        )
    _attach_source_text(norms, dump)
    clients = _paid_clients_or_envelope()
    if isinstance(clients, dict):
        return clients
    return _REPLAY.run(
        tool="evaluate_project_evidence_batch",
        arguments={
            "article_node_id": article_node_id,
            "artifact_type": artifact_type,
            "content": content,
            "artifact_id": artifact_id,
        },
        build=_graph_version(dump),
        model_parameters_sha256=clients.model_parameters_sha256,
        compute=lambda: evidence_rules.evaluate_evidence_batch(
            norms,
            {"artifact_type": artifact_type, "content": content, "artifact_id": artifact_id},
            clients.generator,
            clients.judge,
            graph_version=_graph_version(dump),
        ),
    )


@mcp.tool(annotations=_READ_ONLY_PAID)
def generate_control_backlog(norm_ids: list[str], system_context: str) -> dict[str, Any]:
    """Generate a judged engineering control backlog from judge-accepted
    norms.

    PAID: this tool performs paid model calls (one OpenAI generator call
    plus one Anthropic runtime grounding judge call) on every invocation.

    norm_ids are NormativeStatement ids from get_applicable_requirements
    (capped at 10; any truncation is noted in the answer, never silent).
    Every backlog item cites only input norm ids; items citing anything else
    are dropped and counted. The judge verdict gates the whole backlog."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    norms_payload = loaded.norms
    if norms_payload is None:
        return _norms_missing_envelope()
    if not norm_ids:
        return tools.make_envelope(
            answer=None,
            status="not_applicable",
            graph_version=_graph_version(dump),
            confidence=0.0,
            missing_facts=["norm_ids is empty; at least one judge-accepted norm id is required"],
        )
    if not isinstance(norm_ids, list):
        # A non-list here would crash (int) or be iterated as characters
        # (str); degrade instead of raising (live audit 2026-07-21).
        return _invalid_input_envelope(
            "'norm_ids' must be a list of NormativeStatement id strings; "
            f"got {type(norm_ids).__name__}",
            dump,
        )
    if not isinstance(system_context, str) or not system_context.strip():
        return _invalid_input_envelope(
            "'system_context' must be a non-empty string describing the "
            f"system; got {type(system_context).__name__}; no backlog was "
            "generated and no model call was made",
            dump,
        )
    unknown = [
        norm_id for norm_id in norm_ids if _norm_by_id(norms_payload, norm_id) is None
    ]
    if unknown:
        return tools.make_envelope(
            answer={"unknown_norm_ids": unknown},
            status="not_applicable",
            graph_version=_graph_version(dump),
            confidence=0.0,
            missing_facts=[
                f"norm_id '{n}' is not present in the judged norms payload"
                for n in unknown
            ],
        )
    norms = [_norm_by_id(norms_payload, norm_id) for norm_id in norm_ids]
    refusals = backlog_rules.deleted_source_refusals(norms, dump)
    if refusals:
        return tools.make_envelope(
            answer={"refused_norm_ids": list(refusals)},
            status="not_applicable",
            graph_version=_graph_version(dump),
            confidence=0.0,
            missing_facts=[*refusals.values(), "no backlog was generated and no model call was made"],
        )
    _attach_source_text(norms, dump)
    clients = _paid_clients_or_envelope()
    if isinstance(clients, dict):
        return clients
    return _REPLAY.run(
        tool="generate_control_backlog",
        arguments={"norm_ids": norm_ids, "system_context": system_context},
        build=_graph_version(dump),
        model_parameters_sha256=clients.model_parameters_sha256,
        compute=lambda: backlog_rules.generate_control_backlog(
            norms,
            system_context,
            clients.generator,
            clients.judge,
            graph_version=_graph_version(dump),
        ),
    )


@mcp.tool(annotations=_READ_ONLY_PAID)
def elicit_features(description: str) -> dict[str, Any]:
    """Propose the system_features facts of a plain-text system description,
    for the person to confirm before classify_ai_system runs.

    PAID: this tool performs one paid model call (one OpenAI generator call,
    no judge) on every invocation.

    description is the system's description in plain text, at least 30
    characters. The prompt quotes the Act's provisions from the served
    build. The answer carries features (schema-valid system_features, never
    a risk category), quotes (for each kept fact, the words of the
    description it rests on, with start and end offsets in code points),
    dropped (each fact removed because its quote was missing, shorter than
    three words, or not in the description), notes, and prompt (version,
    template and rendered prompt hashes, provision ids, build). Code checks
    that the quoted words are in the description; a person judges whether
    they support the fact. The status is requires_human_review by
    construction: the deterministic ladder alone classifies. missing_facts
    names every flag not elicited and every dropped fact. A provision that
    does not resolve in the build stops the call before the model is paid,
    and missing_facts names it."""
    loaded = _active()
    dump = loaded.dump
    if dump is None:
        return _dump_missing_envelope(loaded.error)
    if not isinstance(description, str) or not description.strip():
        return _invalid_input_envelope(
            "'description' must be a non-empty string describing the system; "
            f"got {type(description).__name__}; no facts were elicited and no "
            "model call was made",
            dump,
        )
    if len(description) < elicit_rules.MIN_DESCRIPTION_CHARS:
        # The facade's ElicitRequest floor, so both surfaces refuse alike.
        return _invalid_input_envelope(
            f"'description' must be at least {elicit_rules.MIN_DESCRIPTION_CHARS} "
            f"characters; got {len(description)}; no facts were elicited and no "
            "model call was made",
            dump,
        )
    clients = _paid_clients_or_envelope()
    if isinstance(clients, dict):
        return clients
    return _REPLAY.run(
        tool="elicit_features",
        arguments={"description": description},
        build=_graph_version(dump),
        model_parameters_sha256=clients.model_parameters_sha256,
        compute=lambda: elicit_rules.elicit_envelope(
            description, clients.generator, dump=dump, snapshots_dir=SNAPSHOTS_DIR
        ),
    )


def _check_dump_integrity_at_startup() -> None:
    """Verify the published dumps against a recorded build chain at boot.

    Runtime half of the CI build-chain gate (audit 2026-07-20 D3): if the
    served dumps are present but reproduce no recorded build_chain record,
    they have drifted (corruption or tampering). Default is a loud warning so
    a dumpless or structural-only checkout still starts; set
    TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY=1 to hard-fail instead, which a
    production deployment should do. Absent dumps are handled by the
    per-tool dump-missing envelopes, not here. An activation pointer is
    checked even without a layer1.json, since the activated publication may
    name its Layer 1 file otherwise (B79 item 23).
    """
    if not DUMP_PATH.is_file() and not (DUMP_PATH.parent / ACTIVE_POINTER).is_file():
        return
    from tere4ai.graph_store.build_chain import verify_dumps_against_chain

    manifest = active_manifest(DUMP_PATH.parent)
    if manifest is None and (DUMP_PATH.parent / ACTIVE_POINTER).is_file():
        print(
            f"TERE4AI: the activation pointer {ACTIVE_POINTER} or its publication manifest is "
            "unreadable; running the legacy three-file integrity check instead",
            file=sys.stderr,
        )
    ok, detail = verify_dumps_against_chain(
        DUMP_PATH.parent, chain_id=manifest["chain_id"] if manifest else None
    )
    if ok:
        return
    message = f"TERE4AI dump integrity check FAILED: {detail}"
    if os.environ.get("TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY") == "1":
        raise RuntimeError(message)
    logging.getLogger("tere4ai.mcp_server").warning(
        "%s. Serving anyway (set TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY=1 to "
        "refuse). The published graph may not match a reproducible build.",
        message,
    )


def main() -> None:
    """Run stdio by default; streamable HTTP only behind an explicit flag.

    TERE4AI_MCP_TRANSPORT=http selects FastMCP's streamable HTTP transport
    (the MCP spec's remote transport, REF-31). Anything other than stdio or
    http fails loudly rather than silently serving the wrong surface.
    """
    try:
        # A replay window the paid tools cannot use stops the start, not the
        # first paid call (C3 ruling R3).
        replay.window_seconds()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    _check_dump_integrity_at_startup()
    transport = os.environ.get("TERE4AI_MCP_TRANSPORT", "stdio").strip().lower()
    require_key = transport in ("http", "streamable-http") or os.environ.get(
        "TERE4AI_MCP_REQUIRE_KEY"
    ) == "1"
    if require_key:
        # Section 8: remote consumers authenticate with scoped, revocable
        # keys; local stdio (Mode B trusted workstation) stays keyless
        # unless TERE4AI_MCP_REQUIRE_KEY=1. Keys: scripts/manage_mcp_keys.py.
        from tere4ai.mcp_server.keys import ScopedKeyMiddleware

        mcp.add_middleware(ScopedKeyMiddleware())
    if transport == "stdio":
        mcp.run()
        return
    if transport in ("http", "streamable-http"):
        mcp.run(
            transport="http",
            host=os.environ.get("TERE4AI_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("TERE4AI_MCP_PORT", "8765")),
        )
        return
    raise SystemExit(
        f"unsupported TERE4AI_MCP_TRANSPORT {transport!r}: use 'stdio' or 'http'"
    )


if __name__ == "__main__":
    main()
