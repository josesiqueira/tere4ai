"""M4 ablation strategies: the five conditions of the Section 12 ladder.

@implements: DEC-11
@grounded_by: REF-15, REF-16, REF-17

Each strategy is a uniform callable answer(item) -> {"answer_text",
"citations": [node ids], "risk_category"?} so the harness (harness.py) can
run any subset over the same items. The ladder (architecture.md Section 12):

1. plain_llm        generator only, no graph; the prompt holds the question only.
2. vector_rag       naive lexical retrieval (in-process TF-IDF, no new deps)
                    over Layer 1 node texts; top-k passages as context. This
                    is deliberately the WEAK baseline. Practitioner write-ups
                    report around 38 percent for vector-only RAG, but that
                    source was dropped from the register (non-citable), so we
                    run our own baseline and never quote that figure.
3. graph_no_judge   deterministic classify plus ALL extracted norms as
                    context, judge verdicts ignored (accepted, rejected, and
                    needs_human_review norms are all offered).
4. graph_build_judge  classify plus judge-ACCEPTED norms only.
5. graph_full       graph_build_judge plus the runtime grounding judge
                    gating the generated answer (unverifiable citations are
                    withheld and the verdict is attached).

Model access is injected: every strategy takes constructed clients
(tere4ai.extract_norms.model_clients.ModelClient), so unit tests use
FakeClient and NEVER call a live model. Live construction happens only in
harness.main() behind --live plus TERE4AI_LIVE_TESTS=1.

Item shapes (eval/gold/gold_seed.json and the loaded benchmark items):
- classification: {"id", "kind": "classification", "system_features": {...}}
  (benchmark scenarios carry free text instead; see the note in
  GraphStrategy._classify about unmapped features)
- retrieval / qa: {"id", "kind": "retrieval"|"qa", "question": str}
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Protocol

from tere4ai.extract_norms.model_clients import ModelClient
from tere4ai.mcp_server.classify import classify_ai_system

STRATEGY_NAMES = (
    "plain_llm",
    "vector_rag",
    "graph_no_judge",
    "graph_build_judge",
    "graph_full",
)

# Node types whose text feeds the naive vector_rag index. Recitals are
# included on purpose: a naive baseline does not know recitals are context
# only, and the hallucination/citation metrics should expose that weakness.
_TEXT_NODE_TYPES = ("Paragraph", "Point", "AnnexItem", "Recital")

_GEN_SYSTEM = (
    "You answer questions about the EU AI Act (Regulation 2024/1689). "
    "Respond with a single JSON object with keys: answer_text (string), "
    "citations (list of node id strings), risk_category (one of prohibited, "
    "high_risk, transparency_only, minimal_or_none, uncertain, or null when "
    "the question is not a classification). Cite only node ids you were "
    "given in the context; if you were given none, citations must be []. "
    "Never claim compliance or certification."
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class TfidfIndex:
    """Minimal in-process TF-IDF index with cosine scoring. No dependencies.

    Deliberately naive (bag of words, no stemming, no embeddings): it exists
    to make vector_rag a reproducible weak baseline, not a good retriever.
    """

    def __init__(self, passages: list[tuple[str, str]]):
        self._ids = [pid for pid, _ in passages]
        self._texts = dict(passages)
        docs = [Counter(_tokenize(text)) for _, text in passages]
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(doc.keys())
        n_docs = max(len(docs), 1)
        self._idf = {term: math.log(n_docs / (1 + count)) + 1.0 for term, count in df.items()}
        self._vectors: list[dict[str, float]] = []
        for doc in docs:
            vec = {t: tf * self._idf[t] for t, tf in doc.items()}
            norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
            self._vectors.append({t: w / norm for t, w in vec.items()})

    def query(self, text: str, top_k: int = 5) -> list[tuple[str, float, str]]:
        """Top-k (node_id, score, passage_text), ties broken by node id."""
        counts = Counter(_tokenize(text))
        qvec = {t: tf * self._idf.get(t, 0.0) for t, tf in counts.items()}
        qnorm = math.sqrt(sum(w * w for w in qvec.values())) or 1.0
        scored = []
        for pid, vec in zip(self._ids, self._vectors):
            score = sum(w * vec.get(t, 0.0) for t, w in qvec.items()) / qnorm
            if score > 0.0:
                scored.append((pid, score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [(pid, score, self._texts[pid]) for pid, score in scored[:top_k]]


def passages_from_dump(dump: dict[str, Any]) -> list[tuple[str, str]]:
    """(node_id, text) for every Layer 1 node type carrying text."""
    return [
        (node["id"], node["text"])
        for node in dump.get("nodes", [])
        if node.get("type") in _TEXT_NODE_TYPES and node.get("text")
    ]


def _item_question(item: dict[str, Any]) -> str:
    """The natural-language task text for one item, kind-aware."""
    if item.get("kind") == "classification":
        features = item.get("system_features") or {}
        described = features.get("description") or item.get("system_text") or ""
        flags = features.get("flags") or {}
        parts = [
            "Classify the EU AI Act risk category of this AI system "
            "(prohibited, high_risk, transparency_only, minimal_or_none, or uncertain).",
            f"System description: {described}",
        ]
        if features.get("domain"):
            parts.append(f"Domain: {features['domain']}")
        if flags:
            parts.append("Known facts: " + json.dumps(flags, sort_keys=True))
        return "\n".join(parts)
    return str(item.get("question", ""))


def _parse_result(raw: str) -> dict[str, Any]:
    """Parse a generator response into the uniform result shape, leniently.

    An unparseable response is kept verbatim as answer_text with no
    citations, never discarded and never repaired into invented content.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"answer_text": raw, "citations": [], "risk_category": None,
                "notes": ["generator response was not valid JSON"]}
    if not isinstance(parsed, dict):
        return {"answer_text": raw, "citations": [], "risk_category": None,
                "notes": ["generator response was not a JSON object"]}
    citations = parsed.get("citations")
    if not isinstance(citations, list):
        citations = []
    return {
        "answer_text": str(parsed.get("answer_text", "")),
        "citations": [str(c) for c in citations],
        "risk_category": parsed.get("risk_category"),
        "notes": [],
    }


class Strategy(Protocol):
    """The uniform strategy contract the harness runs."""

    name: str

    def __call__(self, item: dict[str, Any]) -> dict[str, Any]: ...

    @property
    def models(self) -> dict[str, str]: ...


class PlainLLM:
    """Condition 1: generator only, question only, no graph and no context."""

    name = "plain_llm"

    def __init__(self, generator: ModelClient):
        self._generator = generator

    @property
    def models(self) -> dict[str, str]:
        return {"generator": self._generator.model}

    def __call__(self, item: dict[str, Any]) -> dict[str, Any]:
        return _parse_result(self._generator.complete(_GEN_SYSTEM, _item_question(item)))


class VectorRag:
    """Condition 2: naive TF-IDF retrieval over Layer 1 texts, then generate.

    The weak baseline of the ladder (see the module header).
    """

    name = "vector_rag"

    def __init__(self, generator: ModelClient, dump: dict[str, Any], top_k: int = 5):
        self._generator = generator
        self._top_k = top_k
        self._index = TfidfIndex(passages_from_dump(dump))

    @property
    def models(self) -> dict[str, str]:
        return {"generator": self._generator.model}

    def __call__(self, item: dict[str, Any]) -> dict[str, Any]:
        question = _item_question(item)
        hits = self._index.query(question, top_k=self._top_k)
        context = "\n".join(f"[{pid}] {text}" for pid, _score, text in hits)
        user = (
            f"{question}\n\nRetrieved passages (cite by the node id in brackets):\n"
            f"{context or '(no passage retrieved)'}"
        )
        result = _parse_result(self._generator.complete(_GEN_SYSTEM, user))
        result["retrieved_node_ids"] = [pid for pid, _score, _text in hits]
        return result


class GraphStrategy:
    """Conditions 3 to 5: deterministic classify plus norm-graph context.

    judged_only=False ignores the build judge (ALL extracted norms offered,
    accepted, rejected, and needs_human_review alike): condition 3.
    judged_only=True offers judge-accepted norms only: condition 4.
    runtime_judge set: condition 5, the runtime grounding judge gates the
    generated answer and unverifiable citations are withheld.
    """

    def __init__(
        self,
        name: str,
        generator: ModelClient,
        dump: dict[str, Any],
        norms_payload: dict[str, Any],
        judged_only: bool,
        runtime_judge: ModelClient | None = None,
        top_k_norms: int = 8,
        judge_log_path: Any = None,
    ):
        self.name = name
        self._generator = generator
        self._dump = dump
        self._node_ids = {n["id"] for n in dump.get("nodes", []) if "id" in n}
        self._runtime_judge = runtime_judge
        self._judge_log_path = judge_log_path
        self._top_k = top_k_norms
        norms = norms_payload.get("norms") or []
        if judged_only:
            norms = [n for n in norms if n.get("judge_verdict") == "accepted"]
        self._norms_by_id = {n["norm_id"]: n for n in norms}
        self._norms_payload = norms_payload
        # Norms are ranked lexically against the question over their
        # normative content; the same naive index as vector_rag, applied to
        # Layer 2 instead of raw Layer 1 text.
        self._norm_index = TfidfIndex(
            [(n["norm_id"], self._norm_text(n)) for n in norms]
        )
        # Retrieval-kind items ask which Annex item covers a use case, and
        # the gold citations sit at AnnexItem granularity (for example
        # annex-iii:point-5:a), which norm digests cannot reach; index the
        # Layer 1 AnnexItem texts so those items can be offered directly.
        self._annex_index = TfidfIndex(
            [
                (n["id"], n["text"])
                for n in dump.get("nodes", [])
                if n.get("type") == "AnnexItem" and n.get("text")
            ]
        )

    @staticmethod
    def _norm_text(norm: dict[str, Any]) -> str:
        pieces = [
            str(norm.get("actor_explicit") or norm.get("actor_inferred") or ""),
            str(norm.get("action") or ""),
            str(norm.get("object") or ""),
            " ".join(norm.get("conditions") or []),
            " ".join(norm.get("exceptions") or []),
            str(norm.get("source_node_id") or ""),
        ]
        return " ".join(pieces)

    @property
    def models(self) -> dict[str, str]:
        models = {"generator": self._generator.model}
        if self._runtime_judge is not None:
            models["judge"] = self._runtime_judge.model
        return models

    def _select_norms(self, question: str) -> list[dict[str, Any]]:
        hits = self._norm_index.query(question, top_k=self._top_k)
        return [self._norms_by_id[norm_id] for norm_id, _score, _text in hits]

    def _norm_digest(self, norm: dict[str, Any]) -> dict[str, Any]:
        return {
            "norm_id": norm.get("norm_id"),
            "source_node_id": norm.get("source_node_id"),
            "deontic_type": norm.get("deontic_type"),
            "modal": norm.get("modal"),
            "actor": norm.get("actor_explicit") or norm.get("actor_inferred"),
            "action": norm.get("action"),
            "object": norm.get("object"),
            "conditions": norm.get("conditions") or [],
            "exceptions": norm.get("exceptions") or [],
        }

    def _classify(self, item: dict[str, Any]) -> dict[str, Any]:
        features = item.get("system_features")
        if not isinstance(features, dict):
            # Benchmark scenarios are free text; mapping them into structured
            # system_features is annotation work (see eval/README.md), not
            # something the deterministic classifier may guess. Honest
            # degradation instead of a fabricated classification.
            return {
                "answer_text": (
                    "No structured system_features were provided, so the "
                    "deterministic classifier cannot run; the classification "
                    "is uncertain and needs the features to be annotated."
                ),
                "citations": [],
                "risk_category": "uncertain",
                "notes": ["classification item without structured system_features"],
            }
        envelope = classify_ai_system(features, self._dump)
        answer = envelope["answer"]
        summary = {
            "risk_category": answer["risk_category"],
            "rationale": answer["rationale"],
            "cited_nodes": envelope["source_nodes"],
            "status": envelope["status"],
        }
        user = (
            f"{_item_question(item)}\n\n"
            "The deterministic rule ladder already classified this system; "
            "your answer_text explains that result to an engineer. Do not "
            "change the classification and cite only the listed node ids.\n"
            f"Deterministic classification: {json.dumps(summary, sort_keys=True)}"
        )
        generated = _parse_result(self._generator.complete(_GEN_SYSTEM, user))
        # Work item from the first ablation sweep: the classification basis
        # alone under-cites relative to a scenario's full obligation set.
        # Add the source articles of the applicable judged requirements
        # (deterministic, resolved against the dump, never model-invented).
        citations = list(envelope["source_nodes"])
        citations.extend(self._applicable_requirement_articles(envelope))
        seen: set[str] = set()
        citations = [c for c in citations if not (c in seen or seen.add(c))]
        return {
            "answer_text": generated["answer_text"],
            # Citations from the deterministic envelope plus the applicable
            # requirements articles, never from the model.
            "citations": citations,
            "risk_category": answer["risk_category"],
            "notes": generated.get("notes", []),
            "status": envelope["status"],
        }

    def _applicable_requirement_articles(self, envelope: dict[str, Any]) -> list[str]:
        """Article-level node ids of the judged requirements applicable to
        the classified system. Deterministic; empty for categories that
        carry no requirements."""
        if envelope["answer"].get("risk_category") not in (
            "high_risk",
            "transparency_only",
        ):
            return []
        from tere4ai.mcp_server.requirements import get_applicable_requirements

        req = get_applicable_requirements(envelope, self._norms_payload, self._dump)
        groups = req["answer"].get("requirements_by_article") or {}
        entries = [e for group in groups.values() for e in group]
        articles: set[str] = set()
        for entry in entries:
            source = str(entry.get("source_node_id", ""))
            m = re.match(r"(eu-ai-act:(?:article|annex)-[a-z0-9]+)", source)
            if m and m.group(1) in self._node_ids:
                articles.add(m.group(1))
        return sorted(articles)

    def _answer_from_norms(self, item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        question = _item_question(item)
        selected = self._select_norms(question)
        digests = [self._norm_digest(n) for n in selected]
        context_blocks = [
            "Context: normative statements extracted from the Act, each with "
            "its source node id. Answer from these only and cite the "
            "source_node_id values that support your answer.\n"
            + json.dumps(digests, sort_keys=True)
        ]
        annex_ids: list[str] = []
        if item.get("kind") == "retrieval":
            # AnnexItem-level retrieval: these items ask which Annex item
            # covers a use case, and the gold citations sit at AnnexItem
            # granularity; offer the matching Layer 1 annex-item texts too.
            annex_hits = self._annex_index.query(question, top_k=5)
            annex_ids = [node_id for node_id, _score, _text in annex_hits]
            if annex_hits:
                context_blocks.append(
                    "Annex items from the Act, each with its node id; cite "
                    "the annex item id when one answers the question.\n"
                    + json.dumps(
                        [{"id": nid, "text": text} for nid, _s, text in annex_hits],
                        sort_keys=True,
                    )
                )
        user = f"{question}\n\n" + "\n\n".join(context_blocks)
        result = _parse_result(self._generator.complete(_GEN_SYSTEM, user))
        result["offered_norm_ids"] = [d["norm_id"] for d in digests]
        if annex_ids:
            result["offered_annex_item_ids"] = annex_ids
        return result, digests

    def __call__(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("kind") == "classification":
            result = self._classify(item)
            digests: list[dict[str, Any]] = []
        else:
            result, digests = self._answer_from_norms(item)

        if self._runtime_judge is None:
            return result

        # Condition 5 only: the runtime grounding gate. Citations that do
        # not resolve in the graph dump are withheld (mirroring the
        # _Citations discipline of the deterministic tools), and the
        # grounding judge verdict is attached; any verdict other than
        # accepted degrades the answer to requires_human_review.
        from tere4ai.judge.runtime_grounding import ground_check

        verified = [c for c in result["citations"] if c in self._node_ids]
        withheld = [c for c in result["citations"] if c not in self._node_ids]
        result["citations"] = verified
        if withheld:
            result.setdefault("notes", []).append(
                f"citations withheld (not in graph dump): {', '.join(withheld)}"
            )
        judged = ground_check(
            answer_text=result["answer_text"],
            cited_norms=digests,
            evidence_text=None,
            judge=self._runtime_judge,
            log_path=self._judge_log_path,
            context="eval_harness",
        )
        result["judge_verdict"] = judged["verdict"]
        if judged["verdict"] != "accepted":
            result["status"] = "requires_human_review"
            result.setdefault("notes", []).append(
                "runtime grounding judge did not accept the answer: "
                + judged["rationale"]
            )
        return result


def build_strategy(
    name: str,
    generator: ModelClient,
    dump: dict[str, Any],
    norms_payload: dict[str, Any],
    judge: ModelClient | None = None,
    judge_log_path: Any = None,
) -> PlainLLM | VectorRag | GraphStrategy:
    """Construct one named ablation condition from injected clients."""
    if name == "plain_llm":
        return PlainLLM(generator)
    if name == "vector_rag":
        return VectorRag(generator, dump)
    if name == "graph_no_judge":
        return GraphStrategy(name, generator, dump, norms_payload, judged_only=False)
    if name == "graph_build_judge":
        return GraphStrategy(name, generator, dump, norms_payload, judged_only=True)
    if name == "graph_full":
        if judge is None:
            raise ValueError("graph_full needs a judge client (runtime grounding judge)")
        return GraphStrategy(
            name, generator, dump, norms_payload, judged_only=True,
            runtime_judge=judge, judge_log_path=judge_log_path,
        )
    raise ValueError(f"unknown strategy {name!r}; known: {', '.join(STRATEGY_NAMES)}")
