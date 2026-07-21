"""FastMCP server exposing the read-only TERE4AI tools over the offline dumps.

Wraps the pure functions in tools.py, classify.py, requirements.py,
evidence.py, and backlog.py as read-only MCP tools (no write surface,
architecture.md Section 8). The Layer 0+1 dump is read from
data/graph_dumps/layer1.json and the judged norms payload from
data/graph_dumps/norms_core.json (versioned build artifacts); no running
Neo4j is required. If a dump has not been built, the tools return a
degraded envelope instead of failing silently (Section 13).

evaluate_project_evidence and generate_control_backlog perform PAID model
calls (OpenAI generator plus Anthropic runtime grounding judge); their
descriptions say so, and a missing model configuration surfaces as a clean
degraded envelope, never a traceback.

Transport: stdio by default (Mode B, architecture.md Section 9). The
streamable HTTP transport for remote consumers sits behind an explicit
flag, TERE4AI_MCP_TRANSPORT=http, binding TERE4AI_MCP_HOST (default
127.0.0.1) and TERE4AI_MCP_PORT (default 8765). HTTP requests must carry
a scoped t4a_ API key as a Bearer token (keys.py; mint and revoke with
scripts/manage_mcp_keys.py); stdio stays keyless unless
TERE4AI_MCP_REQUIRE_KEY=1. Every tool call is metered body-free.

@implements: DEC-08, DEC-10
@grounded_by: REF-16, REF-17, REF-15, REF-31
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from tere4ai.judge.config import ModelConfigError, load_model_config
from tere4ai.mcp_server import backlog as backlog_rules
from tere4ai.mcp_server import classify as classify_rules
from tere4ai.mcp_server import evidence as evidence_rules
from tere4ai.mcp_server import explain as explain_rules
from tere4ai.mcp_server import requirements as requirements_rules
from tere4ai.mcp_server import spans as spans_rules
from tere4ai.mcp_server import tools
from tere4ai.mcp_server import trace as trace_rules

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DUMP_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "alignments_core.json"
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"

# Facade-parity cap on backlog input norms (http_facade.app.MAX_BACKLOG_NORMS).
MAX_BACKLOG_NORMS = 10

_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
# Paid tools stay read-only against the graph but reach external model APIs.
_READ_ONLY_PAID = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}

mcp = FastMCP(
    name="tere4ai",
    instructions=(
        "TERE4AI v2 tools over the EU AI Act graph: M1 structural tools "
        "(coverage_report, source_trace) plus explanation and trace tools "
        "(explain_requirement, trace_alignment, resolve_span) plus M3 "
        "runtime tools (classify_ai_system, get_applicable_requirements, "
        "evaluate_project_evidence, generate_control_backlog). Read-only; "
        "evaluate_project_evidence and generate_control_backlog perform paid "
        "model calls. " + tools.NON_LEGAL_ADVICE_NOTICE
    ),
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_dump(dump_path: Path = DUMP_PATH) -> dict[str, Any] | None:
    return _read_json(dump_path)


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


def _dump_missing_envelope() -> dict[str, Any]:
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
        "build it with python -m tere4ai.align_hleg_altai"
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


def _paid_clients_or_envelope() -> tuple[Any, Any] | dict[str, Any]:
    """Real generator and judge, or a clean degraded envelope on config error."""
    try:
        from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator

        cfg = load_model_config()
        return OpenAIGenerator(cfg), AnthropicJudge(cfg)
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
    """Structural coverage of the Layer 0+1 graph against the M1 acceptance
    (113 articles, 180 recitals, 13 annexes, chapters I to XIII, high-risk
    core presence), with per-chapter article listing and layer 2/3 status.
    Deterministic and free."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    return tools.coverage_report(dump)


@mcp.tool(annotations=_READ_ONLY)
def source_trace(node_id: str) -> dict[str, Any]:
    """Trace a graph node to its frozen source snapshot: file, sha256, span
    start/end, HTML anchor, and a text excerpt. Deterministic and free."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    return tools.source_trace(dump, node_id, snapshots_dir=SNAPSHOTS_DIR)


@mcp.tool(annotations=_READ_ONLY)
def explain_requirement(norm_id: str) -> dict[str, Any]:
    """Explain ONE judged NormativeStatement: deontic decomposition (actor,
    modal, action, object, conditions, exceptions), full source unit text,
    Article 3 definitions occurring in its action/object, accepted HLEG
    alignment targets with relation types and final scores, and a span
    trace. Non-accepted norms are explained too, with their review status
    stated prominently. Deterministic and free."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    norms_payload = _read_json(NORMS_PATH)
    if norms_payload is None:
        return _norms_missing_envelope()
    alignments_payload = _read_json(ALIGNMENTS_PATH)
    if alignments_payload is None:
        return _alignments_missing_envelope()
    return explain_rules.explain_requirement(norm_id, dump, norms_payload, alignments_payload)


@mcp.tool(annotations=_READ_ONLY)
def trace_alignment(id: str) -> dict[str, Any]:
    """All reified EU-to-HLEG alignment chains for a norm_id (assertions
    from that norm) or an HLEG requirement id (assertions targeting it).
    Every assertion is rendered with relation type, scores, judge verdict
    and rationale, mapping and judge runs (models, prompt versions), and
    evidence span ids on both sides; never a bare edge. The mappings are
    LLM-generated and not expert-validated. Deterministic and free."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    alignments_payload = _read_json(ALIGNMENTS_PATH)
    if alignments_payload is None:
        return _alignments_missing_envelope()
    return trace_rules.trace_alignment(id, alignments_payload, dump)


@mcp.tool(annotations=_READ_ONLY)
def resolve_span(span_id: str) -> dict[str, Any]:
    """Resolve a SourceSpan id to its checksum-verified snapshot slice:
    snapshot file, sha256, start, end, and the exact text. Unknown span ids
    and checksum drift come back as clean degraded envelopes, never an
    exception. Deterministic and free."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    return spans_rules.resolve_span_envelope(
        span_id, dump, SNAPSHOTS_DIR, extra_nodes=_hleg_nodes()
    )


def _hleg_nodes() -> list[dict[str, Any]]:
    """The seven HLEG requirement nodes (target-side spans live outside the
    Layer 0+1 dump); empty when the frozen HLEG text is unavailable."""
    try:
        from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes

        return build_hleg_nodes()
    except Exception:  # noqa: BLE001 - degrade to dump-only span resolution
        return []


@mcp.tool(annotations=_READ_ONLY)
def classify_ai_system(features: dict[str, Any]) -> dict[str, Any]:
    """Deterministic EU AI Act risk classification of a described AI system.

    Consumes structured system features (system_features.schema.json) and
    returns risk_category (prohibited, high_risk, transparency_only,
    minimal_or_none, uncertain) with cited Article 5 / Article 6 / Annex III
    / Article 50 nodes. A fixed rule ladder decides, never a model; unknown
    prohibition-relevant facts surface in missing_facts and lower the status
    to requires_human_review. The answer also carries a fria block: whether
    the Article 27(1) fundamental rights impact assessment obligation
    applies to the deployer (applies, does_not_apply, unknown), decided by
    the same deterministic rules from the flags and the optional deployer
    facts (deployer.body_governed_by_public_law,
    deployer.private_entity_providing_public_services). Free, no model
    calls."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    return classify_rules.classify_ai_system(features, dump)


@mcp.tool(annotations=_READ_ONLY)
def get_applicable_requirements(
    classification: dict[str, Any], actor: str | None = None
) -> dict[str, Any]:
    """Judge-accepted engineering requirements applicable to a classified
    system, grouped by source article.

    classification is the classify_ai_system envelope (or its bare answer).
    Only judge-ACCEPTED NormativeStatements are returned; prohibited systems
    get zero requirements, only the prohibition citation. The optional actor
    filter uses the canonical actor vocabulary (provider, deployer, ...).
    Deterministic selection over the judged build artifact; free, no model
    calls."""
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    if not isinstance(classification, dict):
        return _invalid_input_envelope(
            "'classification' must be a dict (the classify_ai_system envelope "
            f"or its bare answer); got {type(classification).__name__}",
            dump,
        )
    norms_payload = _read_json(NORMS_PATH)
    if norms_payload is None:
        return _norms_missing_envelope()
    return requirements_rules.get_applicable_requirements(
        classification, norms_payload, dump, actor=actor
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
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    norms_payload = _read_json(NORMS_PATH)
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
    generator, judge = clients
    return evidence_rules.evaluate_project_evidence(
        norm,
        {"artifact_type": artifact_type, "content": content, "artifact_id": artifact_id},
        generator,
        judge,
        graph_version=_graph_version(dump),
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
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    norms_payload = _read_json(NORMS_PATH)
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
    generator, judge = clients
    return evidence_rules.evaluate_evidence_batch(
        norms,
        {"artifact_type": artifact_type, "content": content, "artifact_id": artifact_id},
        generator,
        judge,
        graph_version=_graph_version(dump),
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
    dump = _read_dump()
    if dump is None:
        return _dump_missing_envelope()
    norms_payload = _read_json(NORMS_PATH)
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
    _attach_source_text(norms, dump)
    clients = _paid_clients_or_envelope()
    if isinstance(clients, dict):
        return clients
    generator, judge = clients
    return backlog_rules.generate_control_backlog(
        norms,
        system_context,
        generator,
        judge,
        max_norms=MAX_BACKLOG_NORMS,
        graph_version=_graph_version(dump),
    )


def _check_dump_integrity_at_startup() -> None:
    """Verify the published dumps against a recorded build chain at boot.

    Runtime half of the CI build-chain gate (audit 2026-07-20 D3): if the
    served dumps are present but reproduce no recorded build_chain record,
    they have drifted (corruption or tampering). Default is a loud warning so
    a dumpless or structural-only checkout still starts; set
    TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY=1 to hard-fail instead, which a
    production deployment should do. Absent dumps are handled by the
    per-tool dump-missing envelopes, not here.
    """
    if not DUMP_PATH.is_file():
        return
    from tere4ai.graph_store.build_chain import verify_dumps_against_chain

    ok, detail = verify_dumps_against_chain(DUMP_PATH.parent)
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
