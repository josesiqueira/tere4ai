"""Generate the TERE4AI v2 judge-pipeline diagram (SVG) deterministically.

Companion to make_architecture_diagram.py: one figure answering "how does
LLM-as-judge actually happen here". Content verified against the code by
the 2026-07-19 judge audit: three separate judges (extraction, mapping,
runtime grounding), each preceded and followed by mechanical, non-LLM
checks; categorical verdicts with a safe fallback (unusable judge output
can never accept); no numeric thresholds anywhere (the verdict decides,
the five scores are recorded evidence); every decision logged.

  .venv/bin/python scripts/make_judge_diagram.py
  inkscape judge_diagram.svg --export-filename=judge_diagram.png \
      --export-width=3360
"""

from __future__ import annotations

from pathlib import Path

W, H = 1680, 1620
FONT = "DejaVu Sans, sans-serif"
BG = "#0b0e14"
INK = "#e6edf3"
MUTED = "#9aa4ad"
FAINT = "#6e7681"
ARROW = "#8b98a5"
GEN = "#e3b341"      # generator (OpenAI)
JUDGE = "#a371f7"    # judges (Anthropic)
MECH = "#9aa4ad"     # mechanical, non-LLM checks
HUMAN = "#d2649a"    # human review
OK = "#3fb950"       # accepted
BAD = "#f85149"      # rejected / degraded

OUT_PATH = Path(__file__).resolve().parents[1] / "judge_diagram.svg"

_parts: list[str] = []


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=12.5, fill=MUTED, anchor="middle", weight=None, style=None, spacing=None):
    attrs = (
        f'x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'fill="{fill}" text-anchor="{anchor}"'
    )
    if weight:
        attrs += f' font-weight="{weight}"'
    if style:
        attrs += f' font-style="{style}"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    _parts.append(f"<text {attrs}>{esc(s)}</text>")


def box(x, y, w, h, title, lines, stroke, fill, dashed=False, title_size=14.5, line_size=11):
    dash = ' stroke-dasharray="7,5"' if dashed else ""
    _parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2.2"{dash}/>'
    )
    cx = x + w / 2
    text(cx, y + 24, title, size=title_size, fill=stroke, weight="bold")
    ly = y + 44
    for line in lines:
        text(cx, ly, line, size=line_size)
        ly += line_size + 5


def arrow(x1, y1, x2, y2, label="", color=ARROW, lx=None, ly=None, lanchor="start"):
    _parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="1.6" marker-end="url(#ah)"/>'
    )
    if label:
        text(
            lx if lx is not None else (x1 + x2) / 2 + 6,
            ly if ly is not None else (y1 + y2) / 2 - 6,
            label, size=11, fill=FAINT, anchor=lanchor, style="italic",
        )


def lane_label(y, s):
    text(40, y, s, size=15, fill=FAINT, anchor="start", weight="bold", spacing="1.5")


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
    text(W / 2, 48, "TERE4AI v2  LLM-as-judge, exactly as implemented", size=34, fill=INK, weight="bold")
    text(W / 2, 80,
         "Three separate judges (Anthropic Claude) gate the OpenAI generator. Mechanical, non-LLM checks run "
         "before and after every judge. No numeric thresholds:",
         size=15)
    text(W / 2, 100,
         "the categorical verdict decides; the five scores are recorded evidence. "
         "An unusable judge response can never accept anything.",
         size=15)

    # Lane 1: extraction judge
    lane_label(150, "BUILD TIME 1 - NORM EXTRACTION  (extract_norms/pipeline.py)")
    y = 170
    box(40, y, 240, 120, "Source unit",
        ["one article / paragraph /", "point with verbatim text", "+ span id; recitals refused", "as sources (raises)"],
        FAINT, "#11151c")
    box(330, y, 250, 120, "Generator (OpenAI)",
        ["proposes candidate norms", "as JSON, temperature 0,", "one retry on parse failure"],
        GEN, "#1d1704")
    box(630, y, 250, 120, "Mechanical pre-checks",
        ["field allow-list (11 schema", "fields); candidates without", "a source span skipped", "before any judging"],
        MECH, "#141920")
    box(930, y, 270, 120, "Extraction judge",
        ["prompts/judge_norms/v1.md", "6 checks: span exists, deontic", "supported, actor valid, grounded,", "conditions kept, binding source"],
        JUDGE, "#191426")
    arrow(280, y + 60, 330, y + 60)
    arrow(580, y + 60, 630, y + 60)
    arrow(880, y + 60, 930, y + 60)
    arrow(1200, y + 30, 1280, y - 4, "accepted", color=OK, lx=1216, ly=y + 4)
    arrow(1200, y + 60, 1280, y + 84, "rejected", color=BAD, lx=1216, ly=y + 62)
    arrow(1200, y + 90, 1280, y + 172, "needs review / unusable output", color=HUMAN, lx=1108, ly=y + 136)
    box(1280, y - 46, 360, 96, "Published norm",
        ["provenance LLM_JUDGED_ACCEPTED;", "schema-validated or dropped with the", "JudgeRun kept"],
        OK, "#0c1a10", title_size=13)
    box(1280, y + 58, 360, 84, "Excluded from the graph",
        ["JudgeRun kept for audit;", "never served, never aligned"],
        BAD, "#1a0c0c", title_size=13)
    box(1280, y + 166, 360, 96, "Human review queue",
        ["adjudicated via scripts/review_cli.py;", "decisions republished with", "HUMAN_REVIEWED_* provenance"],
        HUMAN, "#231018", title_size=13)

    # Lane 2: mapping judge
    lane_label(452, "BUILD TIME 2 - HLEG ETHICS ALIGNMENT  (align_hleg_altai/pipeline.py)")
    y = 472
    box(40, y, 240, 124, "Accepted norm",
        ["only judge-accepted norms", "are ever aligned", "+ one of the 7 closed", "HLEG requirements"],
        FAINT, "#11151c")
    box(330, y, 250, 124, "Generator (OpenAI)",
        ["proposes up to 3 candidate", "alignments, each with a", "source quote AND a target", "quote (evidence both sides)"],
        GEN, "#1d1704")
    box(630, y, 250, 124, "Mechanical quote gate",
        ["each quote must be a verbatim", "substring of its side's text;", "failures NEVER reach the judge", "(logged as mechanical:quote_check)"],
        MECH, "#141920")
    box(930, y, 270, 124, "Mapping judge",
        ["prompts/judge_alignment/v1.md", "4 checks; may CORRECT the", "relation type (closed set);", "no forced mapping"],
        JUDGE, "#191426")
    arrow(280, y + 62, 330, y + 62)
    arrow(580, y + 62, 630, y + 62)
    arrow(880, y + 62, 930, y + 62)
    arrow(1200, y + 40, 1280, y + 20, "accepted", color=OK, lx=1216, ly=y + 16)
    arrow(1200, y + 84, 1280, y + 128, "rejected / review", color=HUMAN, lx=1272, ly=y + 122, lanchor="end")
    box(1280, y - 12, 360, 112, "Reified AlignmentAssertion",
        ["never a bare truth edge; gate G4 fails", "any accepted assertion missing evidence", "spans on both sides; served with the", "not-expert-validated caveat"],
        OK, "#0c1a10", title_size=13)
    box(1280, y + 112, 360, 72, "Held, never served as accepted",
        ["145 pending assertions live in the", "review queue today"],
        HUMAN, "#231018", title_size=13)

    # Lane 3: runtime judge
    lane_label(722, "RUNTIME - EVIDENCE EVALUATION AND BACKLOG, PAID PATHS  (mcp_server/evidence.py, backlog.py)")
    y = 742
    box(40, y, 240, 140, "Project artifact",
        ["UNTRUSTED text, fenced as", "data-never-instructions;", "refusal gate: a non-accepted", "norm is refused BEFORE any", "model call"],
        FAINT, "#11151c")
    box(330, y, 250, 140, "Generator (OpenAI)",
        ["assessment with quotes,", "gaps, rationale; backlog", "items citing norm ids"],
        GEN, "#1d1704")
    box(630, y, 250, 140, "Mechanical checks",
        ["quotes: verbatim substring or", "dropped; zero surviving quotes", "downgrades to cannot_assess;", "backlog citation allow-list:", "unknown norm ids dropped"],
        MECH, "#141920")
    box(930, y, 270, 140, "Runtime grounding judge",
        ["prompts/runtime_grounding/v1.md", "7 checks: citations support claim,", "closed citation set, sources kept", "apart, uncertainty marked, no", "compliance claim, injection detected"],
        JUDGE, "#191426")
    arrow(280, y + 70, 330, y + 70)
    arrow(580, y + 70, 630, y + 70)
    arrow(880, y + 70, 930, y + 70)
    arrow(1200, y + 46, 1280, y + 26, "accepted", color=OK, lx=1216, ly=y + 22)
    arrow(1200, y + 94, 1280, y + 136, "any other verdict", color=BAD, lx=1272, ly=y + 128, lanchor="end")
    box(1280, y - 8, 360, 108, "Answer surfaces",
        ["envelope judge_verdict: accepted;", "confidence = the judge's own", "evidence_strength score (see caveat", "in docs: uncalibrated until task 25)"],
        OK, "#0c1a10", title_size=13)
    box(1280, y + 120, 360, 96, "Degraded, never silent",
        ["status forced to requires_human_review,", "confidence 0.0, judge rationale attached;", "pipeline stops earlier: verdict not_run"],
        BAD, "#1a0c0c", title_size=13)

    # Values strip
    lane_label(996, "WHERE EVERY JUDGE VALUE LIVES  (nothing is hidden; build values are static per build, runtime values are per call)")
    y = 1016
    box(40, y, 520, 150, "JudgeRun records (static per build)",
        ["inside norms_core.json and alignments_core.json:", "verdict, rationale, all 5 scores, judge model,", "prompt version AND prompt sha256, timestamps;", "442 extraction + 636 alignment runs this build;", "regenerated only by a new judged build or", "a human adjudication"],
        JUDGE, "#191426", title_size=13.5)
    box(600, y, 520, 150, "Append-only audit logs (JSONL)",
        ["data/review_queue/extraction_log.jsonl,", "alignment_log.jsonl, runtime_log.jsonl: one", "event per call with model, prompt version +", "sha256, verdict, rationale, input sha256 (text", "never logged; secrets scrubbed); merge with", "scripts/consolidated_audit.py"],
        MECH, "#141920", title_size=13.5)
    box(1160, y, 480, 150, "The envelope (per call, dynamic)",
        ["every runtime answer carries judge_verdict,", "judge_rationale (in answer), confidence,", "and judge_run_id; two identical paid calls", "may differ (model nondeterminism), which is", "why the verdict gates and the scores only", "describe"],
        GEN, "#1d1704", title_size=13.5)

    # Score legend
    text(40, 1218, "The five recorded scores (defined in the judge prompts, clamped to [0,1], never thresholded):",
         size=13, fill=MUTED, anchor="start", weight="bold")
    text(40, 1240,
         "semantic_similarity, normative_relevance, operational_utility, evidence_strength "
         "(surfaced as envelope confidence), judge_confidence.",
         size=12.5, fill=MUTED, anchor="start")
    text(40, 1262,
         "The categorical verdict (accepted / rejected / needs_human_review) is the only thing that gates; "
         "fallback on unusable output is needs_human_review with all scores zeroed.",
         size=12.5, fill=MUTED, anchor="start")

    # Inspect commands
    lane_label(1316, "INSPECT THE VALUES YOURSELF")
    cmds = [
        "jq '.judge_runs[0]' data/graph_dumps/norms_core.json                         # one full extraction JudgeRun with scores",
        "jq '.norms[] | select(.review_status==\"accepted\") | .judge_verdict' data/graph_dumps/norms_core.json | sort | uniq -c",
        "tail -3 data/review_queue/runtime_log.jsonl                                  # latest runtime judge events",
        ".venv/bin/python scripts/consolidated_audit.py                               # merged, scrubbed audit trail",
        "curl -s -X POST localhost:8008/api/explain -H 'content-type: application/json' -d '{\"norm_id\":\"norm:eu-ai-act:article-9:paragraph-1:n1\"}'",
    ]
    yy = 1340
    for c in cmds:
        text(48, yy, c, size=12, fill="#8ab4f8", anchor="start")
        yy += 22

    text(W / 2, 1478,
         "Change detection: every event and JudgeRun also logs the prompt's sha256, so editing a prompt file is "
         "detectable even at the same version label, and tied to the decisions it made.",
         size=13, fill=MUTED)
    text(W / 2, 1500,
         "Independence: the generator is OpenAI, all judges are Anthropic Claude (DEC-07); the config loader "
         "rejects an OpenAI-family judge (or one equal to the generator) and both run at temperature 0.",
         size=13, fill=MUTED)
    text(W / 2, 1522,
         "Honest limits, stated: judge FA/FR rates are instrumented but unmeasured until the 50-decision human "
         "labeling (task 25); scores are recorded, not calibrated.",
         size=13, fill=MUTED)
    text(W / 2, 1556,
         "Sources: extract_norms/pipeline.py, align_hleg_altai/pipeline.py, judge/runtime_grounding.py, "
         "judge/audit_log.py, prompts/. Regenerate: scripts/make_judge_diagram.py",
         size=12, fill=FAINT, style="italic")

    _parts.append("</svg>")
    return "".join(_parts)


def main() -> None:
    OUT_PATH.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
