"""HTML rendering of recorded MCP envelopes as one self-contained report.

@implements: DEC-08, DEC-15
@grounded_by: ADD-14, ADD-15

Pure function of the ingested exchanges: no clock, no randomness, no model,
no network. Every timestamp shown comes from the envelopes' own generated_at
or line ts fields. Same input bytes in, byte-identical HTML out.

Markup contract (the honesty tests code against it):
- emit_field is the single emitter for envelope-carried strings; it escapes
  and stamps data-envelope-field, plus data-verbatim="true" for the fields
  in VERBATIM_QUOTE_FIELDS.
- Status badges are neutral and identically styled for all seven values;
  requires_human_review gets a dashed border only.
- Sections carry data-section attributes; matrix rows carry data-trace-row.
- The non-legal-advice notice renders twice and is never inside <details>.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
    VERBATIM_QUOTE_FIELDS,
)
from tere4ai.report.ingest import Exchange, ProblemCard, ingest_inputs

# Fixed honesty sentence for the trace matrix. When the recorded trace_note
# does not carry it, the generator inserts it itself and flags the insertion.
FIXED_TRACE_SENTENCE = "A trace is a developer claim, not evidence."

# Mandated header copy.
_KICKER = "TERE4AI ENGINEERING REQUIREMENTS REPORT"
_SUBKICKER = "Machine-generated working record"

_LEGEND_SENTENCE = (
    "Statuses describe evidence state. They are not grades and do not sum "
    "to a compliance result."
)

# Neutral one-line readings of the calibrated vocabulary (generator copy).
_STATUS_LEGEND: dict[str, str] = {
    "not_applicable": "the provision does not apply to the system as described",
    "potentially_applicable": "may apply; the classification inputs leave the question open",
    "applicable_missing_evidence": "applies; no evaluated evidence is on record yet",
    "partially_satisfied": "evaluated evidence covers part of the requirement",
    "satisfied_with_evidence": "evaluated evidence covers the requirement as submitted",
    "rejected_as_unsupported": "submitted evidence did not support the claim",
    "requires_human_review": "the system cannot settle this; a person must review it",
}

_HOMED_TOOLS = frozenset(
    {
        "classify_ai_system",
        "get_applicable_requirements",
        "trace_implementation",
        "generate_control_backlog",
        "trace_alignment",
        "evaluate_project_evidence",
        "explain_requirement",
        "resolve_span",
    }
)

_CSS = """
:root {
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-serif: Charter, "Iowan Old Style", Palatino, "Palatino Linotype", "Times New Roman", Times, Georgia, serif;
  --font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --ink: oklch(0.141 0.005 285.823);
  --ink-muted: oklch(0.552 0.016 285.938);
  --paper: oklch(1 0 0);
  --paper-tint: oklch(0.967 0.001 286.375);
  --quote-bg: oklch(0.985 0.002 286);
  --rule: oklch(0.92 0.004 286.32);
  --rule-strong: oklch(0.70 0.01 286);
  --head: oklch(0.21 0.034 270);
  /* --attn is reserved for document failures only, never for statuses. */
  --attn: oklch(0.577 0.245 27.325);
  --radius: 3px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: oklch(0.945 0 0);
    --ink-muted: oklch(0.75 0 0);
    --paper: oklch(0.145 0 0);
    --paper-tint: oklch(0.215 0 0);
    --quote-bg: oklch(0.195 0 0);
    --rule: oklch(1 0 0 / 14%);
    --rule-strong: oklch(1 0 0 / 32%);
    --head: oklch(0.945 0 0);
    --attn: oklch(0.704 0.191 22.216);
  }
}
* { box-sizing: border-box; }
html { background: var(--paper); }
body {
  margin: 0 auto; max-width: 46rem; padding: 2.5rem 1.25rem 3rem;
  font-family: var(--font-sans); font-size: 0.95rem; line-height: 1.55;
  color: var(--ink); background: var(--paper);
}
h1, h2, h3, h4 { color: var(--head); line-height: 1.25; }
h1 { font-size: 1.55rem; margin: 0.4rem 0 0.8rem; }
h2 { font-size: 1.15rem; margin: 2.2rem 0 0.6rem; border-bottom: 1px solid var(--rule-strong); padding-bottom: 0.25rem; }
h3 { font-size: 0.98rem; margin: 1.3rem 0 0.4rem; }
.kicker { font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-muted); }
dl.identity { margin: 0.8rem 0; }
dl.identity > div { display: flex; gap: 0.6rem; padding: 0.18rem 0; border-bottom: 1px solid var(--rule); }
dl.identity dt { flex: 0 0 11rem; color: var(--ink-muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 0.15rem; }
dl.identity dd { margin: 0; overflow-wrap: anywhere; }
dl.pairs > div { display: flex; gap: 0.6rem; padding: 0.12rem 0; }
dl.pairs dt { flex: 0 0 14rem; color: var(--ink-muted); font-size: 0.82rem; }
dl.pairs dd { margin: 0; overflow-wrap: anywhere; }
.notice { border: 1px solid var(--rule-strong); border-radius: var(--radius-container); background: var(--paper-tint); padding: 0.6rem 0.9rem; margin: 1rem 0; }
.microlabel { font-family: var(--font-mono); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-muted); }
.status, .chip, .token {
  font-family: var(--font-mono); font-size: 0.76rem; background: var(--paper-tint);
  border: 1px solid var(--rule-strong); border-radius: var(--radius); padding: 0.05rem 0.35rem;
}
.status[data-status="requires_human_review"] { border-style: dashed; }
.chip { overflow-wrap: anywhere; }
.judge-record { border: 1px solid var(--rule); background: var(--paper-tint); padding: 0.6rem 0.9rem; margin: 0.7rem 0; border-radius: var(--radius-container); }
blockquote.verbatim { font-family: var(--font-serif); background: var(--quote-bg); border-left: 2px solid var(--head); margin: 0.6rem 0; padding: 0.55rem 0.9rem; border-radius: 10px; }
blockquote.verbatim .quote-credential { display: block; margin-top: 0.4rem; font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-muted); }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 0.6rem 0; }
th { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; text-align: left; color: var(--ink-muted); border-bottom: 1px solid var(--rule-strong); padding: 0.3rem 0.5rem; }
td { border-bottom: 1px solid var(--rule); padding: 0.35rem 0.5rem; vertical-align: top; }
.muted { color: var(--ink-muted); }
.caption { font-size: 0.85rem; color: var(--ink-muted); margin: 0.4rem 0; }
.figure-band { display: flex; flex-wrap: wrap; gap: 0.8rem; margin: 0.8rem 0; }
.figure { border: 1px solid var(--rule); border-radius: var(--radius-container); padding: 0.5rem 0.8rem; flex: 1 1 10rem; }
.figure .number { display: block; font-size: 1.35rem; font-family: var(--font-mono); }
.figure .qualifier { display: block; font-size: 0.74rem; color: var(--ink-muted); }
.banner { border: 2px solid var(--head); border-radius: var(--radius-container); padding: 0.9rem 1.1rem; margin: 1.2rem 0; }
.banner.document-failure { border-color: var(--attn); }
.prohibition-banner { border: 3px double var(--head); border-radius: var(--radius-container); padding: 1rem 1.2rem; margin: 1.2rem 0; }
.problem-card { border: 1px solid var(--attn); background: var(--paper-tint); padding: 0.6rem 0.9rem; margin: 0.7rem 0; border-radius: var(--radius-container); }
tr.defect-error > td:first-child { border-left: 3px solid var(--attn); }
.flag { font-size: 0.8rem; color: var(--attn); font-family: var(--font-mono); margin: 0.2rem 0; }
.norm-row { border-bottom: 1px solid var(--rule); padding: 0.45rem 0; }
.meta-line { font-size: 0.8rem; color: var(--ink-muted); }
.record-line { font-size: 0.84rem; margin: 0.5rem 0; }
.call-history { font-size: 0.78rem; color: var(--ink-muted); border-top: 1px dotted var(--rule-strong); margin-top: 0.4rem; padding-top: 0.25rem; }
ul.todo { list-style: none; padding-left: 0; }
ul.todo > li { padding: 0.4rem 0; border-bottom: 1px solid var(--rule); }
code.tag-line { display: inline-block; font-family: var(--font-mono); font-size: 0.78rem; background: var(--paper-tint); border: 1px solid var(--rule); border-radius: var(--radius); padding: 0.08rem 0.4rem; user-select: all; overflow-wrap: anywhere; }
pre.source-text { font-family: var(--font-mono); font-size: 0.78rem; background: var(--paper-tint); border: 1px solid var(--rule); border-radius: 10px; padding: 0.6rem 0.8rem; overflow-x: auto; white-space: pre-wrap; }
details { margin: 0.5rem 0; }
details > summary { cursor: pointer; color: var(--ink-muted); font-size: 0.85rem; }
.placeholder { color: var(--ink-muted); font-style: italic; }
footer.report-footer { margin-top: 2.5rem; border-top: 1px solid var(--rule-strong); padding-top: 0.8rem; font-size: 0.85rem; }
.print-footer { font-family: var(--font-mono); font-size: 0.7rem; color: var(--ink-muted); border-top: 1px solid var(--rule); margin-top: 1rem; padding-top: 0.3rem; }
@page {
  size: A4;
  margin: 16mm;
}
@media print {
  body { max-width: none; }
  h2 { break-before: page; }
  thead { display: table-header-group; }
  tr, blockquote.verbatim, .notice, .figure, .problem-card { break-inside: avoid; }
  .print-footer { position: fixed; bottom: 0; left: 0; right: 0; background: var(--paper); }
}
"""


def _esc(value: Any) -> str:
    return escape(str(value), quote=True)


def emit_field(field_name: str, value: Any, *, block: bool = False) -> str:
    """The single emitter for envelope-carried strings.

    HTML-escapes the value and stamps data-envelope-field; fields listed in
    VERBATIM_QUOTE_FIELDS additionally carry data-verbatim="true". All
    envelope values in the document are routed through this function.
    """
    tag = "div" if block else "span"
    verbatim = ' data-verbatim="true"' if field_name in VERBATIM_QUOTE_FIELDS else ""
    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=1)
    else:
        text = str(value)
    return (
        f'<{tag} class="field" data-envelope-field="{_esc(field_name)}"'
        f"{verbatim}>{_esc(text)}</{tag}>"
    )


def _status_badge(status: Any) -> str:
    return (
        '<span class="microlabel">status</span> '
        f'<span class="status" data-status="{_esc(status)}">{_esc(status)}</span>'
    )


def _chip(field_name: str, value: Any) -> str:
    return f'<span class="chip">{emit_field(field_name, value)}</span>'


def _token(field_name: str, value: Any) -> str:
    return f'<span class="token">{emit_field(field_name, value)}</span>'


def _verbatim_block(field_name: str, value: Any, credential_html: str = "") -> str:
    cred = (
        f'<span class="quote-credential">{credential_html}</span>'
        if credential_html
        else ""
    )
    return (
        f'<blockquote class="verbatim">{emit_field(field_name, value)}{cred}'
        "</blockquote>"
    )


def _answer(ex: Exchange | None) -> dict[str, Any]:
    if ex is None:
        return {}
    ans = ex.envelope.get("answer")
    return ans if isinstance(ans, dict) else {}


def _flags_html(ex: Exchange) -> str:
    return "".join(f'<p class="flag">{_esc(f)}</p>' for f in ex.conformance_flags)


def _legal_notes_html(ex: Exchange) -> str:
    """legal_status_notes promoted into the owning section (never appendix)."""
    notes = ex.envelope.get("legal_status_notes")
    if not isinstance(notes, list) or not notes:
        return ""
    items = "".join(
        f"<li>{emit_field('legal_status_notes', n)}</li>" for n in notes
    )
    return (
        '<div class="legal-notes"><p class="microlabel">legal status notes</p>'
        f"<ul>{items}</ul></div>"
    )


def _record_line(
    ex: Exchange,
    mixed_versions: bool,
    superseded: list[Exchange],
    extra_note: str = "",
) -> str:
    """The per-card envelope record: status, confidence, judge, call history."""
    parts = [_status_badge(ex.envelope.get("status"))]
    confidence = ex.envelope.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        parts.append(
            "confidence "
            + emit_field("confidence", f"{confidence:.2f}")
            + ' <span class="muted">(model self-report, not calibrated'
            " probability)</span>"
        )
    judge_verdict = ex.envelope.get("judge_verdict")
    if judge_verdict == "not_applicable_deterministic":
        parts.append(
            '<span class="muted">judge: deterministic, no model</span>'
        )
    elif judge_verdict is not None:
        parts.append("judge verdict " + emit_field("judge_verdict", judge_verdict))
    if mixed_versions:
        parts.append(
            '<span class="microlabel">graph version</span> '
            + _chip("graph_version", ex.envelope.get("graph_version"))
        )
    html = '<p class="record-line">' + " · ".join(parts) + "</p>"
    if extra_note:
        html += f'<p class="caption">{extra_note}</p>'
    if superseded:
        entries = "; ".join(
            f"seq {e.seq}, {_esc(e.ts)}, " + _status_badge(e.envelope.get("status"))
            for e in superseded
        )
        html += (
            '<div class="call-history">call history, superseded by the record'
            f" above: {entries}</div>"
        )
    return html + _flags_html(ex)


def _placeholder(tool: str) -> str:
    return f'<p class="placeholder">{_esc(tool)}: not recorded in this session</p>'


def _identity_of(ex: Exchange) -> Any:
    ans = _answer(ex)
    req = ex.request if isinstance(ex.request, dict) else {}
    if ex.tool in ("explain_requirement", "evaluate_project_evidence"):
        return ans.get("norm_id") or req.get("norm_id")
    if ex.tool == "trace_alignment":
        return req.get("id") or ans.get("id")
    if ex.tool == "resolve_span":
        return ans.get("span_id") or req.get("span_id")
    if ex.tool == "source_trace":
        return ans.get("node_id") or req.get("node_id")
    return None


def _build_model(
    exchanges: list[Exchange],
) -> tuple[dict[tuple[str, Any], Exchange], dict[tuple[str, Any], list[Exchange]]]:
    latest: dict[tuple[str, Any], Exchange] = {}
    history: dict[tuple[str, Any], list[Exchange]] = {}
    for ex in exchanges:
        key = (ex.tool, _identity_of(ex))
        if key in latest:
            history.setdefault(key, []).append(latest[key])
        latest[key] = ex
    return latest, history


def _latest_for_tool(
    latest: dict[tuple[str, Any], Exchange], tool: str
) -> list[Exchange]:
    found = [ex for (t, _), ex in latest.items() if t == tool]
    found.sort(key=lambda e: (e.seq, e.order))
    return found


def _collect_versions(
    exchanges: list[Exchange],
) -> tuple[list[tuple[str, int]], list[str]]:
    entries: list[tuple[str, int]] = []
    for ex in exchanges:
        gv = ex.envelope.get("graph_version")
        if gv is not None:
            entries.append((str(gv), ex.seq))
        ans = _answer(ex)
        summary = ans.get("summary")
        if isinstance(summary, dict) and summary.get("norms_build_id") is not None:
            entries.append((str(summary["norms_build_id"]), ex.seq))
        if ans.get("alignments_build_id") is not None:
            entries.append((str(ans["alignments_build_id"]), ex.seq))
    versions = list(dict.fromkeys(v for v, _ in entries))
    return entries, versions


def _tier(classify_ex: Exchange | None) -> str:
    if classify_ex is None:
        return "unclassified"
    ans = _answer(classify_ex)
    if not ans:
        return "uncertain"
    if ans.get("prohibited") is True or ans.get("risk_category") == "prohibited":
        return "prohibited"
    risk_category = ans.get("risk_category")
    if (
        risk_category is None
        or classify_ex.envelope.get("status") == "requires_human_review"
    ):
        return "uncertain"
    if risk_category == "minimal_or_none":
        return "minimal"
    return "full"


def _system_name(
    classify_ex: Exchange | None, session_names: list[str]
) -> tuple[str, bool]:
    """(heading html-ready text or field value, carried_by_envelope)."""
    if classify_ex is not None and isinstance(classify_ex.request, dict):
        features = classify_ex.request.get("features")
        if isinstance(features, dict):
            description = features.get("description")
            if isinstance(description, str) and description.strip():
                first = description.strip().splitlines()[0].split(". ")[0].strip()
                if len(first) > 80:
                    # Cut at a word boundary so the heading never ends
                    # mid-word ("creditworthiness o...").
                    cut = first[:77]
                    if " " in cut:
                        cut = cut.rsplit(" ", 1)[0]
                    first = cut.rstrip(" ,;:") + "..."
                return first, True
    if session_names:
        return session_names[0], False
    return "system identity not recorded", False


def _generated_range(exchanges: list[Exchange]) -> list[str]:
    values = sorted(
        {
            str(ex.envelope["generated_at"])
            for ex in exchanges
            if ex.envelope.get("generated_at") is not None
        }
    )
    if not values:
        return []
    if len(values) == 1:
        return [values[0]]
    return [values[0], values[-1]]


def _deslug_hleg(target_id: Any) -> str:
    slug = str(target_id)
    slug = slug.split(":", 1)[1] if ":" in slug else slug
    return " ".join(part.title() for part in slug.split("-") if part)


_CITATION_PREFIXES = ("eu-ai-act:", "norm:eu-ai-act:")


def _citation_chips(text: Any) -> str:
    """Chips for provision ids mentioned inside a rationale line."""
    ids = re.findall(r"(?:norm:)?eu-ai-act:[a-z0-9:.()-]+[a-z0-9)]", str(text))
    unique = list(dict.fromkeys(ids))
    return " ".join(_chip("citation", i) for i in unique)


def _list_items(field_name: str, values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "".join(f"<li>{emit_field(field_name, v)}</li>" for v in values)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_head(
    *,
    name_text: str,
    name_from_envelope: bool,
    versions: list[str],
    version_entries: list[tuple[str, int]],
    mixed: bool,
    generated_range: list[str],
    source_names: list[str],
    repo_ref: str | None,
    notice: str | None,
    header_flags: list[str],
) -> str:
    out: list[str] = []
    out.append(
        f'<header><p class="kicker">{_esc(_KICKER)}</p>'
        f'<p class="kicker">{_esc(_SUBKICKER)}</p>'
    )
    # The non-legal-advice notice precedes every heading: the first thing a
    # reader (or a cropped screenshot) meets is what this document is not.
    notice_value = notice if notice is not None else NON_LEGAL_ADVICE_NOTICE
    if notice is None:
        out.append(
            '<p class="flag">no envelope carried a non_legal_advice_notice;'
            " the package default is shown</p>"
        )
    out.append(
        f'<div class="notice">{emit_field("non_legal_advice_notice", notice_value)}'
        "</div>"
    )
    if name_from_envelope:
        out.append(f"<h1>{emit_field('description', name_text)}</h1>")
    else:
        out.append(f"<h1>{_esc(name_text)}</h1>")

    for flag in header_flags:
        out.append(f'<p class="flag">{_esc(flag)}</p>')

    if mixed:
        listing = "".join(
            "<li>"
            + _chip("graph_version", version)
            + " (seq "
            + ", ".join(
                str(seq)
                for seq in dict.fromkeys(
                    s for v, s in version_entries if v == version
                )
            )
            + ")</li>"
            for version in versions
        )
        out.append(
            '<div class="banner document-failure"><p class="microlabel">'
            "document integrity</p><p><strong>MIXED GRAPH VERSIONS</strong>:"
            " the recorded envelopes cite more than one graph build. Each card"
            " below is stamped with its own version and data is not joined"
            " across versions. The report still renders; the mismatch is the"
            f" finding.</p><ul>{listing}</ul></div>"
        )

    version_dd = (
        _chip("graph_version", versions[0])
        if (versions and not mixed)
        else ("mixed, see banner above" if mixed else "not recorded")
    )
    if len(generated_range) == 2:
        range_dd = (
            emit_field("generated_at", generated_range[0])
            + " to "
            + emit_field("generated_at", generated_range[1])
        )
    elif len(generated_range) == 1:
        range_dd = emit_field("generated_at", generated_range[0])
    else:
        range_dd = "not recorded"
    repo_dd = (
        emit_field("repo_ref", repo_ref)
        if repo_ref
        else "repository state not recorded"
    )
    out.append(
        '<dl class="identity">'
        f"<div><dt>graph version</dt><dd>{version_dd}</dd></div>"
        f"<div><dt>generated</dt><dd>{range_dd}</dd></div>"
        f"<div><dt>input files</dt><dd>{_esc(', '.join(source_names))}</dd></div>"
        f"<div><dt>repository state</dt><dd>{repo_dd}</dd></div>"
        "</dl>"
    )

    rows = "".join(
        f'<tr><td><span class="status" data-status="{_esc(s)}">{_esc(s)}</span></td>'
        f"<td>{_esc(_STATUS_LEGEND[s])}</td></tr>"
        for s in STATUS_VOCABULARY
    )
    out.append(
        '<div class="table-wrap"><table><thead><tr><th>status</th>'
        f"<th>meaning</th></tr></thead><tbody>{rows}</tbody></table></div>"
        f"<p class='caption'>{_esc(_LEGEND_SENTENCE)}</p></header>"
    )
    return "".join(out)


def _render_prohibition_banner(
    classify_ex: Exchange | None,
    requirements_ex: Exchange | None,
    matrix_ex: Exchange | None,
) -> str:
    out: list[str] = ['<div class="prohibition-banner">']
    out.append('<p class="microlabel">recorded result</p>')
    req_ans = _answer(requirements_ex)
    message = req_ans.get("message")
    if message is not None:
        out.append(_verbatim_block("message", message))
    else:
        out.append(
            '<p class="placeholder">the classification records this system as'
            " prohibited; the requirements call carrying the recorded message"
            " was not recorded in this session</p>"
        )
    banner_ex = requirements_ex or classify_ex
    if banner_ex is not None:
        nodes = banner_ex.envelope.get("source_nodes")
        if isinstance(nodes, list) and nodes:
            out.append(
                "<p>"
                + " ".join(_chip("source_nodes", n) for n in nodes)
                + "</p>"
            )
        out.append(_legal_notes_html(banner_ex))

    # Any recorded tags render here as claims against a prohibited system.
    matrix_ans = _answer(matrix_ex)
    if matrix_ans:
        claims: list[tuple[str, str, Any]] = []
        for row in matrix_ans.get("matrix") or []:
            for loc in row.get("trace_locations") or []:
                claims.append(
                    (row.get("norm_id"), loc.get("path"), loc.get("line"))
                )
        for group in ("out_of_scope_tags", "invalid_tags"):
            for t in matrix_ans.get(group) or []:
                claims.append((t.get("norm_id"), t.get("path"), t.get("line")))
        if claims:
            items = "".join(
                "<li>"
                + _chip("norm_id", norm_id)
                + " "
                + emit_field("path", f"{path}:{line}")
                + "</li>"
                for norm_id, path, line in claims
            )
            out.append(
                '<p class="microlabel">code claims against a prohibited'
                f" system</p><ul>{items}</ul>"
            )
    out.append("</div>")
    return "".join(out)


def _render_summary_band(
    *,
    tier: str,
    requirements_ex: Exchange | None,
    matrix_ex: Exchange | None,
    backlog_ex: Exchange | None,
    evidence_exs: list[Exchange],
) -> str:
    out = ['<section class="summary-band"><h2>Summary figures</h2>']
    if tier == "prohibited":
        out.append(
            '<p class="placeholder">summary figures are not rendered: the'
            " recorded classification is an Article 5 prohibition (see the"
            " banner above)</p></section>"
        )
        return "".join(out)
    if tier == "minimal":
        out.append(
            '<p class="placeholder">summary figures are not rendered: the'
            " recorded classification is minimal_or_none (see the"
            " classification section)</p></section>"
        )
        return "".join(out)

    def figure(label: str, value_html: str, qualifier: str = "") -> str:
        q = f'<span class="qualifier">{_esc(qualifier)}</span>' if qualifier else ""
        return (
            f'<div class="figure"><span class="qualifier">{_esc(label)}</span>'
            f'<span class="number">{value_html}</span>{q}</div>'
        )

    figures: list[str] = []
    req_summary = _answer(requirements_ex).get("summary")
    req_summary = req_summary if isinstance(req_summary, dict) else {}
    if requirements_ex is not None:
        figures.append(
            figure(
                "applicable requirements returned",
                emit_field("returned", req_summary.get("returned")),
            )
        )
        figures.append(
            figure(
                "requiring human review",
                emit_field(
                    "needs_human_review_total",
                    req_summary.get("needs_human_review_total"),
                ),
                "review-queue transparency count; never returned as requirements",
            )
        )
    else:
        figures.append(
            figure(
                "applicable requirements returned",
                '<span class="muted">&#183;</span>',
                "get_applicable_requirements not recorded in this session",
            )
        )
    matrix_summary = _answer(matrix_ex).get("summary")
    matrix_summary = matrix_summary if isinstance(matrix_summary, dict) else {}
    if matrix_ex is not None:
        figures.append(
            figure(
                "traced",
                emit_field("traced", matrix_summary.get("traced")),
                "claimed in code; a trace is a claim, not evidence",
            )
        )
        figures.append(
            figure("untraced", emit_field("untraced", matrix_summary.get("untraced")))
        )
        figures.append(
            figure(
                "invalid tags",
                emit_field("invalid_tags", matrix_summary.get("invalid_tags")),
            )
        )
    else:
        figures.append(
            figure(
                "traced",
                '<span class="muted">&#183;</span>',
                "trace_implementation not recorded in this session; "
                "a trace is a claim, not evidence",
            )
        )
    backlog_items = _answer(backlog_ex).get("items")
    if isinstance(backlog_items, list):
        figures.append(
            figure("backlog items", emit_field("items", len(backlog_items)))
        )
    if evidence_exs:
        counts: dict[str, int] = {}
        for ex in evidence_exs:
            status = str(ex.envelope.get("status"))
            counts[status] = counts.get(status, 0) + 1
        listing = ", ".join(
            f"{_esc(status)} {count}" for status, count in sorted(counts.items())
        )
        figures.append(
            figure("evidence evaluations by status", f"<span>{listing}</span>")
        )
    out.append('<div class="figure-band">' + "".join(figures) + "</div>")
    out.append("</section>")
    return "".join(out)


def _render_fria(fria: Any) -> str:
    if not isinstance(fria, dict):
        return ""
    out = ['<h3>Fundamental rights impact assessment (Article 27)</h3>']
    out.append(
        '<dl class="pairs"><div><dt>applicability</dt><dd>'
        + emit_field("applicability", fria.get("applicability"))
        + "</dd></div></dl>"
    )
    rationale = fria.get("rationale")
    if isinstance(rationale, list) and rationale:
        out.append(
            "<ol>"
            + "".join(
                f"<li>{emit_field('rationale', line)} {_citation_chips(line)}</li>"
                for line in rationale
            )
            + "</ol>"
        )
    basis = fria.get("basis_nodes")
    if isinstance(basis, list) and basis:
        out.append(
            "<p>" + " ".join(_chip("basis_nodes", n) for n in basis) + "</p>"
        )
    applies_from = fria.get("applies_from")
    if isinstance(applies_from, dict):
        out.append(
            '<dl class="pairs">'
            "<div><dt>applies from</dt><dd>"
            + emit_field("date", applies_from.get("date"))
            + "</dd></div><div><dt>meaning</dt><dd>"
            + emit_field("meaning", applies_from.get("meaning"))
            + "</dd></div><div><dt>legal status</dt><dd>"
            + _token("legal_status", applies_from.get("legal_status"))
            + "</dd></div>"
        )
        if applies_from.get("source") is not None:
            out.append(
                "<div><dt>source</dt><dd>"
                + emit_field("source", applies_from.get("source"))
                + "</dd></div>"
            )
        out.append("</dl>")
    if fria.get("note") is not None:
        out.append(f'<p class="caption">{emit_field("note", fria.get("note"))}</p>')
    if isinstance(fria.get("missing_facts"), list) and fria["missing_facts"]:
        out.append(
            '<p class="microlabel">missing facts</p><ul>'
            + _list_items("missing_facts", fria["missing_facts"])
            + "</ul>"
        )
    return "".join(out)


def _render_classification(
    classify_ex: Exchange | None,
    tier: str,
    mixed: bool,
    superseded: list[Exchange],
) -> str:
    out = ['<section data-section="classification"><h2>Classification</h2>']
    if classify_ex is None:
        out.append(_placeholder("classify_ai_system"))
        out.append("</section>")
        return "".join(out)
    ans = _answer(classify_ex)
    reclassified = ""
    if superseded and isinstance(classify_ex.request, dict):
        latest_features = classify_ex.request.get("features")
        for earlier in superseded:
            if (
                isinstance(earlier.request, dict)
                and earlier.request.get("features") != latest_features
            ):
                reclassified = "re-classified: inputs changed"
                break
    out.append(
        '<dl class="pairs">'
        "<div><dt>risk category</dt><dd>"
        + emit_field("risk_category", ans.get("risk_category"))
        + "</dd></div><div><dt>prohibited</dt><dd>"
        + emit_field("prohibited", ans.get("prohibited"))
        + "</dd></div><div><dt>Annex III category</dt><dd>"
        + emit_field("annex_iii_category", ans.get("annex_iii_category"))
        + "</dd></div><div><dt>Article 6(3) exception candidate</dt><dd>"
        + emit_field(
            "article_6_3_exception_candidate",
            ans.get("article_6_3_exception_candidate"),
        )
        + "</dd></div></dl>"
    )
    rationale = ans.get("rationale")
    if isinstance(rationale, list) and rationale:
        out.append('<p class="microlabel">rule ladder</p><ol>')
        for line in rationale:
            out.append(
                f"<li>{emit_field('rationale', line)} {_citation_chips(line)}</li>"
            )
        out.append("</ol>")
    missing_facts = classify_ex.envelope.get("missing_facts")
    if isinstance(missing_facts, list) and missing_facts:
        label = (
            "open questions (this list is the to-do: the classification cannot"
            " settle until they are answered)"
            if tier == "uncertain"
            else "missing facts"
        )
        out.append(
            f'<p class="microlabel">{_esc(label)}</p><ul>'
            + _list_items("missing_facts", missing_facts)
            + "</ul>"
        )
    out.append(_render_fria(ans.get("fria")))
    out.append(_legal_notes_html(classify_ex))
    out.append(_record_line(classify_ex, mixed, superseded, reclassified))
    out.append("</section>")
    return "".join(out)


def _provisional_notice(ans: dict[str, Any], tier: str) -> str:
    out: list[str] = []
    if ans.get("provisional") is True:
        note = ans.get("provisional_note")
        out.append(
            '<div class="notice"><p class="microlabel">provisional</p>'
            + (
                emit_field("provisional_note", note, block=True)
                if note is not None
                else "<p>the recorded answer is marked provisional</p>"
            )
            + "</div>"
        )
    elif tier == "uncertain":
        out.append(
            '<div class="notice"><p class="microlabel">provisional</p>'
            "<p>the recorded classification is unsettled (open questions in"
            " the classification section), so this section is provisional"
            "</p></div>"
        )
    return "".join(out)


def _render_requirements(
    requirements_ex: Exchange | None,
    tier: str,
    mixed: bool,
    superseded: list[Exchange],
    explain_exs: list[Exchange],
) -> str:
    out = ['<section data-section="requirements"><h2>Applicable requirements</h2>']
    if requirements_ex is None:
        out.append(_placeholder("get_applicable_requirements"))
        if tier == "uncertain":
            out.append(_provisional_notice({}, tier))
        out.append("</section>")
        return "".join(out)
    ans = _answer(requirements_ex)
    out.append(_provisional_notice(ans, tier))

    if tier == "prohibited":
        out.append(
            '<p class="placeholder">no engineering requirements are recorded'
            " for a prohibited system; the recorded message renders in the"
            " banner on page one</p>"
        )
    elif tier == "minimal" and ans.get("message") is not None:
        out.append(
            '<div class="notice"><p class="microlabel">recorded result</p>'
            + _verbatim_block("message", ans.get("message"))
            + "</div>"
        )

    by_article = ans.get("requirements_by_article")
    by_article = by_article if isinstance(by_article, dict) else {}
    for article, norms in by_article.items():
        if not isinstance(norms, list):
            continue
        out.append(
            f"<h3>{emit_field('article', article)} "
            + _chip("source_node", f"eu-ai-act:{article}")
            + "</h3>"
        )
        for norm in norms:
            if not isinstance(norm, dict):
                continue
            meta_parts = [
                emit_field("deontic_type", norm.get("deontic_type")),
                emit_field("modal", norm.get("modal")),
                "actor " + emit_field("actor", norm.get("actor")),
            ]
            if norm.get("actor_source") is not None:
                meta_parts.append(
                    "(" + emit_field("actor_source", norm.get("actor_source")) + ")"
                )
            conditions = norm.get("conditions") or []
            exceptions = norm.get("exceptions") or []
            details = ""
            if conditions or exceptions:
                inner = ""
                if conditions:
                    inner += (
                        '<p class="microlabel">conditions</p><ul>'
                        + _list_items("conditions", conditions)
                        + "</ul>"
                    )
                if exceptions:
                    inner += (
                        '<p class="microlabel">exceptions</p><ul>'
                        + _list_items("exceptions", exceptions)
                        + "</ul>"
                    )
                details = (
                    "<details><summary>conditions and exceptions</summary>"
                    + inner
                    + "</details>"
                )
            out.append(
                '<div class="norm-row">'
                + _chip("norm_id", norm.get("norm_id"))
                + " "
                + _chip("source_span_id", norm.get("source_span_id"))
                + f'<p class="meta-line">{" · ".join(meta_parts)}</p>'
                + "<p>"
                + emit_field("action", norm.get("action"))
                + " "
                + emit_field("object", norm.get("object"))
                + "</p>"
                + details
                + f'<p class="meta-line">{_status_badge(requirements_ex.envelope.get("status"))}</p>'
                + "</div>"
            )

    summary = ans.get("summary")
    if isinstance(summary, dict):
        out.append(
            '<h3>Requirements summary</h3><dl class="pairs">'
            "<div><dt>total accepted in scope</dt><dd>"
            + emit_field(
                "total_accepted_in_scope", summary.get("total_accepted_in_scope")
            )
            + "</dd></div><div><dt>returned</dt><dd>"
            + emit_field("returned", summary.get("returned"))
            + "</dd></div><div><dt>needs human review</dt><dd>"
            + emit_field(
                "needs_human_review_total", summary.get("needs_human_review_total")
            )
            + "</dd></div></dl>"
        )
        if summary.get("needs_human_review_note") is not None:
            out.append(
                '<p class="caption">'
                + emit_field(
                    "needs_human_review_note",
                    summary.get("needs_human_review_note"),
                )
                + "</p>"
            )

    for explain_ex in explain_exs:
        explain_ans = _answer(explain_ex)
        deontic = explain_ans.get("deontic")
        deontic = deontic if isinstance(deontic, dict) else {}
        out.append(
            '<details><summary>explain_requirement record for '
            + _esc(explain_ans.get("norm_id"))
            + "</summary>"
            + _chip("norm_id", explain_ans.get("norm_id"))
        )
        if explain_ans.get("review_note") is not None:
            out.append(
                f'<p class="caption">{emit_field("review_note", explain_ans.get("review_note"))}</p>'
            )
        out.append(
            "<p>"
            + emit_field("deontic_type", deontic.get("deontic_type"))
            + " · "
            + emit_field("modal", deontic.get("modal"))
            + " · "
            + emit_field("action", deontic.get("action"))
            + " "
            + emit_field("object", deontic.get("object"))
            + "</p>"
        )
        out.append(_record_line(explain_ex, mixed, []))
        out.append("</details>")
        notes = _legal_notes_html(explain_ex)
        if notes:
            out.append(notes)

    out.append(_legal_notes_html(requirements_ex))
    out.append(_record_line(requirements_ex, mixed, superseded))
    out.append("</section>")
    return "".join(out)


def _render_matrix(
    matrix_ex: Exchange | None,
    requirements_ex: Exchange | None,
    tier: str,
    mixed: bool,
    superseded: list[Exchange],
) -> str:
    out = [
        '<section data-section="trace_matrix"><h2>Traceability matrix</h2>'
    ]
    fixed_sentence = f'<p class="caption">{_esc(FIXED_TRACE_SENTENCE)}</p>'

    if tier == "prohibited":
        out.append(
            '<p class="placeholder">the traceability matrix is not rendered'
            " for a prohibited system: an empty matrix would imply nothing"
            " left to do. Recorded tags render in the banner on page one as"
            " code claims against a prohibited system.</p>"
        )
        out.append(fixed_sentence)
        out.append("</section>")
        return "".join(out)
    if tier == "minimal":
        out.append(
            '<p class="placeholder">the traceability matrix is not rendered'
            " for a minimal_or_none classification; recorded tags are listed"
            " below as claims out of scope</p>"
        )
        matrix_ans = _answer(matrix_ex)
        claims = []
        for row in matrix_ans.get("matrix") or []:
            for loc in row.get("trace_locations") or []:
                claims.append((row.get("norm_id"), loc.get("path"), loc.get("line")))
        for group in ("out_of_scope_tags", "invalid_tags"):
            for t in matrix_ans.get(group) or []:
                claims.append((t.get("norm_id"), t.get("path"), t.get("line")))
        if claims:
            out.append(
                "<ul>"
                + "".join(
                    "<li>"
                    + _chip("norm_id", norm_id)
                    + " "
                    + emit_field("path", f"{path}:{line}")
                    + "</li>"
                    for norm_id, path, line in claims
                )
                + "</ul>"
            )
        out.append(fixed_sentence)
        out.append("</section>")
        return "".join(out)

    if matrix_ex is None:
        out.append(_placeholder("trace_implementation"))
        out.append(fixed_sentence)
        out.append("</section>")
        return "".join(out)

    ans = _answer(matrix_ex)
    join_allowed = (not mixed) or (
        requirements_ex is not None
        and matrix_ex.envelope.get("graph_version")
        == requirements_ex.envelope.get("graph_version")
    )
    norm_index: dict[str, dict[str, Any]] = {}
    if requirements_ex is not None and join_allowed:
        for norms in (_answer(requirements_ex).get("requirements_by_article") or {}).values():
            if isinstance(norms, list):
                for n in norms:
                    if isinstance(n, dict) and n.get("norm_id"):
                        norm_index[n["norm_id"]] = n

    rows_html: list[str] = []
    matrix_rows = [r for r in (ans.get("matrix") or []) if isinstance(r, dict)]
    for row in matrix_rows:
        norm_id = row.get("norm_id")
        joined = norm_index.get(norm_id) if isinstance(norm_id, str) else None
        sentence = ""
        if joined is not None:
            sentence = (
                '<p class="meta-line">'
                + emit_field("action", joined.get("action"))
                + " "
                + emit_field("object", joined.get("object"))
                + "</p>"
            )
        alignments = row.get("hleg_alignments") or []
        if alignments:
            alignment_cell = "<br>".join(
                _chip("target_id", a.get("target_id"))
                + " "
                + emit_field("relation_type", a.get("relation_type"))
                + " "
                + emit_field("final_score", a.get("final_score"))
                for a in alignments
                if isinstance(a, dict)
            )
        else:
            alignment_cell = '<span class="muted">none recorded</span>'
        locations = row.get("trace_locations") or []
        if locations:
            location_cell = "<br>".join(
                emit_field("trace_locations", f"{loc.get('path')}:{loc.get('line')}")
                for loc in locations
                if isinstance(loc, dict)
            )
        else:
            location_cell = (
                '<span class="muted">no @implements tag found</span>'
            )
        rows_html.append(
            "<tr data-trace-row>"
            f"<td>{_chip('norm_id', norm_id)}{sentence}</td>"
            f"<td>{emit_field('article', row.get('article'))}</td>"
            f"<td>{_chip('source_span_id', row.get('source_span_id'))}</td>"
            f"<td>{alignment_cell}</td>"
            f"<td>{location_cell}</td>"
            f"<td>{_token('trace_status', row.get('trace_status'))}</td>"
            "</tr>"
        )
    out.append(
        '<div class="table-wrap"><table><thead><tr><th>Norm</th><th>Article</th>'
        "<th>Source span</th><th>HLEG alignments</th><th>Code locations</th>"
        f"<th>Trace</th></tr></thead><tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    if mixed and not join_allowed:
        out.append(
            '<p class="flag">requirement sentences are not joined into the'
            " matrix: the matrix and requirements envelopes cite different"
            " graph versions</p>"
        )

    trace_note = ans.get("trace_note")
    if trace_note is not None:
        out.append(f'<p class="caption">{emit_field("trace_note", trace_note)}</p>')
        if FIXED_TRACE_SENTENCE not in str(trace_note):
            out.append(fixed_sentence)
    else:
        out.append(fixed_sentence)
        out.append(
            '<p class="flag">the recorded envelope carried no trace_note; the'
            " fixed sentence above was inserted by the report generator</p>"
        )
    hleg_caveat = ans.get("hleg_caveat") or ans.get("caveat")
    if hleg_caveat is not None:
        out.append(
            f'<p class="caption">{emit_field("hleg_caveat", hleg_caveat)}</p>'
        )
    else:
        out.append(f'<p class="caption">{_esc(HLEG_MAPPING_CAVEAT)}</p>')
        out.append(
            '<p class="flag">the recorded envelope carried no hleg_caveat;'
            " the fixed caveat above was inserted by the report generator</p>"
        )

    untraced_rows = [
        r for r in matrix_rows if r.get("trace_status") != "traced"
    ]
    tag_convention = str(ans.get("tag_convention") or "@implements: <norm-id>")
    if untraced_rows:
        out.append("<h3>To do: untraced requirements</h3><ul class='todo'>")
        for row in untraced_rows:
            norm_id = row.get("norm_id")
            joined = norm_index.get(norm_id) if isinstance(norm_id, str) else None
            sentence = ""
            if joined is not None:
                sentence = (
                    " "
                    + emit_field("action", joined.get("action"))
                    + " "
                    + emit_field("object", joined.get("object"))
                )
            tag_line = tag_convention.replace("<norm-id>", str(norm_id))
            out.append(
                "<li>[ ] "
                + _chip("norm_id", norm_id)
                + sentence
                + f'<br><code class="tag-line">{_esc(tag_line)}</code></li>'
            )
        out.append("</ul>")
        out.append(
            "<p>Adding a tag records a claim only. The evidence route is"
            " evaluate_project_evidence: submit artifacts there to move a"
            " norm up the calibrated evidence ladder.</p>"
        )

    invalid_tags = [t for t in (ans.get("invalid_tags") or []) if isinstance(t, dict)]
    if invalid_tags:
        out.append("<h3>Invalid tags</h3><div class='table-wrap'><table><thead>")
        out.append(
            "<tr><th>Norm id cited</th><th>Location</th><th>Reason</th></tr>"
            "</thead><tbody>"
        )
        for t in invalid_tags:
            out.append(
                '<tr class="defect-error">'
                f"<td>{_chip('norm_id', t.get('norm_id'))}</td>"
                f"<td>{emit_field('path', str(t.get('path')) + ':' + str(t.get('line')))}</td>"
                f"<td>{emit_field('reason', t.get('reason'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
    out_of_scope = [
        t for t in (ans.get("out_of_scope_tags") or []) if isinstance(t, dict)
    ]
    if out_of_scope:
        out.append(
            "<h3>Out-of-scope tags</h3><p class='caption'>These tags cite real"
            " judge-accepted norms, but norms not applicable to this"
            " classification. They are recorded as warnings, never joined into"
            " the matrix.</p><div class='table-wrap'><table><thead>"
            "<tr><th>Norm id cited</th><th>Location</th></tr></thead><tbody>"
        )
        for t in out_of_scope:
            out.append(
                "<tr>"
                f"<td>{_chip('norm_id', t.get('norm_id'))}</td>"
                f"<td>{emit_field('path', str(t.get('path')) + ':' + str(t.get('line')))}</td></tr>"
            )
        out.append("</tbody></table></div>")

    out.append(_legal_notes_html(matrix_ex))
    out.append(_record_line(matrix_ex, mixed, superseded))
    out.append("</section>")
    return "".join(out)


def _judge_record_html(source: dict[str, Any], envelope: dict[str, Any]) -> str:
    parts = ['<div class="judge-record"><p class="microlabel">judge record</p>']
    parts.append(
        '<p class="record-line">verdict '
        + _token("judge_verdict", envelope.get("judge_verdict"))
    )
    if source.get("judge_model") is not None:
        parts.append(" · model " + emit_field("judge_model", source.get("judge_model")))
    if source.get("judge_run_id") is not None:
        parts.append(
            " · run " + emit_field("judge_run_id", source.get("judge_run_id"))
        )
    parts.append("</p>")
    if source.get("judge_rationale") is not None:
        parts.append(_verbatim_block("judge_rationale", source.get("judge_rationale")))
    parts.append("</div>")
    return "".join(parts)


def _render_backlog(
    backlog_ex: Exchange | None, mixed: bool, superseded: list[Exchange]
) -> str:
    out = ['<section data-section="backlog"><h2>Control backlog</h2>']
    if backlog_ex is None:
        out.append(
            '<p class="placeholder">generate_control_backlog: not recorded in'
            " this session. Backlog generation is the paid model-generation"
            " step; run it against the recorded classification to draft"
            " control items.</p></section>"
        )
        return "".join(out)
    ans = _answer(backlog_ex)
    items = [i for i in (ans.get("items") or []) if isinstance(i, dict)]
    out.append("<ol>")
    for item in items:
        norm_chips = " ".join(
            _chip("norm_ids", n) for n in (item.get("norm_ids") or [])
        )
        evidence_tokens = " ".join(
            _token("suggested_evidence", s)
            for s in (item.get("suggested_evidence") or [])
        )
        out.append(
            "<li><p><strong>"
            + emit_field("title", item.get("title"))
            + "</strong> "
            + _token("priority", item.get("priority"))
            + "</p><p>"
            + emit_field("description", item.get("description"))
            + f"</p><p>{norm_chips}</p>"
            + (
                f'<p><span class="microlabel">suggested evidence</span> {evidence_tokens}</p>'
                if evidence_tokens
                else ""
            )
            + "</li>"
        )
    out.append("</ol>")
    dropped = ans.get("dropped_items")
    merged = ans.get("merged_items")
    truncated = ans.get("truncated")
    dropped_n = len(dropped) if isinstance(dropped, list) else dropped
    merged_n = len(merged) if isinstance(merged, list) else merged
    out.append(
        '<p class="caption">integrity: '
        + emit_field("dropped_items", dropped_n)
        + " items dropped, "
        + emit_field("merged_items", merged_n)
        + " merged, "
        + ("truncated" if truncated else "not truncated")
        + "</p>"
    )
    notes = ans.get("notes")
    if isinstance(notes, list) and notes:
        out.append("<ul>" + _list_items("notes", notes) + "</ul>")
    out.append(_judge_record_html(ans, backlog_ex.envelope))
    out.append(_legal_notes_html(backlog_ex))
    out.append(_record_line(backlog_ex, mixed, superseded))
    out.append("</section>")
    return "".join(out)


def _render_hleg(
    matrix_ex: Exchange | None,
    alignment_exs: list[Exchange],
    mixed: bool,
    history: dict[tuple[str, Any], list[Exchange]],
) -> str:
    out = ['<section data-section="alignment"><h2>HLEG alignment rollup</h2>']
    matrix_ans = _answer(matrix_ex)
    caveat = matrix_ans.get("hleg_caveat") or matrix_ans.get("caveat")
    if caveat is None and alignment_exs:
        caveat = _answer(alignment_exs[0]).get("caveat")
    if caveat is not None:
        out.append(f'<p class="caption">{emit_field("caveat", caveat)}</p>')
    else:
        out.append(f'<p class="caption">{_esc(HLEG_MAPPING_CAVEAT)}</p>')
        if matrix_ex is not None or alignment_exs:
            out.append(
                '<p class="flag">no recorded envelope carried the HLEG caveat;'
                " the fixed caveat above was inserted by the report generator"
                "</p>"
            )

    matrix_rows = [
        r for r in (matrix_ans.get("matrix") or []) if isinstance(r, dict)
    ]
    if matrix_rows:
        agg: dict[str, dict[str, Any]] = {}
        for row in matrix_rows:
            for a in row.get("hleg_alignments") or []:
                if not isinstance(a, dict):
                    continue
                target = str(a.get("target_id"))
                entry = agg.setdefault(
                    target,
                    {"norms": 0, "relations": [], "scores": [], "traced": 0, "untraced": 0},
                )
                entry["norms"] += 1
                relation = a.get("relation_type")
                if relation not in entry["relations"]:
                    entry["relations"].append(relation)
                if isinstance(a.get("final_score"), (int, float)):
                    entry["scores"].append(a["final_score"])
                if row.get("trace_status") == "traced":
                    entry["traced"] += 1
                else:
                    entry["untraced"] += 1
        rows_html = []
        for target in sorted(agg):
            entry = agg[target]
            scores = entry["scores"]
            if scores:
                score_range = (
                    emit_field("final_score", min(scores))
                    + " to "
                    + emit_field("final_score", max(scores))
                    if len(set(scores)) > 1
                    else emit_field("final_score", scores[0])
                )
            else:
                score_range = '<span class="muted">none</span>'
            relations = ", ".join(
                str(emit_field("relation_type", r)) for r in entry["relations"]
            )
            rows_html.append(
                "<tr>"
                f"<td>{_esc(_deslug_hleg(target))}<br>{_chip('target_id', target)}</td>"
                f"<td>{entry['norms']}</td>"
                f"<td>{relations}</td>"
                f"<td>{score_range}</td>"
                f"<td>{entry['traced']} traced, {entry['untraced']} untraced"
                "</td></tr>"
            )
        out.append(
            '<div class="table-wrap"><table><thead><tr>'
            "<th>HLEG requirement</th><th>Aligned norms</th><th>Relations</th>"
            "<th>Score range</th><th>Trace split</th></tr></thead><tbody>"
            + "".join(rows_html)
            + "</tbody></table></div>"
        )
        out.append(
            '<p class="caption">The trace split counts developer claims, not'
            " evidence.</p>"
        )
    elif matrix_ex is None:
        out.append(
            '<p class="placeholder">trace_implementation: not recorded in this'
            " session, so no rollup can be aggregated</p>"
        )
    else:
        out.append(
            '<p class="placeholder">the recorded matrix carries no HLEG'
            " alignments to aggregate</p>"
        )

    for align_ex in alignment_exs:
        align_ans = _answer(align_ex)
        out.append(
            '<div data-section="alignment_trace"><h3>trace_alignment: '
            + _esc(align_ans.get("id"))
            + "</h3>"
        )
        if align_ans.get("caveat") is not None:
            out.append(
                f'<p class="caption">{emit_field("caveat", align_ans.get("caveat"))}</p>'
            )
        for assertion in align_ans.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            out.append(
                "<p>"
                + _chip("source_norm_id", assertion.get("source_norm_id"))
                + " "
                + emit_field("relation_type", assertion.get("relation_type"))
                + " "
                + _chip("target_id", assertion.get("target_id"))
                + " · verdict "
                + _token("judge_verdict", assertion.get("judge_verdict"))
                + "</p>"
            )
            scores = assertion.get("scores")
            if isinstance(scores, dict) and scores:
                score_rows = "".join(
                    f"<tr><td>{_esc(dim)}</td>"
                    f"<td>{emit_field('scores', val)}</td></tr>"
                    for dim, val in scores.items()
                )
                score_rows += (
                    "<tr><td>final</td><td>"
                    + emit_field("final_score", assertion.get("final_score"))
                    + "</td></tr>"
                )
                out.append(
                    '<div class="table-wrap"><table><thead><tr>'
                    "<th>dimension</th><th>score</th></tr></thead>"
                    f"<tbody>{score_rows}</tbody></table></div>"
                )
            evidence = assertion.get("evidence")
            evidence = evidence if isinstance(evidence, dict) else {}
            if evidence.get("source_quote") is not None:
                credential = " ".join(
                    str(_chip("span_id", s))
                    for s in evidence.get("source_evidence_span_ids") or []
                )
                out.append(
                    _verbatim_block(
                        "source_quote", evidence.get("source_quote"), credential
                    )
                )
            if evidence.get("target_quote") is not None:
                credential = " ".join(
                    str(_chip("span_id", s))
                    for s in evidence.get("target_evidence_span_ids") or []
                )
                out.append(
                    _verbatim_block(
                        "target_quote", evidence.get("target_quote"), credential
                    )
                )
            mapping_run = assertion.get("mapping_run")
            if isinstance(mapping_run, dict):
                out.append(
                    '<p class="meta-line">mapping run '
                    + emit_field("id", mapping_run.get("id"))
                    + " · generator "
                    + emit_field("generator_model", mapping_run.get("generator_model"))
                    + " · prompt "
                    + emit_field("prompt_version", mapping_run.get("prompt_version"))
                    + "</p>"
                )
            judge_run = assertion.get("judge_run")
            if isinstance(judge_run, dict):
                out.append(
                    '<p class="meta-line">judge run '
                    + emit_field("id", judge_run.get("id"))
                    + " · judge "
                    + emit_field("judge_model", judge_run.get("judge_model"))
                    + " · prompt "
                    + emit_field("prompt_version", judge_run.get("prompt_version"))
                    + " · verdict "
                    + _token("verdict", judge_run.get("verdict"))
                    + "</p>"
                )
                if judge_run.get("rationale") is not None:
                    out.append(
                        _verbatim_block("rationale", judge_run.get("rationale"))
                    )
        out.append(_legal_notes_html(align_ex))
        out.append(
            _record_line(
                align_ex,
                mixed,
                history.get(("trace_alignment", _identity_of(align_ex)), []),
            )
        )
        out.append("</div>")

    if caveat is not None:
        out.append(f'<p class="caption">{emit_field("caveat", caveat)}</p>')
    else:
        out.append(f'<p class="caption">{_esc(HLEG_MAPPING_CAVEAT)}</p>')
    out.append("</section>")
    return "".join(out)


def _render_evidence(
    evidence_exs: list[Exchange],
    mixed: bool,
    history: dict[tuple[str, Any], list[Exchange]],
) -> str:
    out = ['<section data-section="evidence"><h2>Evidence evaluations</h2>']
    if not evidence_exs:
        out.append(_placeholder("evaluate_project_evidence"))
        out.append("</section>")
        return "".join(out)
    for ex in evidence_exs:
        ans = _answer(ex)
        rejected = ex.envelope.get("status") == "requires_human_review"
        out.append(
            "<div class='norm-row'>"
            + _chip("norm_id", ans.get("norm_id"))
            + " · artifact "
            + _token("artifact_type", ans.get("artifact_type"))
            + " · assessment "
            + _token("assessment", ans.get("assessment"))
        )
        if rejected:
            out.append(
                ' <span class="muted">(not surfaced as-is: the runtime'
                " grounding judge did not accept this assessment; see the"
                " judge record)</span>"
            )
        out.append("</div>")
        for quote in ans.get("quotes") or []:
            out.append(_verbatim_block("quotes", quote))
        gaps = ans.get("gaps")
        if isinstance(gaps, list) and gaps:
            out.append(
                '<p class="microlabel">gaps</p><ul>'
                + _list_items("gaps", gaps)
                + "</ul>"
            )
        if ans.get("rationale") is not None:
            out.append(_verbatim_block("rationale", ans.get("rationale")))
        out.append(_judge_record_html(ans, ex.envelope))
        out.append(_legal_notes_html(ex))
        out.append(
            _record_line(
                ex,
                mixed,
                history.get(("evaluate_project_evidence", _identity_of(ex)), []),
            )
        )
    out.append("</section>")
    return "".join(out)


def _span_credential(span: dict[str, Any]) -> str:
    parts = [str(_chip("span_id", span.get("span_id")))]
    if span.get("snapshot_file") is not None:
        parts.append(str(emit_field("snapshot_file", span.get("snapshot_file"))))
    sha = span.get("sha256")
    if isinstance(sha, str) and sha:
        parts.append(
            f'<span class="chip" title="{_esc(sha)}">'
            + emit_field("sha256", sha[:12])
            + "</span>"
        )
    if span.get("start") is not None and span.get("end") is not None:
        parts.append(
            emit_field("start", span.get("start"))
            + "-"
            + emit_field("end", span.get("end"))
        )
    return " ".join(parts)


def _render_provenance(
    exchanges: list[Exchange],
    resolve_exs: list[Exchange],
    unhomed_exs: list[Exchange],
    mixed: bool,
) -> str:
    out = ['<section data-section="provenance"><h2>Provenance appendix</h2>']
    out.append(
        '<p class="caption">Legal status notes render inside their owning'
        " sections, never only here.</p>"
    )
    # Promoted legal notes for tools whose only home is this appendix.
    for ex in resolve_exs + unhomed_exs:
        notes = _legal_notes_html(ex)
        if notes:
            out.append(notes)

    out.append("<details><summary>per-exchange record</summary>")
    rows = []
    not_recorded = '<span class="muted">not recorded</span>'
    for ex in exchanges:
        ts_cell = emit_field("ts", ex.ts) if ex.ts else not_recorded
        rows.append(
            "<tr>"
            f"<td>{ex.seq}</td>"
            f"<td>{ts_cell}</td>"
            f"<td>{emit_field('tool', ex.tool)}</td>"
            f"<td>{_status_badge(ex.envelope.get('status'))}</td>"
            f"<td>{emit_field('confidence', ex.envelope.get('confidence'))}</td>"
            f"<td>{emit_field('judge_verdict', ex.envelope.get('judge_verdict'))}</td>"
            f"<td>{emit_field('graph_version', ex.envelope.get('graph_version'))}</td>"
            "</tr>"
        )
    out.append(
        '<div class="table-wrap"><table><thead><tr><th>seq</th><th>ts</th>'
        "<th>tool</th><th>status</th><th>confidence</th><th>judge verdict</th>"
        f"<th>graph version</th></tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )

    registry: dict[str, dict[str, Any]] = {}
    for ex in exchanges:
        spans = ex.envelope.get("source_spans")
        if not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict) or span.get("span_id") is None:
                continue
            entry = registry.setdefault(str(span["span_id"]), {})
            for key, value in span.items():
                entry.setdefault(key, value)
    if registry:
        span_rows = []
        for span_id in sorted(registry):
            span = registry[span_id]
            sha = span.get("sha256")
            sha_cell = (
                f'<span title="{_esc(sha)}">' + emit_field("sha256", str(sha)[:12]) + "</span>"
                if isinstance(sha, str) and sha
                else '<span class="muted">not recorded</span>'
            )
            offsets = (
                emit_field("start", span.get("start"))
                + "-"
                + emit_field("end", span.get("end"))
                if span.get("start") is not None and span.get("end") is not None
                else '<span class="muted">not recorded</span>'
            )
            snapshot = (
                emit_field("snapshot_file", span.get("snapshot_file"))
                if span.get("snapshot_file") is not None
                else '<span class="muted">not recorded</span>'
            )
            span_rows.append(
                f"<tr><td>{_chip('span_id', span_id)}</td><td>{snapshot}</td>"
                f"<td>{sha_cell}</td><td>{offsets}</td></tr>"
            )
        out.append(
            "<h3>Span registry</h3>"
            '<div class="table-wrap"><table><thead><tr><th>span</th>'
            "<th>snapshot file</th><th>sha256</th><th>offsets</th></tr>"
            f"</thead><tbody>{''.join(span_rows)}</tbody></table></div>"
        )

    for ex in resolve_exs:
        ans = _answer(ex)
        out.append(
            "<h3>Resolved span "
            + _esc(ans.get("span_id"))
            + "</h3><p>"
            + _span_credential(ans)
            + "</p>"
        )
        if ans.get("text") is not None:
            out.append(
                '<pre class="source-text">'
                + emit_field("text", ans.get("text"))
                + "</pre>"
            )
        out.append(_record_line(ex, mixed, []))

    for ex in unhomed_exs:
        out.append(
            "<h3>Recorded call: "
            + emit_field("tool", ex.tool)
            + f" (seq {ex.seq})</h3>"
        )
        out.append(emit_field("answer", ex.envelope.get("answer"), block=True))
        out.append(_record_line(ex, mixed, []))

    out.append("</details></section>")
    return "".join(out)


def _render_problems(problems: list[ProblemCard]) -> str:
    if not problems:
        return ""
    ordered = sorted(
        enumerate(problems),
        key=lambda pair: (
            pair[1].seq if pair[1].seq is not None else float("inf"),
            pair[0],
        ),
    )
    out = ['<section class="problems"><h2>Recording problems</h2>']
    for _, card in ordered:
        seq_text = f"seq {card.seq}" if card.seq is not None else "seq unknown"
        tool_text = (
            f", claimed tool {_esc(card.claimed_tool)}" if card.claimed_tool else ""
        )
        errors = "".join(f"<li>{_esc(e)}</li>" for e in card.errors)
        out.append(
            '<div class="problem-card"><p class="microlabel">'
            f"{_esc(card.source)}, {_esc(card.position)}, {seq_text}{tool_text}"
            f"</p><ul>{errors}</ul>"
            f'<pre class="source-text">{_esc(card.raw_excerpt)}</pre></div>'
        )
    out.append("</section>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------


def render_report(
    exchanges: list[Exchange],
    problems: list[ProblemCard] | tuple[ProblemCard, ...] = (),
    *,
    source_names: list[str],
    header_flags: list[str] | tuple[str, ...] = (),
) -> str:
    """Render the full report as one self-contained HTML document.

    A pure function of its arguments. There are deliberately no parameters
    that could disable notices, caveats, or sections.
    """
    problems = list(problems)
    header_flags = list(header_flags)
    latest, history = _build_model(exchanges)

    def single(tool: str) -> Exchange | None:
        found = _latest_for_tool(latest, tool)
        return found[-1] if found else None

    def superseded_for(ex: Exchange | None) -> list[Exchange]:
        if ex is None:
            return []
        return history.get((ex.tool, _identity_of(ex)), [])

    classify_ex = single("classify_ai_system")
    requirements_ex = single("get_applicable_requirements")
    matrix_ex = single("trace_implementation")
    backlog_ex = single("generate_control_backlog")
    alignment_exs = _latest_for_tool(latest, "trace_alignment")
    evidence_exs = _latest_for_tool(latest, "evaluate_project_evidence")
    explain_exs = _latest_for_tool(latest, "explain_requirement")
    resolve_exs = _latest_for_tool(latest, "resolve_span")
    unhomed_exs = sorted(
        (ex for (t, _), ex in latest.items() if t not in _HOMED_TOOLS),
        key=lambda e: (e.seq, e.order),
    )

    version_entries, versions = _collect_versions(exchanges)
    mixed = len(versions) > 1
    tier = _tier(classify_ex)

    session_names = [n for n in source_names if str(n).endswith(".jsonl")]
    name_text, name_from_envelope = _system_name(classify_ex, session_names)
    repo_ref = next(
        (ex.repo_ref for ex in exchanges if ex.repo_ref), None
    )
    notice = next(
        (
            ex.envelope["non_legal_advice_notice"]
            for ex in exchanges
            if isinstance(ex.envelope.get("non_legal_advice_notice"), str)
        ),
        None,
    )
    generated_range = _generated_range(exchanges)

    body: list[str] = []
    body.append(
        _render_head(
            name_text=name_text,
            name_from_envelope=name_from_envelope,
            versions=versions,
            version_entries=version_entries,
            mixed=mixed,
            generated_range=generated_range,
            source_names=[str(n) for n in source_names],
            repo_ref=repo_ref,
            notice=notice,
            header_flags=header_flags,
        )
    )
    if tier == "prohibited":
        body.append(
            _render_prohibition_banner(classify_ex, requirements_ex, matrix_ex)
        )
    body.append(
        _render_summary_band(
            tier=tier,
            requirements_ex=requirements_ex,
            matrix_ex=matrix_ex,
            backlog_ex=backlog_ex,
            evidence_exs=evidence_exs,
        )
    )
    body.append(
        _render_classification(classify_ex, tier, mixed, superseded_for(classify_ex))
    )
    body.append(
        _render_requirements(
            requirements_ex, tier, mixed, superseded_for(requirements_ex), explain_exs
        )
    )
    body.append(
        _render_matrix(
            matrix_ex, requirements_ex, tier, mixed, superseded_for(matrix_ex)
        )
    )
    body.append(_render_backlog(backlog_ex, mixed, superseded_for(backlog_ex)))
    body.append(_render_hleg(matrix_ex, alignment_exs, mixed, history))
    body.append(_render_evidence(evidence_exs, mixed, history))
    body.append(_render_provenance(exchanges, resolve_exs, unhomed_exs, mixed))
    body.append(_render_problems(problems))

    notice_value = notice if notice is not None else NON_LEGAL_ADVICE_NOTICE
    footer_bits = [_esc(_SUBKICKER)]
    if versions:
        footer_bits.append(
            "graph "
            + (str(emit_field("graph_version", versions[0])) if not mixed else "mixed versions")
        )
    if generated_range:
        footer_bits.append(
            "generated "
            + " to ".join(str(emit_field("generated_at", g)) for g in generated_range)
        )
    body.append(
        '<footer class="report-footer">'
        f'<div class="notice">{emit_field("non_legal_advice_notice", notice_value)}</div>'
        f'<div class="print-footer">{" · ".join(footer_bits)}</div>'
        "</footer>"
    )

    title = "TERE4AI engineering requirements report"
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body>"
        + "".join(body)
        + "</body></html>\n"
    )


def render_report_from_paths(
    session_paths: list[str | Path],
    envelope_paths: list[str | Path] | tuple[str | Path, ...] = (),
) -> str:
    """Ingest the given files and render the report."""
    result = ingest_inputs(session_paths, envelope_paths)
    return render_report(
        result.exchanges,
        result.problems,
        source_names=result.source_names,
        header_flags=result.header_flags,
    )
