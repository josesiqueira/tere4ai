"""Generate the TERE4AI v2 architecture diagram (SVG) deterministically.

The previous tere4ai_v2_architecture.svg was an unregenerable committed
blob with three stale labels (eIds that do not exist in the source, an
open judge-family decision that was closed 2026-07-08, and a v1-migration
plan that was replaced by regeneration) plus two visual defects
(overlapping edge labels, clipped box text). This script makes the figure
a derived artifact like everything else in the build: run it and the SVG
is rewritten byte-identically (no timestamps, no randomness).

  .venv/bin/python scripts/make_architecture_diagram.py
  inkscape tere4ai_v2_architecture_<date>.svg \
      --export-filename=tere4ai_v2_architecture_<date>.png --export-width=3360

Diagram files carry the date they were produced (DIAGRAM_DATE). A dated
file that no longer matches this generator is history, not an error: bump
DIAGRAM_DATE when the content changes and the previous file stays beside
the new one (tere4ai_v2_architecture_2026-07-19.svg is the first).

Content decisions encoded here (kept in sync with docs/architecture.md):
node IDs are parser-derived, not eIds (Section 6); the judge family is
Anthropic Claude, independent from the OpenAI generator (DEC-07); judge
calls leave the machine just like generator calls (Section 9 sovereignty);
the runtime serves versioned, checksummed JSON dumps and needs no live
database (Neo4j is the build-time store and optional for browsing and RDF
export); uncertain items go to a human review queue and are never served
as accepted. Since 2026-09-17 (B74 session design): the browser consumer
is the tere4ai-dashboard with four views (Build, Evaluate, Use, Research),
the demo web UI is no longer drawn as the product surface, the served
build id carries the publication chain, and Evaluate (measuring the tool)
is drawn as its own phase; a separate evaluation diagram follows.
"""

from __future__ import annotations

from pathlib import Path

W, H = 1680, 2090
FONT = "DejaVu Sans, sans-serif"
BG = "#0b0e14"
INK = "#e6edf3"
MUTED = "#9aa4ad"
FAINT = "#6e7681"
ARROW = "#8b98a5"

DIAGRAM_DATE = "2026-09-17"
OUT_PATH = (
    Path(__file__).resolve().parents[1]
    / f"tere4ai_v2_architecture_{DIAGRAM_DATE}.svg"
)

_parts: list[str] = []


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(
    x: float,
    y: float,
    s: str,
    size: float = 12.5,
    fill: str = MUTED,
    anchor: str = "middle",
    weight: str | None = None,
    spacing: str | None = None,
    style: str | None = None,
) -> None:
    attrs = (
        f'x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'fill="{fill}" text-anchor="{anchor}"'
    )
    if weight:
        attrs += f' font-weight="{weight}"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    if style:
        attrs += f' font-style="{style}"'
    _parts.append(f"<text {attrs}>{esc(s)}</text>")


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    lines: list[str],
    stroke: str,
    fill: str,
    dashed: bool = False,
    title_size: float = 18,
    line_size: float = 12.5,
) -> tuple[float, float, float, float]:
    dash = ' stroke-dasharray="7,5"' if dashed else ""
    _parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2.5"{dash}/>'
    )
    cx = x + w / 2
    text(cx, y + 28, title, size=title_size, fill=stroke, weight="bold")
    ly = y + 50
    for line in lines:
        text(cx, ly, line, size=line_size)
        ly += line_size + 6
    return (x, y, w, h)


def arrow(x1: float, y1: float, x2: float, y2: float, label: str = "", lx: float | None = None, ly: float | None = None) -> None:
    _parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ARROW}" '
        f'stroke-width="1.6" marker-end="url(#ah)"/>'
    )
    if label:
        text(lx if lx is not None else (x1 + x2) / 2 + 8, ly if ly is not None else (y1 + y2) / 2 - 6, label, size=12, fill=FAINT, anchor="start", style="italic")


def zone_label(x: float, y: float, s: str) -> None:
    text(x, y, s, size=15, fill=FAINT, anchor="start", weight="bold", spacing="1.5")


def dashed_arrow(x1: float, y1: float, x2: float, y2: float, label: str = "", lx: float | None = None, ly: float | None = None, anchor: str = "start") -> None:
    _parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{ARROW}" '
        f'stroke-width="1.6" stroke-dasharray="7,5" marker-end="url(#ah)"/>'
    )
    if label:
        text(lx if lx is not None else (x1 + x2) / 2 + 8, ly if ly is not None else (y1 + y2) / 2 - 6, label, size=12, fill=FAINT, anchor=anchor, style="italic")


def build() -> str:
    _parts.clear()
    _parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">'
        '<defs><marker id="ah" markerWidth="11" markerHeight="11" refX="8.5" '
        'refY="4" orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M0,0 L9,4 L0,8 z" fill="{ARROW}"/></marker></defs>'
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>'
    )
    text(W / 2, 52, "TERE4AI v2  Architecture", size=40, fill=INK, weight="bold")
    text(
        W / 2,
        86,
        "Phase 1: self-hosted core; the browser consumer is the tere4ai-dashboard "
        "(a separate repository). The multi-tenant hosted SaaS is Phase 2+ over the same code.",
        size=17,
    )

    # Consumers
    zone_label(40, 136, "CONSUMERS")
    box(
        225, 156, 340, 150, "Coding Agent",
        ["Claude Code, Cursor, ...", "speaks MCP, reads SKILL.md",
         "discovery: /llms.txt, /.well-known",
         "also the dashboard's project door (MCP stdio)"],
        "#a371f7", "#191426",
    )
    box(
        605, 156, 560, 150, "Human (Browser): tere4ai-dashboard",
        ["Build: the graph as a wizard, live progress, layer closing",
         "Evaluate: calibration campaigns, judge runs, specialists",
         "Use: projects, classification, requirements, backlog, traces (the product)",
         "Research (owner only): lineage across phases, numbers, verdicts, exports"],
        "#4493f8", "#0f1a2b",
    )
    box(
        1240, 156, 400, 150, "Phase 2+ consumers",
        ["remote agents, REST clients", "added with the hosted SaaS"],
        "#6e7681", "#11151c", dashed=True,
    )

    # Phase 1 runtime zone
    zone_label(40, 342, "PHASE 1 - RUNTIME (docker compose up)")
    _parts.append(
        '<rect x="225" y="366" width="1425" height="560" rx="16" fill="none" '
        'stroke="#39d2c0" stroke-width="2.5"/>'
    )
    text(250, 392, "SELF-HOSTED: everything inside this frame runs on the user's machine",
         size=15, fill="#39d2c0", anchor="start", weight="bold")

    arrow(395, 306, 448, 436, "MCP (stdio / localhost)", lx=450, ly=350)
    arrow(1000, 306, 800, 636, "HTTP facade", lx=935, ly=480)

    box(
        280, 440, 340, 140, "TERE4AI MCP Server",
        ["Python, FastMCP; stdio or HTTP+keys",
         "8 Section 8 tools + resolve_span",
         "+ batch evidence; free tools are",
         "deterministic, paid tools marked"],
        "#d2649a", "#231018",
    )
    box(
        420, 640, 500, 150, "Domain / Service Layer",
        ["risk classification: deterministic rule ladder,",
         "the LLM never decides the tier (DEC-13)",
         "requirements generation with span citations",
         "runtime grounding judge on every paid answer",
         "calibrated status vocabulary (never 'compliant')"],
        "#e3b341", "#1d1704",
    )
    box(
        1060, 450, 480, 215, "Knowledge graph artifacts",
        ["versioned JSON dumps + frozen snapshots,",
         "every file sha256-checksummed (build chain)",
         "full Act mirror; judged norms; reified HLEG",
         "alignments; provenance on every edge",
         "served build id = snapshot hash + chain",
         "over the exact dump files served (B74)",
         "runtime needs NO live database",
         "Neo4j optional: browsing + n10s RDF export"],
        "#4493f8", "#0d1726",
    )
    arrow(560, 580, 620, 640)
    arrow(920, 700, 1060, 620)
    # Notes sit between the Tier 3 arrow (x 470) and the model-call arrow
    # (x above 1000 at these heights) so no arrow crosses any text.
    text(500, 912, "the graph and project evidence never leave the machine in self-hosted mode",
         size=12.5, fill=FAINT, anchor="start", style="italic")
    for i, line in enumerate((
        "The read-only demo web UI in web/ (shown at MAISA, August 2026) is retained",
        "for the MCP demo recording and screenshots; the dashboard's Use view",
        "supersedes it as the product surface.",
    )):
        text(500, 950 + 18 * i, line, size=12.5, fill=FAINT, anchor="start", style="italic")

    # Sovereignty
    zone_label(40, 996, "RUNTIME MODELS & DATA SOVEREIGNTY")
    box(
        345, 1020, 500, 92, "Local model (Tier 3)",
        ["experimental: fully on-machine, lower quality"],
        "#3fb950", "#0c1a10", dashed=True,
    )
    arrow(470, 790, 470, 1020, "Tier 3 option", lx=380, ly=975)
    _parts.append(
        f'<line x1="70" y1="1150" x2="{W - 70}" y2="1150" stroke="#f85149" '
        'stroke-width="1.6" stroke-dasharray="10,7"/>'
    )
    text(80, 1142, "ON-MACHINE (sovereign)", size=14, fill="#f85149", anchor="start", weight="bold")
    text(W - 80, 1142, "LEAVES THE MACHINE", size=14, fill="#f85149", anchor="end", weight="bold")
    box(
        960, 1180, 600, 150, "Model APIs (runtime internals)",
        ["generator: OpenAI gpt-6-astra (extraction, alignment, answers)",
         "judges: Anthropic Claude claude-opus-5, an independent model",
         "family with uncorrelated failure modes (DEC-07); ids since 2026-09-16 (B74)",
         "temperature 0 requested, provider default where rejected, recorded per build",
         "config from .env, never hardcoded; degraded envelope if absent"],
        "#e3b341", "#1d1403",
    )
    arrow(920, 760, 1180, 1180, "generator + judge calls", lx=1075, ly=1000)

    # Build-time lane
    zone_label(40, 1402, "BUILD-TIME (offline) - producing the knowledge graph")
    lane_y = 1426
    lane_h = 150
    boxes = [
        ("EU AI Act + HLEG", ["OJ text via CELLAR / ELI", "frozen + checksummed"], "#6e7681", "#11151c"),
        ("Deterministic parse", ["structure from frozen HTML", "+ Formex; node IDs derived", "from parsed structure, no LLM;", "cross-refs by rule first"], "#9aa4ad", "#141920"),
        ("LLM extraction", ["deontic norms + HLEG", "alignments (OpenAI", "generator, judged next)"], "#e3b341", "#1d1704"),
        ("JUDGES", ["extraction + mapping judges", "(Anthropic Claude, DEC-07)", "accept / reject / review"], "#a371f7", "#191426"),
        ("Human review queue", ["today: needs_human_review", "items via scripts/review_cli.py", "(accept / reject); rejected", "candidates are dropped;", "never served as accepted"], "#d2649a", "#231018"),
        ("Neo4j KG + gates", ["validation gates G1-G6;", "a failing build is not", "published"], "#4493f8", "#0d1726"),
        ("Versioned dumps", ["published JSON artifacts,", "sha256 build chain;", "what the runtime serves"], "#39d2c0", "#0a1a18"),
    ]
    n = len(boxes)
    gap = 18
    bw = (W - 80 - gap * (n - 1)) / n
    x = 40
    queue_bottom = (0.0, 0.0)
    dumps_bottom = (0.0, 0.0)
    for i, (title, lines, stroke, fill) in enumerate(boxes):
        box(x, lane_y, bw, lane_h, title, lines, stroke, fill, title_size=15.5, line_size=11.5)
        if title == "Human review queue":
            queue_bottom = (x + bw / 2, lane_y + lane_h)
        if title == "Versioned dumps":
            dumps_bottom = (x + bw / 2, lane_y + lane_h)
        if i < n - 1:
            arrow(x + bw, lane_y + lane_h / 2, x + bw + gap, lane_y + lane_h / 2)
        x += bw + gap
    text(
        40, lane_y + lane_h + 28,
        "Full structural mirror; deep extraction only on the high-risk core. "
        "The v1 poster query is kept as a regression fixture over the regenerated graph.",
        size=12.5, fill=FAINT, anchor="start", style="italic",
    )
    text(
        40, lane_y + lane_h + 46,
        "Human review queue, direction (2026-09-17): every core source unit reviewable in the "
        "dashboard's Build view",
        size=12.5, fill=FAINT, anchor="start", style="italic",
    )
    text(
        40, lane_y + lane_h + 64,
        "with accept, reject, correct and add, plus a blind subset for recall.",
        size=12.5, fill=FAINT, anchor="start", style="italic",
    )

    # Evaluate lane. Specialist grading sits under the human review queue and
    # the versioned dumps so both cross-lane arrows stay clear of the notes.
    zone_label(40, 1690, "EVALUATE - measuring the tool (separate diagram to follow)")
    eval_y = 1714
    eval_h = 150
    eboxes = [
        ("Benchmark and ablations", ["REF-15 AI Act Evaluation Benchmark;", "ladder: plain LLM, RAG, graph,", "graph + build judge,", "graph + runtime judge"], "#9aa4ad", "#141920"),
        ("Judge error rates (H1)", ["50 blind-labelled judge decisions;", "false accept, false reject"], "#a371f7", "#191426"),
        ("Judge calibration (B68)", ["eight candidate models grade the same", "items; EMD with permutation null,", "weighted kappa, inter-specialist", "ceiling; Python cross-check"], "#a371f7", "#191426"),
        ("Specialist grading", ["dashboard campaigns, personal links;", "HLEG alignments: correct / incorrect /", "cannot decide; tailored requirements:", "1 to 5 rubric; Layer 2 blind subset", "for recall"], "#d2649a", "#231018"),
    ]
    en = len(eboxes)
    ebw = (W - 80 - gap * (en - 1)) / en
    x = 40
    grading_left = (0.0, 0.0)
    for i, (title, lines, stroke, fill) in enumerate(eboxes):
        box(x, eval_y, ebw, eval_h, title, lines, stroke, fill, title_size=15.5, line_size=12)
        if title == "Specialist grading":
            grading_left = (x + 40, eval_y)
        x += ebw + gap
    arrow(dumps_bottom[0], dumps_bottom[1], dumps_bottom[0], eval_y,
          "build artefacts + runtime envelopes", lx=1240, ly=eval_y - 62)
    dashed_arrow(grading_left[0], grading_left[1], queue_bottom[0], queue_bottom[1],
                 "decisions, once closing rules are set", lx=1175, ly=eval_y - 62, anchor="end")

    # Phase 2+
    zone_label(40, 1906, "PHASE 2+ (later)")
    _parts.append(
        '<rect x="225" y="1924" width="1425" height="104" rx="16" fill="none" '
        'stroke="#6e7681" stroke-width="2" stroke-dasharray="7,5"/>'
    )
    text(250, 1950, "MULTI-TENANT HOSTED SaaS on Rahti (CSC, EU), same service layer and graph",
         size=15, fill=MUTED, anchor="start", weight="bold")
    cols = [
        ("REST API", "API keys, rate limits"),
        ("Remote MCP", "streamable HTTP, OAuth"),
        ("Multi-tenant", "usage metering, billing"),
        ("Full Web UI", "accounts, dashboards"),
    ]
    cx = 340
    for title, sub in cols:
        text(cx, 1982, title, size=15, fill=INK, weight="bold", anchor="start")
        text(cx, 2004, sub, size=12.5, anchor="start")
        cx += 340
    text(250, 2022, "Only transport, auth, and tenancy change. Core code stays identical.",
         size=12.5, fill=FAINT, anchor="start", style="italic")

    # Footer
    text(W / 2, 2056,
         "Stack: Python + FastAPI + FastMCP + Neo4j (n10s RDF export) + the Next.js dashboard + "
         "Docker Compose; OpenAI generator, Anthropic judges; AGPL-3.0",
         size=13.5, fill=MUTED)
    text(W / 2, 2076,
         "Spec: docs/architecture.md; references: docs/references.md; visual system: "
         "DESIGN.md; agent rules: AGENTS.md. Regenerate: scripts/make_architecture_diagram.py. "
         f"Diagram date {DIAGRAM_DATE}; the 2026-07-19 version is kept beside it.",
         size=12, fill=FAINT, style="italic")

    _parts.append("</svg>")
    return "".join(_parts)


def main() -> None:
    OUT_PATH.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
