"""Draft gold-set candidates from the graph for human confirmation (#26).

@grounded_by: REF-15

Implements the drafting half of eval/gold/ANNOTATION_PROTOCOL.md toward the
60-80 item gold set (architecture.md Section 12): candidate items are
DRAFTS, never gold. Every draft is mechanically verified against the
published dump (citations resolve; classification drafts agree with the
deterministic ladder, which the protocol requires of seed items too), and
the human annotator confirms or rewrites each one per the protocol. The
second-annotator subset is a deterministic, stratified draw over item id
hashes with the seed recorded in the output.

Usage:
  .venv/bin/python scripts/draft_gold_candidates.py draft
      [--out eval/gold/draft_candidates.json] [--subset-seed tere4ai-gold-v1]
  .venv/bin/python scripts/draft_gold_candidates.py agreement A.json B.json
      (each file maps item_id -> label; kappa and raw agreement per file pair)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.agreement import cohen_kappa, raw_agreement  # noqa: E402
from tere4ai.mcp_server.classify import classify_ai_system  # noqa: E402

DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
DEFAULT_OUT = ROOT / "eval" / "gold" / "draft_candidates.json"

# Classification variant templates over the ladder's own rule tables; the
# description is a draft for the annotator to rewrite in scenario language.
CLASSIFICATION_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "slug": "prohibited-social-scoring",
        "flags": {"social_scoring": True},
        "description": "DRAFT: a public authority scores citizens' social behaviour over time and access to services depends on the score.",
    },
    {
        "slug": "prohibited-subliminal",
        "flags": {"subliminal_or_manipulative": True},
        "description": "DRAFT: an advertising system uses subliminal cues to steer purchase decisions users would not otherwise make.",
    },
    {
        "slug": "prohibited-rbi-law-enforcement",
        "flags": {"real_time_remote_biometric_public": True, "law_enforcement_use": True},
        "description": "DRAFT: police scan live public CCTV with face recognition to locate persons in real time.",
    },
    {
        "slug": "high-risk-employment",
        "flags": {"employment_decisions": True},
        "description": "DRAFT: a tool ranks and filters job applications and its output decides who is invited to interview.",
    },
    {
        "slug": "high-risk-education",
        "flags": {"education_scoring_or_access": True},
        "description": "DRAFT: a system grades admission exams that determine access to a university programme.",
    },
    {
        "slug": "high-risk-essential-services",
        "flags": {"essential_services_access": True},
        "description": "DRAFT: a scoring model decides eligibility for social benefit payments.",
    },
    {
        "slug": "high-risk-critical-infrastructure",
        "flags": {"critical_infrastructure_safety": True},
        "description": "DRAFT: a controller manages safety functions of the electricity grid.",
    },
    {
        "slug": "high-risk-migration",
        "flags": {"migration_asylum_border_use": True},
        "description": "DRAFT: a border authority uses a tool to assess asylum application risk.",
    },
    {
        "slug": "high-risk-6-3-candidate",
        "flags": {"education_scoring_or_access": True, "preparatory_or_narrow_procedural_task": True, "profiling_of_natural_persons": False},
        "autonomy": "advisory",
        "description": "DRAFT: an advisory tool pre-sorts student admission paperwork before human assessment.",
    },
    {
        "slug": "high-risk-6-3-profiling-override",
        "flags": {"education_scoring_or_access": True, "preparatory_or_narrow_procedural_task": True, "profiling_of_natural_persons": True},
        "autonomy": "advisory",
        "description": "DRAFT: an advisory admission pre-sorter that profiles applicants.",
    },
    {
        "slug": "high-risk-annex-i-route",
        "flags": {"annex_i_covered_product": True, "third_party_conformity_assessment_required": True},
        "description": "DRAFT: a vision safety component in machinery subject to third-party conformity assessment.",
    },
    {
        "slug": "transparency-chatbot",
        "flags": {"interacts_with_natural_persons": True},
        "description": "DRAFT: a customer-service chatbot that answers billing questions.",
    },
    {
        "slug": "transparency-synthetic-content",
        "flags": {"generates_synthetic_content": True},
        "description": "DRAFT: a tool that generates photorealistic marketing images.",
    },
    {
        "slug": "minimal-spam-filter",
        "flags": {},
        "description": "DRAFT: a spam filter for an internal mailbox.",
    },
    {
        "slug": "uncertain-unknown-flags",
        "flags": None,
        "description": "DRAFT: a vendor tool described only as AI-powered analytics, no facts established.",
    },
)

ALL_SCHEMA_FLAGS = (
    "biometric_identification", "biometric_categorisation",
    "real_time_remote_biometric_public", "emotion_recognition",
    "emotion_recognition_workplace_or_education", "social_scoring",
    "subliminal_or_manipulative", "exploits_vulnerabilities",
    "predictive_policing_profiling", "facial_image_scraping",
    "law_enforcement_use", "migration_asylum_border_use",
    "justice_democratic_use", "education_scoring_or_access",
    "employment_decisions", "essential_services_access",
    "critical_infrastructure_safety", "medical_or_safety_component",
    "interacts_with_natural_persons", "generates_synthetic_content",
    "profiling_of_natural_persons", "preparatory_or_narrow_procedural_task",
    "improves_previous_human_activity",
    "detects_patterns_without_replacing_human_assessment",
    "annex_i_covered_product", "third_party_conformity_assessment_required",
)


def _all_false(overrides: dict[str, Any]) -> dict[str, Any]:
    flags = dict.fromkeys(ALL_SCHEMA_FLAGS, False)
    flags.update(overrides)
    return flags


def draft_classification(dump: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for variant in CLASSIFICATION_VARIANTS:
        features: dict[str, Any] = {"description": variant["description"]}
        if variant.get("autonomy"):
            features["autonomy"] = variant["autonomy"]
        if variant["flags"] is None:
            features["flags"] = {}
        else:
            features["flags"] = _all_false(variant["flags"])
        envelope = classify_ai_system(features, dump)
        answer = envelope["answer"]
        items.append(
            {
                "id": f"draft:cls-{variant['slug']}",
                "kind": "classification",
                "system_features": features,
                "gold": {
                    "risk_category": answer["risk_category"],
                    "article_6_3_exception_candidate": answer[
                        "article_6_3_exception_candidate"
                    ],
                },
                "gold_citations": envelope["source_nodes"],
                "status": "draft",
                "note": (
                    "gold drafted FROM the deterministic ladder (mechanical "
                    "agreement holds by construction); annotator must confirm "
                    "the label against the source text, not against the tool"
                ),
                "source": "drafted from ladder rule tables",
            }
        )
    return items


def draft_retrieval(dump: dict[str, Any], limit: int = 28) -> list[dict[str, Any]]:
    """One draft per Annex III leaf AnnexItem, most precise node id as gold."""
    nodes = [n for n in dump["nodes"] if n.get("type") == "AnnexItem" and n.get("text")]
    annex_iii = sorted(
        (n for n in nodes if n["id"].startswith("eu-ai-act:annex-iii:")),
        key=lambda n: n["id"],
    )
    ids = {n["id"] for n in annex_iii}
    leaves = [n for n in annex_iii if not any(
        other != n["id"] and other.startswith(n["id"] + ":") for other in ids
    )]
    items = []
    for node in leaves[:limit]:
        text = " ".join(node["text"].split())
        items.append(
            {
                "id": f"draft:ret-{node['id'].removeprefix('eu-ai-act:annex-iii:')}",
                "kind": "retrieval",
                "question": (
                    "DRAFT (rewrite as a situation, not the provision text): "
                    f"Which Annex III item covers: {text[:220]}"
                ),
                "gold": {"node_id": node["id"]},
                "gold_citations": [node["id"]],
                "status": "draft",
                "note": "question must be rewritten so it does not quote the provision verbatim",
                "source": "drafted from Annex III leaf items",
            }
        )
    return items


def draft_qa(dump: dict[str, Any], norms_payload: dict[str, Any], limit: int = 30) -> list[dict[str, Any]]:
    """One accepted norm per (article, paragraph), highest confidence first."""
    node_ids = {n["id"] for n in dump["nodes"]}
    accepted = [
        n for n in norms_payload.get("norms", [])
        if n.get("judge_verdict") == "accepted"
        and n.get("source_node_id") in node_ids
        # QA questions are phrased per article and actor; annex-sourced norms
        # and unresolved actors make unusable question drafts.
        and str(n.get("source_node_id", "")).startswith("eu-ai-act:article-")
        and (n.get("actor_explicit") or n.get("actor_inferred") or "").strip()
        not in ("", "unspecified_needs_review")
    ]
    by_paragraph: dict[str, dict[str, Any]] = {}
    for norm in sorted(accepted, key=lambda n: (-(n.get("confidence") or 0), n["norm_id"])):
        source = norm["source_node_id"]
        paragraph_key = ":".join(source.split(":")[:3])
        by_paragraph.setdefault(paragraph_key, norm)
    items = []
    for paragraph_key in sorted(by_paragraph)[:limit]:
        norm = by_paragraph[paragraph_key]
        source = norm["source_node_id"]
        parts = source.split(":")
        article_id = ":".join(parts[:2])
        article_no = parts[1].removeprefix("article-")
        paragraph_no = parts[2].removeprefix("paragraph-") if len(parts) > 2 else ""
        actor = norm.get("actor_explicit") or norm.get("actor_inferred") or "the provider"
        items.append(
            {
                "id": f"draft:qa-{source.removeprefix('eu-ai-act:')}",
                "kind": "qa",
                "question": (
                    f"DRAFT: Under Article {article_no}({paragraph_no}) of the EU "
                    f"AI Act, what must {actor} do regarding "
                    f"{norm.get('object') or 'this obligation'}?"
                ),
                "gold": {
                    "answer_text": (
                        f"DRAFT (rewrite from the source text): {actor} must "
                        f"{norm.get('action')} {norm.get('object')}"
                    )
                },
                "gold_citations": [article_id],
                "status": "draft",
                "note": f"drafted from {norm['norm_id']} (span {norm.get('source_span_id')}); answer must be rewritten from the article text",
                "source": "drafted from judge-accepted norms",
            }
        )
    return items


def assign_second_annotator(items: list[dict[str, Any]], seed: str, share: float = 0.25) -> None:
    """Deterministic stratified draw: lowest sha256(seed + id) per kind."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_kind.setdefault(item["kind"], []).append(item)
    for kind_items in by_kind.values():
        ranked = sorted(
            kind_items,
            key=lambda i: hashlib.sha256(f"{seed}:{i['id']}".encode()).hexdigest(),
        )
        take = max(1, round(len(ranked) * share))
        chosen = {i["id"] for i in ranked[:take]}
        for item in kind_items:
            item["second_annotator"] = item["id"] in chosen


def cmd_draft(args: argparse.Namespace) -> int:
    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    norms_payload = json.loads(NORMS_PATH.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in dump["nodes"]}

    items = (
        draft_classification(dump)
        + draft_retrieval(dump)
        + draft_qa(dump, norms_payload)
    )
    unresolved = [
        (item["id"], cited)
        for item in items
        for cited in item["gold_citations"]
        if cited not in node_ids
    ]
    if unresolved:
        for item_id, cited in unresolved:
            print(f"refusing: {item_id} cites {cited}, not in the dump", file=sys.stderr)
        return 1
    assign_second_annotator(items, args.subset_seed)

    counts = {k: sum(1 for i in items if i["kind"] == k) for k in ("classification", "retrieval", "qa")}
    payload = {
        "provenance": {
            "generated_by": "scripts/draft_gold_candidates.py",
            "build_id": dump["build"]["build_id"],
            "protocol": "eval/gold/ANNOTATION_PROTOCOL.md",
            "second_annotator_seed": args.subset_seed,
            "counts": counts,
            "status": "DRAFTS ONLY: no item is gold until a human confirms it per the protocol",
        },
        "items": items,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    second = sum(1 for i in items if i["second_annotator"])
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(
        f"wrote {shown}: {len(items)} drafts "
        f"({counts}), {second} assigned to the second annotator"
    )
    return 0


def cmd_agreement(args: argparse.Namespace) -> int:
    labels_a = json.loads(Path(args.file_a).read_text(encoding="utf-8"))
    labels_b = json.loads(Path(args.file_b).read_text(encoding="utf-8"))
    shared = sorted(set(labels_a) & set(labels_b))
    if not shared:
        print("no shared item ids between the two label files", file=sys.stderr)
        return 1
    a = [labels_a[i] for i in shared]
    b = [labels_b[i] for i in shared]
    print(f"items compared: {len(shared)}")
    print(f"raw agreement: {raw_agreement(a, b):.3f}")
    print(f"cohen kappa:   {cohen_kappa(a, b):.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft", help="draft candidate items from the graph")
    draft.add_argument("--out", default=str(DEFAULT_OUT))
    draft.add_argument("--subset-seed", default="tere4ai-gold-v1")
    agree = sub.add_parser("agreement", help="kappa between two label files")
    agree.add_argument("file_a")
    agree.add_argument("file_b")
    args = parser.parse_args(argv)
    return cmd_draft(args) if args.command == "draft" else cmd_agreement(args)


if __name__ == "__main__":
    sys.exit(main())
