# Tool reference

Every tool the MCP server serves, in the order its tool list gives
them: free or paid, its annotations, its whole description as a client
receives it, and its input fields. This page is generated from the
running server by scripts/gen_server_docs.py; the descriptions are
written in src/tere4ai/mcp_server/server.py.

## `classify_ai_system`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Deterministic EU AI Act risk classification of a described AI system.

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
names that fact. Free, no model calls.
```

| Input | Type | Required |
|---|---|---|
| [`features`](https://github.com/josesiqueira/tere4ai/blob/main/schema/json_schemas/system_features.schema.json) | object | yes |

## `coverage_report`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Structural coverage of the Act's graph and its judged layers, against
the frozen source. The Layer 0+1 graph is checked against what the Act
in force holds (119 articles, 180 recitals, 14 annexes, chapters I to
XIII, the high-risk core present), with per-chapter article listing and
layer 2/3 status. Deterministic and free.
```

No input.

## `elicit_features`

Paid. Annotations: destructiveHint false, openWorldHint true, readOnlyHint true.

```text
Propose the system_features facts of a plain-text system description,
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
and missing_facts names it.
```

| Input | Type | Required |
|---|---|---|
| `description` | string | yes |

## `evaluate_project_evidence`

Paid. Annotations: destructiveHint false, openWorldHint true, readOnlyHint true.

```text
Evaluate ONE untrusted project evidence artifact against ONE
judge-accepted norm from the graph.

PAID: this tool performs paid model calls (one OpenAI generator call
plus one Anthropic runtime grounding judge call) on every invocation.

norm_id must be a judge-accepted NormativeStatement id from
get_applicable_requirements. Returns the assessment (satisfied,
partially_satisfied, missing, contradicted, cannot_assess), the
surviving verbatim quotes, the gaps, and the judge verdict and
rationale; a non-accepting judge verdict degrades the status to
requires_human_review, never silently.
```

| Input | Type | Required |
|---|---|---|
| `artifact_id` | string or null | no |
| `artifact_type` | string | yes |
| `content` | string | yes |
| `norm_id` | string | yes |

## `evaluate_project_evidence_batch`

Paid. Annotations: destructiveHint false, openWorldHint true, readOnlyHint true.

```text
Evaluate ONE untrusted evidence artifact against EVERY judge-accepted
norm of one article, in a single envelope with per-norm results.

PAID: this tool performs paid model calls PER NORM (one generator call
plus one runtime grounding judge call for each judge-accepted norm of
the article), so an article with N accepted norms costs N times the
single-norm tool.

article_node_id is a Layer 1 article id such as eu-ai-act:article-9.
The envelope status is the most conservative per-norm status and the
judge_verdict is accepted only when every per-norm verdict is.
```

| Input | Type | Required |
|---|---|---|
| `article_node_id` | string | yes |
| `artifact_id` | string or null | no |
| `artifact_type` | string | yes |
| `content` | string | yes |

## `explain_requirement`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Explain one judged requirement (a normative statement) in depth. The
answer holds its deontic decomposition (actor, modal, action, object,
conditions, exceptions), full source unit text, Article 3 definitions
occurring in its action/object, accepted HLEG alignment targets with
relation types and final scores, and a span trace. Non-accepted norms
are explained too, with their review status stated prominently. The
source text is the Act in force (Regulation (EU) 2024/1689 as amended by
Regulation (EU) 2026/1744); earlier_version=true adds the unit's 2024
wording where the amendment changed it, or says why it has none.
Deterministic and free.
```

| Input | Type | Required |
|---|---|---|
| `earlier_version` | boolean | no |
| `norm_id` | string | yes |

## `generate_control_backlog`

Paid. Annotations: destructiveHint false, openWorldHint true, readOnlyHint true.

```text
Generate a judged engineering control backlog from judge-accepted
norms.

PAID: this tool performs paid model calls (one OpenAI generator call
plus one Anthropic runtime grounding judge call) on every invocation.

norm_ids are NormativeStatement ids from get_applicable_requirements
(capped at 10; any truncation is noted in the answer, never silent).
Every backlog item cites only input norm ids; items citing anything else
are dropped and counted. The judge verdict gates the whole backlog.
```

| Input | Type | Required |
|---|---|---|
| `norm_ids` | array of string | yes |
| `system_context` | string | yes |

## `get_applicable_requirements`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Judge-accepted engineering requirements applicable to a classified
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
calls.
```

| Input | Type | Required |
|---|---|---|
| `actor` | string or null | no |
| `addressee` | string or null | no |
| `classification` | object | yes |

## `resolve_span`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
The exact source text behind a span id, checked against the
snapshot's checksum: snapshot file, sha256, start, end, and the text.
Start and end
count Unicode code points in the snapshot decoded as UTF-8, not bytes;
sha256 is over the file's bytes. Unknown span ids and checksum drift
come back as clean degraded envelopes, never an exception.
Deterministic and free.
```

| Input | Type | Required |
|---|---|---|
| `span_id` | string | yes |

## `source_trace`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Trace a graph node to its frozen source snapshot: file, sha256, span
start/end, HTML anchor, and a text excerpt. Start and end count Unicode
code points in the snapshot decoded as UTF-8, not bytes; sha256 is over
the file's bytes. The excerpt is capped at 500
characters for payload size; when it is shorter than the full provision,
answer.excerpt_truncated is true and answer.excerpt_chars /
answer.span_chars report exactly how much of the text was returned, so a
partial quote is never mistaken for a complete one. Get the full
verbatim text via resolve_span on the same span_id (or GET
/api/span/{span_id} on the HTTP facade). Deterministic and free.
```

| Input | Type | Required |
|---|---|---|
| `node_id` | string | yes |

## `trace_alignment`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Every EU-to-HLEG alignment for a norm or an HLEG requirement, with
its judge verdict and evidence. Given a norm_id, the assertions from
that norm; given an HLEG requirement id, the assertions targeting it.
Every assertion is rendered with relation type, scores, judge verdict
and rationale, alignment and judge runs (models, prompt versions), and
evidence span ids on both sides; never a bare edge. The alignments are
LLM-generated and not expert-validated. Deterministic and free.
```

| Input | Type | Required |
|---|---|---|
| `id` | string | yes |

## `trace_implementation`

Free. Annotations: destructiveHint false, openWorldHint false, readOnlyHint true.

```text
Requirement-to-code traceability matrix for a classified system.

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
Deterministic and free.
```

| Input | Type | Required |
|---|---|---|
| `actor` | string or null | no |
| `addressee` | string or null | no |
| `classification` | object | yes |
| `tags` | array of object | yes |
