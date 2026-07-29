"use client";

/* M3 demo flow (docs/architecture.md Sections 8, 9, 14): describe a system,
   see the deterministic classification, load judge-accepted requirements
   with citations, evaluate evidence, generate a backlog. The UI never
   touches the database or model APIs: every call goes to the thin HTTP
   facade, which calls the same pure functions the MCP server exposes.
   Every result card renders source citations (node ids and span ids), the
   judge verdict, the calibrated status vocabulary badge, and the page ends
   with the non-legal-advice notice. Visual system: docs/DESIGN.md. */

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { FACADE_URL } from "@/lib/facade";
import { SCENARIO_PRESETS, type ScenarioPreset } from "./presets";
import { EvidenceGraph, mergeSubgraphs, type GraphEvidenceSubgraph } from "./evidence-graph";

const MAX_BACKLOG_NORMS = 10;

type Span = Record<string, unknown>;

type Envelope<A = Record<string, unknown>> = {
  answer: A;
  status: string;
  confidence: number;
  source_nodes: string[];
  source_spans: Span[];
  graph_evidence_subgraph: GraphEvidenceSubgraph;
  legal_status_notes: string[];
  missing_facts: string[];
  judge_verdict: string;
  generated_at: string;
  graph_version: string;
  non_legal_advice_notice: string;
};

type ClassificationAnswer = {
  risk_category: string | null;
  prohibited: boolean;
  annex_iii_category: string | null;
  article_6_3_exception_candidate: boolean;
  rationale: string[];
};

type Requirement = {
  norm_id: string;
  deontic_type: string;
  modal: string;
  actor: string | null;
  actor_source: string;
  action: string;
  object: string;
  source_node_id: string;
  source_span_id: string;
  conditions?: string[];
};

/* Fact elicitation (DEC-13): the elicitor proposes schema-valid facts with
   textual support, never a risk category. answer is null when elicitation
   failed outright (see src/tere4ai/mcp_server/elicit.py); a present answer
   never omits notes. Purposes and deployer are elicitable per the schema but
   this form has no controls for them yet, so they are read, never applied. */
type ElicitFeatures = {
  description?: string;
  domain?: string | null;
  purposes?: string[];
  autonomy?: "advisory" | "partial" | "full" | null;
  flags?: Record<string, boolean>;
  deployer?: Record<string, boolean>;
};

type ElicitAnswer = { features: ElicitFeatures; notes: string[] } | null;

type ElicitPanelState = {
  notes: string[];
  status: string | null;
  confidence: number | null;
  missingFacts: string[];
  error: string | null;
};

type RequirementsAnswer = {
  risk_category: string;
  requirements_by_article: Record<string, Requirement[]>;
  summary: { returned?: number; needs_human_review_total?: number };
  message?: string;
};

/* Reified alignment chain as served by /api/trace/batch (trace_alignment
   pass-through): never a bare edge, always the assertion with its scores,
   judge verdict, runs, and evidence quotes on both sides (DEC-05). */
type AlignmentAssertion = {
  assertion_id: string;
  source_norm_id: string;
  target_id: string;
  relation_type: string;
  scores: Record<string, number>;
  final_score: number | null;
  judge_verdict: string;
  rationale: string | null;
  review_status: string | null;
  evidence: {
    source_evidence_span_ids: string[];
    target_evidence_span_ids: string[];
    source_quote: string | null;
    target_quote: string | null;
  };
  mapping_run: {
    id: string | null;
    generator_model: string | null;
    prompt_version: string | null;
  };
  judge_run: {
    id: string | null;
    judge_model: string | null;
    prompt_version: string | null;
    verdict: string | null;
    rationale: string | null;
    corrected_relation_type: string | null;
  };
};

type TraceAnswer = {
  id: string;
  found: boolean;
  mode?: string;
  assertion_count?: number;
  accepted_count?: number;
  caveat?: string;
  assertions?: AlignmentAssertion[];
  alignments_build_id?: string;
};

type TraceBatchResponse = {
  envelopes: Record<string, Envelope<TraceAnswer>>;
};

type EvidenceAnswer = {
  norm_id: string;
  artifact_type: string;
  assessment: string;
  quotes: string[];
  gaps: string[];
  rationale: string;
  judge_rationale: string;
  judge_model: string;
  notes: string[];
  refused?: boolean;
  message?: string;
};

type BacklogAnswer = {
  items: {
    title: string;
    description: string;
    norm_ids: string[];
    suggested_evidence: string[];
    priority: string;
  }[];
  dropped_items: number;
  truncated: boolean;
  notes: string[];
  judge_rationale: string;
  refused?: boolean;
  message?: string;
};

type EvidenceUiState = {
  artifactType: string;
  content: string;
  loading: boolean;
  result: Envelope<EvidenceAnswer> | null;
  error: string | null;
};

const NOTICE =
  "TERE4AI provides engineering and documentation support. It does not " +
  "certify EU AI Act compliance and does not replace legal review, " +
  "conformity assessment, or competent-authority interpretation.";

/* The seven HLEG Trustworthy AI requirements are a closed canonical set
   (USER.md domain guardrails). Ids and labels below are exactly those of
   the graph build (align_hleg_altai/hleg_nodes.py CANONICAL, over the
   frozen 2019 HLEG guidelines text). An id outside this map falls back to
   the raw id; a name is never invented. */
const HLEG_LABELS: Record<string, string> = {
  "hleg:human-agency-and-oversight": "Human agency and oversight",
  "hleg:technical-robustness-and-safety": "Technical robustness and safety",
  "hleg:privacy-and-data-governance": "Privacy and data governance",
  "hleg:transparency": "Transparency",
  "hleg:diversity-non-discrimination-and-fairness":
    "Diversity, non-discrimination and fairness",
  "hleg:societal-and-environmental-well-being":
    "Societal and environmental well-being",
  "hleg:accountability": "Accountability",
};

/* Mandatory caveat (USER.md domain guardrails): short form for the chips
   row footnote. The full caveat inside each expanded evidence view comes
   from the trace envelope itself (answer.caveat, server pass-through). */
const HLEG_CAVEAT_SHORT =
  "EU-to-HLEG mappings are LLM-generated, not expert-validated.";

const PROHIBITION_FLAGS: [string, string][] = [
  ["subliminal_or_manipulative", "Subliminal or manipulative techniques"],
  ["exploits_vulnerabilities", "Exploits vulnerabilities (age, disability, situation)"],
  ["causes_significant_harm", "Causes significant harm (Art. 5(1)(a)/(b) qualifier)"],
  ["social_scoring", "Social scoring"],
  [
    "social_score_detrimental_treatment",
    "Social score leads to detrimental treatment (Art. 5(1)(c) qualifier)",
  ],
  ["predictive_policing_profiling", "Predictive policing by profiling"],
  [
    "supports_human_assessment_on_verifiable_facts",
    "Supports human assessment on verifiable facts (Art. 5(1)(d) exception)",
  ],
  ["facial_image_scraping", "Untargeted facial image scraping"],
  ["emotion_recognition_workplace_or_education", "Emotion recognition at work / education"],
  [
    "emotion_recognition_medical_or_safety",
    "Emotion recognition for medical or safety reasons (Art. 5(1)(f) exception)",
  ],
  ["biometric_categorisation", "Biometric categorisation (sensitive traits)"],
  [
    "biometric_categorisation_lawful_or_law_enforcement",
    "Lawful dataset / law enforcement carve-out (Art. 5(1)(g))",
  ],
  ["real_time_remote_biometric_public", "Real-time remote biometric ID in public"],
  [
    "rtrb_strictly_necessary_authorised",
    "RTRB strictly necessary and authorised (Art. 5(1)(h) carve-out)",
  ],
  ["law_enforcement_use", "Law enforcement use"],
];

const CATEGORY_FLAGS: [string, string][] = [
  ["biometric_identification", "Biometric identification"],
  ["emotion_recognition", "Emotion recognition"],
  ["critical_infrastructure_safety", "Critical infrastructure safety component"],
  ["education_scoring_or_access", "Education scoring or access"],
  ["employment_decisions", "Employment decisions"],
  ["essential_services_access", "Essential services access (incl. healthcare)"],
  ["creditworthiness_evaluation", "Creditworthiness evaluation (Annex III point 5(b))"],
  [
    "life_health_insurance_risk_pricing",
    "Life / health insurance risk pricing (Annex III point 5(c))",
  ],
  ["migration_asylum_border_use", "Migration, asylum, border control use"],
  ["justice_democratic_use", "Justice or democratic processes"],
  ["medical_or_safety_component", "Medical or product safety component"],
  ["preparatory_or_narrow_procedural_task", "Preparatory or narrow procedural task"],
  [
    "improves_previous_human_activity",
    "Improves a previously completed human activity (Art. 6(3)(b))",
  ],
  [
    "detects_patterns_without_replacing_human_assessment",
    "Detects patterns without replacing human assessment (Art. 6(3)(c))",
  ],
  ["interacts_with_natural_persons", "Interacts with natural persons"],
  ["generates_synthetic_content", "Generates synthetic content"],
  ["profiling_of_natural_persons", "Profiling of natural persons"],
  ["annex_i_covered_product", "Annex I covered product / safety component"],
  [
    "third_party_conformity_assessment_required",
    "Third-party conformity assessment required",
  ],
];

const DOMAINS = [
  "healthcare",
  "education",
  "employment",
  "law_enforcement",
  "migration",
  "justice",
  "banking",
  "insurance",
  "critical_infrastructure",
  "consumer",
];

const ARTIFACT_TYPES = [
  "risk_management_plan",
  "technical_documentation",
  "data_governance_policy",
  "test_report",
  "logging_design",
  "human_oversight_procedure",
  "monitoring_plan",
  "other_documentation",
];

/* Audit permalink (#52): the describe-system inputs are serialized to JSON
   and carried base64url-encoded in the URL hash. Opening the link prefills
   the form and re-runs the same deterministic classification. Client-side
   only: the hash never reaches the facade or any server log. */
type AssessForm = {
  description: string;
  domain: string;
  autonomy: string;
  flags: Record<string, string>;
};

const PERMALINK_PREFIX = "#assess=";

function encodeAssessForm(form: AssessForm): string {
  const bytes = new TextEncoder().encode(JSON.stringify(form));
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeAssessForm(encoded: string): AssessForm | null {
  try {
    const b64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(b64);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    if (typeof parsed !== "object" || parsed === null) return null;
    return {
      description: typeof parsed.description === "string" ? parsed.description : "",
      domain: typeof parsed.domain === "string" ? parsed.domain : "",
      autonomy: typeof parsed.autonomy === "string" ? parsed.autonomy : "",
      flags:
        typeof parsed.flags === "object" && parsed.flags !== null
          ? (parsed.flags as Record<string, string>)
          : {},
    };
  } catch {
    return null;
  }
}

/* Envelope export (#52): saves the exact envelope object as returned by the
   facade (parsed response, re-serialized without modification). */
function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${FACADE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      data && typeof data.error === "string" ? data.error : `facade error ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

/* DESIGN.md status conventions: green for satisfied, red for rejected,
   muted for everything needing review. The vocabulary is closed (DEC-08). */
function StatusBadge({ status }: { status: string }) {
  const green = status === "satisfied_with_evidence";
  const red = status === "rejected_as_unsupported";
  const cls = green
    ? "text-green-600 dark:text-green-400 border-green-600/40"
    : red
      ? "text-destructive border-destructive/40"
      : "text-muted-foreground border-border";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}

/* Elicitation provenance marker (Task 3): the only provenance surface for an
   elicited control is this chip plus the notes panel. No per-fact quote
   affordance (recorded spec deviation; arrives with increment 2). Cleared
   the moment the user edits the control it sits on. */
function ElicitedChip() {
  return (
    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
      elicited
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
      {children}
    </code>
  );
}

/* HLEG alignment chips per norm card (judge-ACCEPTED assertions only; a
   norm with none renders nothing). Clicking a chip expands the full reified
   evidence: relation type, score dimensions, final score, judge verdict and
   rationale, and the verbatim evidence quotes from both sides. The quotes
   are byte-exact quote fields (DEC-08 verbatim exemption) and are never
   altered here. The mapping caveat renders in short form under the chips
   row and in full inside every expanded view (USER.md domain guardrail). */
function HlegAlignments({ envelope }: { envelope?: Envelope<TraceAnswer> }) {
  const [openTarget, setOpenTarget] = useState<string | null>(null);
  const accepted = (envelope?.answer.assertions ?? []).filter(
    (a) => a.judge_verdict === "accepted"
  );
  if (!envelope || accepted.length === 0) return null;
  const byTarget = new Map<string, AlignmentAssertion[]>();
  for (const assertion of accepted) {
    const list = byTarget.get(assertion.target_id) ?? [];
    list.push(assertion);
    byTarget.set(assertion.target_id, list);
  }
  const caveat = envelope.answer.caveat ?? HLEG_CAVEAT_SHORT;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {Array.from(byTarget.entries()).map(([target, list]) => (
          <button
            key={target}
            type="button"
            aria-expanded={openTarget === target}
            aria-label={`Toggle alignment evidence for ${HLEG_LABELS[target] ?? target}`}
            className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors ${
              openTarget === target
                ? "border-primary/40 text-primary bg-accent"
                : "border-border text-muted-foreground hover:bg-accent"
            }`}
            onClick={() => setOpenTarget(openTarget === target ? null : target)}
          >
            HLEG: {HLEG_LABELS[target] ?? target}
            {list.length > 1 ? ` (${list.length})` : ""}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{HLEG_CAVEAT_SHORT}</p>
      {openTarget !== null && byTarget.has(openTarget) && (
        <div className="rounded-md border border-border p-3 space-y-3">
          <p className="text-xs font-semibold">
            {HLEG_LABELS[openTarget] ?? openTarget}{" "}
            <code className="font-mono font-normal text-muted-foreground">
              {openTarget}
            </code>
          </p>
          {(byTarget.get(openTarget) ?? []).map((assertion) => (
            <div key={assertion.assertion_id} className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Chip>{assertion.relation_type}</Chip>
                <Chip>final score {assertion.final_score ?? "n/a"}</Chip>
                <span className="text-xs text-muted-foreground">
                  Judge verdict:{" "}
                  <code className="font-mono">{assertion.judge_verdict}</code>
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Scores:{" "}
                {Object.entries(assertion.scores)
                  .map(([name, value]) => `${name.replace(/_/g, " ")} ${value}`)
                  .join(", ")}
              </p>
              {assertion.rationale && (
                <p className="text-xs">
                  <span className="font-semibold">Rationale:</span>{" "}
                  <span className="text-muted-foreground">{assertion.rationale}</span>
                </p>
              )}
              {assertion.evidence.source_quote && (
                <blockquote className="border-l-2 border-border pl-3 text-sm text-muted-foreground">
                  &ldquo;{assertion.evidence.source_quote}&rdquo;{" "}
                  <span className="text-xs">(EU AI Act side)</span>
                </blockquote>
              )}
              {assertion.evidence.target_quote && (
                <blockquote className="border-l-2 border-border pl-3 text-sm text-muted-foreground">
                  &ldquo;{assertion.evidence.target_quote}&rdquo;{" "}
                  <span className="text-xs">(HLEG side)</span>
                </blockquote>
              )}
              <div className="flex flex-wrap gap-1.5">
                <Chip>{assertion.assertion_id}</Chip>
                {[
                  ...assertion.evidence.source_evidence_span_ids,
                  ...assertion.evidence.target_evidence_span_ids,
                ].map((spanId) => (
                  <Chip key={spanId}>{spanId}</Chip>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Mapping run: {assertion.mapping_run.generator_model ?? "unknown"} (prompt{" "}
                {assertion.mapping_run.prompt_version ?? "unknown"}); judge:{" "}
                {assertion.judge_run.judge_model ?? "unknown"} (prompt{" "}
                {assertion.judge_run.prompt_version ?? "unknown"})
              </p>
            </div>
          ))}
          <p className="text-xs text-muted-foreground border-t border-border pt-2">
            {caveat}
          </p>
        </div>
      )}
    </div>
  );
}

/* Node id -> span id, built from data already held by the page (never
   guessed): each requirement's own source_span_id covers its norm node and
   its source article/paragraph node (extract_norms records the same span
   id for both, verified against a live norms_core.json entry); each
   accepted alignment assertion's evidence span ids cover its source norm
   and HLEG target node when a requirement entry does not already. */
function buildNodeSpanIds(
  norms: Requirement[],
  alignments: Record<string, Envelope<TraceAnswer>> | null
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const norm of norms) {
    map[norm.norm_id] = norm.source_span_id;
    map[norm.source_node_id] = norm.source_span_id;
  }
  if (alignments) {
    for (const norm of norms) {
      for (const assertion of alignments[norm.norm_id]?.answer.assertions ?? []) {
        const sourceSpan = assertion.evidence.source_evidence_span_ids[0];
        const targetSpan = assertion.evidence.target_evidence_span_ids[0];
        if (sourceSpan && !map[assertion.source_norm_id]) {
          map[assertion.source_norm_id] = sourceSpan;
        }
        if (targetSpan && !map[assertion.target_id]) {
          map[assertion.target_id] = targetSpan;
        }
      }
    }
  }
  return map;
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-6 space-y-4">
      <h2 className="text-xl font-semibold leading-none">{title}</h2>
      {children}
    </section>
  );
}

/* Shared envelope footer: judge verdict, citations, missing facts, notes.
   Every result card on this screen carries this block (Section 9). */
const MAX_CITATION_CHIPS = 12;

function EnvelopeMeta({ envelope }: { envelope: Envelope<unknown> }) {
  const spanIds = Array.from(
    new Set(
      envelope.source_spans
        .map((s) => (s as { span_id?: unknown }).span_id)
        .filter((v): v is string => typeof v === "string")
    )
  );
  const nodeIds = Array.from(new Set(envelope.source_nodes));
  const chips = [...nodeIds, ...spanIds];
  const hidden = chips.length - MAX_CITATION_CHIPS;
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-muted-foreground">
        Judge verdict: <code className="font-mono">{envelope.judge_verdict}</code>, confidence{" "}
        {envelope.confidence}, graph{" "}
        <code className="font-mono">{envelope.graph_version}</code>
      </p>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {chips.slice(0, MAX_CITATION_CHIPS).map((c) => (
            <Chip key={c}>{c}</Chip>
          ))}
          {hidden > 0 && (
            <span className="text-xs text-muted-foreground">
              +{hidden} more citations (each norm above carries its own span chip)
            </span>
          )}
        </div>
      )}
      {envelope.legal_status_notes.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {envelope.legal_status_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {envelope.missing_facts.length > 0 && (
        <div>
          <p className="text-xs font-semibold">Missing facts</p>
          <ul className="list-disc pl-5 space-y-1 text-xs text-muted-foreground">
            {envelope.missing_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const BUTTON_PRIMARY =
  "inline-flex items-center justify-center h-9 px-4 rounded-md bg-primary " +
  "text-primary-foreground text-sm font-medium transition-all duration-200 " +
  "hover:opacity-90 disabled:pointer-events-none disabled:opacity-50";
const BUTTON_OUTLINE =
  "inline-flex items-center justify-center h-9 px-4 rounded-md border " +
  "border-input bg-transparent shadow-xs text-sm font-medium " +
  "transition-all duration-200 hover:bg-accent disabled:pointer-events-none " +
  "disabled:opacity-50";
const BUTTON_OUTLINE_SM =
  "inline-flex items-center justify-center h-8 px-3 rounded-md border " +
  "border-input bg-transparent shadow-xs text-xs font-medium " +
  "transition-all duration-200 hover:bg-accent disabled:pointer-events-none " +
  "disabled:opacity-50";
const INPUT_CLS =
  "w-full border border-input bg-transparent rounded-md shadow-xs px-3 py-2 " +
  "text-base md:text-sm outline-none focus-visible:border-ring " +
  "focus-visible:ring-ring/50 focus-visible:ring-[3px]";
const SELECT_CLS =
  "h-9 border border-input bg-transparent rounded-md shadow-xs px-2 " +
  "text-base md:text-sm outline-none focus-visible:border-ring " +
  "focus-visible:ring-ring/50 focus-visible:ring-[3px]";

function TriStateSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      className={`${SELECT_CLS} h-8 px-1 text-xs`}
      aria-label={`${label}: fact value`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="unknown">unknown</option>
      <option value="true">true</option>
      <option value="false">false</option>
    </select>
  );
}

function DownloadEnvelopeButton({
  envelope,
  filename,
}: {
  envelope: Envelope<unknown>;
  filename: string;
}) {
  return (
    <button
      type="button"
      className={BUTTON_OUTLINE_SM}
      onClick={() => downloadJson(filename, envelope)}
      aria-label={`Download the ${filename} facade envelope as JSON`}
    >
      Download envelope JSON
    </button>
  );
}

/* Backlog polish (#40): priority is the closed must/should vocabulary from
   the backlog tool (an invalid priority is recomputed mechanically there). */
function PriorityBadge({ priority }: { priority: string }) {
  const must = priority === "must";
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
        must ? "border-primary/40 text-primary" : "border-border text-muted-foreground"
      }`}
    >
      priority: {priority}
    </span>
  );
}

type BacklogItem = BacklogAnswer["items"][number];

function backlogArticleGroup(item: BacklogItem): string {
  for (const id of item.norm_ids) {
    const match = id.match(/eu-ai-act:(article-\d+|annex-[ivxlcdm]+)/i);
    if (match) return `eu-ai-act:${match[1]}`;
  }
  return "other sources";
}

function groupBacklogByArticle(items: BacklogItem[]): [string, BacklogItem[]][] {
  const groups = new Map<string, BacklogItem[]>();
  for (const item of items) {
    const group = backlogArticleGroup(item);
    const list = groups.get(group) ?? [];
    list.push(item);
    groups.set(group, list);
  }
  return Array.from(groups.entries()).sort(([a], [b]) => {
    const na = Number(a.match(/article-(\d+)/)?.[1] ?? 9999);
    const nb = Number(b.match(/article-(\d+)/)?.[1] ?? 9999);
    return na - nb || a.localeCompare(b);
  });
}

export default function AssessPage() {
  const [description, setDescription] = useState("");
  const [domain, setDomain] = useState("");
  const [autonomy, setAutonomy] = useState("");
  const [flags, setFlags] = useState<Record<string, string>>({});

  /* Fact elicitation (Task 3, DEC-13): a proposal only. elicitedFields marks
     which controls the last elicitation filled; editing a control after
     elicitation clears its own entry (never the others). */
  const [elicitLoading, setElicitLoading] = useState(false);
  const [elicitedFields, setElicitedFields] = useState<Record<string, boolean>>({});
  const [elicitPanel, setElicitPanel] = useState<ElicitPanelState | null>(null);

  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyError, setClassifyError] = useState<string | null>(null);
  const [classification, setClassification] =
    useState<Envelope<ClassificationAnswer> | null>(null);

  const [reqLoading, setReqLoading] = useState(false);
  const [reqError, setReqError] = useState<string | null>(null);
  const [requirements, setRequirements] =
    useState<Envelope<RequirementsAnswer> | null>(null);

  /* HLEG alignments for the served norms: one /api/trace/batch call per
     assessment (free, deterministic), keyed by norm_id. */
  const [alignments, setAlignments] = useState<Record<
    string,
    Envelope<TraceAnswer>
  > | null>(null);
  const [alignmentsError, setAlignmentsError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [evidenceUi, setEvidenceUi] = useState<Record<string, EvidenceUiState>>({});

  const [backlogLoading, setBacklogLoading] = useState(false);
  const [backlogError, setBacklogError] = useState<string | null>(null);
  const [backlogUsedIds, setBacklogUsedIds] = useState<string[]>([]);
  const [backlog, setBacklog] = useState<Envelope<BacklogAnswer> | null>(null);

  const [permalink, setPermalink] = useState<string | null>(null);
  const [permalinkCopied, setPermalinkCopied] = useState(false);

  async function classifyWith(form: AssessForm) {
    setClassifyLoading(true);
    setClassifyError(null);
    setRequirements(null);
    setAlignments(null);
    setAlignmentsError(null);
    setBacklog(null);
    setSelected({});
    setEvidenceUi({});
    setPermalinkCopied(false);
    const encoded = encodeAssessForm(form);
    window.history.replaceState(null, "", `${PERMALINK_PREFIX}${encoded}`);
    setPermalink(
      `${window.location.origin}${window.location.pathname}${PERMALINK_PREFIX}${encoded}`
    );
    const flagPayload: Record<string, boolean> = {};
    for (const [key, value] of Object.entries(form.flags)) {
      if (value === "true") flagPayload[key] = true;
      if (value === "false") flagPayload[key] = false;
      // "unknown" is omitted: absence is never treated as false.
    }
    const features: Record<string, unknown> = {
      description: form.description,
      flags: flagPayload,
    };
    if (form.domain) features.domain = form.domain;
    if (form.autonomy) features.autonomy = form.autonomy;
    try {
      const envelope = await postJson<Envelope<ClassificationAnswer>>("/api/classify", {
        features,
      });
      setClassification(envelope);
    } catch (err) {
      setClassification(null);
      setClassifyError(err instanceof Error ? err.message : String(err));
    } finally {
      setClassifyLoading(false);
    }
  }

  function runClassify() {
    void classifyWith({ description, domain, autonomy, flags });
  }

  /* Clears one control's "elicited" chip the moment the user edits it after
     an elicitation run. Never touches the other marked controls. */
  function clearElicited(field: string) {
    setElicitedFields((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  /* Task 3 (DEC-13): one paid generator call, proposal only. Never fills a
     risk category, never shows a per-fact quote (out of scope by decision,
     recorded spec deviation; per-fact quotes arrive with increment 2). The
     elicitation notes panel is the sole provenance surface. Degrades to a
     visible error, never an empty result (architecture.md Section 13). */
  async function runElicit() {
    if (description.trim().length < 30) return;
    setElicitLoading(true);
    try {
      const envelope = await postJson<Envelope<ElicitAnswer>>("/api/elicit", {
        description,
      });
      if (envelope.answer) {
        const { features, notes } = envelope.answer;
        const filled: Record<string, boolean> = {};
        if (typeof features.domain === "string" && features.domain.length > 0) {
          setDomain(features.domain);
          filled.domain = true;
        }
        if (features.autonomy) {
          setAutonomy(features.autonomy);
          filled.autonomy = true;
        }
        if (features.flags) {
          const entries = Object.entries(features.flags);
          if (entries.length > 0) {
            setFlags((prev) => {
              const next = { ...prev };
              for (const [key, value] of entries) next[key] = value ? "true" : "false";
              return next;
            });
            for (const [key] of entries) filled[key] = true;
          }
        }
        setElicitedFields((prev) => ({ ...prev, ...filled }));
        setElicitPanel({
          notes,
          status: envelope.status,
          confidence: envelope.confidence,
          missingFacts: envelope.missing_facts,
          error: null,
        });
      } else {
        // Elicitation failed outright: fill nothing, surface the envelope's
        // own notes (legal_status_notes) and missing_facts.
        setElicitPanel({
          notes: envelope.legal_status_notes,
          status: envelope.status,
          confidence: envelope.confidence,
          missingFacts: envelope.missing_facts,
          error: null,
        });
      }
    } catch (err) {
      setElicitPanel({
        notes: [],
        status: null,
        confidence: null,
        missingFacts: [],
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setElicitLoading(false);
    }
  }

  /* Audit permalink (#52): a reload with #assess=<base64url> prefills the
     form and re-runs the same deterministic classification (free, no model
     call), so a reviewer can reproduce the exact assessment from the link. */
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash.startsWith(PERMALINK_PREFIX)) return;
    const form = decodeAssessForm(hash.slice(PERMALINK_PREFIX.length));
    if (!form || form.description.trim().length < 10) return;
    setDescription(form.description);
    setDomain(form.domain);
    setAutonomy(form.autonomy);
    setFlags(form.flags);
    void classifyWith(form);
    // Run once on mount only; the hash is the source of truth at load time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function copyPermalink() {
    if (!permalink) return;
    try {
      await navigator.clipboard.writeText(permalink);
      setPermalinkCopied(true);
      window.setTimeout(() => setPermalinkCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (permissions, non-secure context);
      // the read-only input below still allows manual copy.
    }
  }

  /* Preset (#53): fills the form in one click and clears downstream results
     so no stale envelope sits under new inputs. Classification still runs
     through the facade when the user clicks Classify. */
  function applyPreset(preset: ScenarioPreset) {
    setDescription(preset.description);
    setDomain(preset.domain);
    setAutonomy(preset.autonomy);
    setFlags({ ...preset.flags });
    setClassification(null);
    setClassifyError(null);
    setRequirements(null);
    setReqError(null);
    setAlignments(null);
    setAlignmentsError(null);
    setBacklog(null);
    setBacklogError(null);
    setSelected({});
    setEvidenceUi({});
    setPermalink(null);
    setElicitedFields({});
    setElicitPanel(null);
  }

  async function loadRequirements() {
    if (!classification) return;
    setReqLoading(true);
    setReqError(null);
    setBacklog(null);
    setAlignments(null);
    setAlignmentsError(null);
    try {
      const envelope = await postJson<Envelope<RequirementsAnswer>>("/api/requirements", {
        classification,
      });
      setRequirements(envelope);
      /* One bulk call for the HLEG chips of every served norm (no per-norm
         request flood). A failure degrades to a visible note, never silently
         (architecture.md Section 13); the requirements themselves stand. */
      const normIds = Object.values(envelope.answer.requirements_by_article ?? {})
        .flat()
        .map((n) => n.norm_id);
      if (normIds.length > 0) {
        try {
          const batch = await postJson<TraceBatchResponse>("/api/trace/batch", {
            ids: normIds,
          });
          setAlignments(batch.envelopes);
        } catch (err) {
          setAlignmentsError(err instanceof Error ? err.message : String(err));
        }
      }
    } catch (err) {
      setRequirements(null);
      setReqError(err instanceof Error ? err.message : String(err));
    } finally {
      setReqLoading(false);
    }
  }

  function evidenceStateFor(normId: string): EvidenceUiState {
    return (
      evidenceUi[normId] ?? {
        artifactType: ARTIFACT_TYPES[0],
        content: "",
        loading: false,
        result: null,
        error: null,
      }
    );
  }

  function patchEvidence(normId: string, patch: Partial<EvidenceUiState>) {
    setEvidenceUi((prev) => ({
      ...prev,
      [normId]: { ...evidenceStateFor(normId), ...prev[normId], ...patch },
    }));
  }

  async function evaluateEvidence(normId: string) {
    const state = evidenceStateFor(normId);
    patchEvidence(normId, { loading: true, error: null, result: null });
    try {
      const envelope = await postJson<Envelope<EvidenceAnswer>>("/api/evidence", {
        norm_id: normId,
        artifact_type: state.artifactType,
        content: state.content,
      });
      patchEvidence(normId, { loading: false, result: envelope });
    } catch (err) {
      patchEvidence(normId, {
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const grouped = requirements?.answer.requirements_by_article ?? {};
  const allNorms: Requirement[] = Object.values(grouped).flat();
  const selectedIds = allNorms
    .map((n) => n.norm_id)
    .filter((id) => selected[id]);
  const backlogIds = (selectedIds.length > 0 ? selectedIds : allNorms.map((n) => n.norm_id)).slice(
    0,
    MAX_BACKLOG_NORMS
  );

  async function generateBacklog() {
    if (backlogIds.length === 0) return;
    setBacklogLoading(true);
    setBacklogError(null);
    setBacklogUsedIds(backlogIds);
    try {
      const envelope = await postJson<Envelope<BacklogAnswer>>("/api/backlog", {
        norm_ids: backlogIds,
        system_context: description,
      });
      setBacklog(envelope);
    } catch (err) {
      setBacklog(null);
      setBacklogError(err instanceof Error ? err.message : String(err));
    } finally {
      setBacklogLoading(false);
    }
  }

  const risk = classification?.answer.risk_category;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Assess an AI system</h1>
          <p className="text-sm text-muted-foreground">
            M3 demo flow: deterministic classification, judge-accepted requirements with
            citations, evidence evaluation, and a control backlog. All calls go through the
            local facade at <code className="font-mono">{FACADE_URL}</code>.
          </p>
        </div>

        <Card title="1. Describe the system">
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm font-medium leading-none">
                Canonical scenarios (one click fills the form; classification still runs
                through the deterministic ladder)
              </p>
              <div className="flex flex-wrap gap-2">
                {SCENARIO_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    className={BUTTON_OUTLINE}
                    onClick={() => applyPreset(preset)}
                    aria-label={`Fill the form with the ${preset.label} scenario`}
                  >
                    <span>{preset.label}</span>
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {preset.hint}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none" htmlFor="description">
                Plain-language description (context only; classification rests on the
                structured facts below)
              </label>
              <textarea
                id="description"
                className={`${INPUT_CLS} min-h-16`}
                rows={3}
                placeholder="e.g. An AI triage assistant that prioritises emergency department patients by predicted urgency to support clinician decisions."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  type="button"
                  className={BUTTON_OUTLINE}
                  onClick={() => void runElicit()}
                  disabled={elicitLoading || description.trim().length < 30}
                >
                  {elicitLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                      Eliciting...
                    </>
                  ) : (
                    "Elicit facts from description"
                  )}
                </button>
                <span className="text-xs text-muted-foreground">
                  {description.trim().length}/30 characters minimum. Paid model call:
                  proposes domain, autonomy, and flags below for you to confirm or edit;
                  it never decides the classification.
                </span>
              </div>
              {elicitPanel && (
                <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      {elicitPanel.status && <StatusBadge status={elicitPanel.status} />}
                      {elicitPanel.confidence !== null && (
                        <span className="text-xs text-muted-foreground">
                          confidence {elicitPanel.confidence}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="text-xs text-muted-foreground hover:text-foreground"
                      onClick={() => setElicitPanel(null)}
                      aria-label="Dismiss the elicitation panel"
                    >
                      Dismiss
                    </button>
                  </div>
                  {elicitPanel.error && (
                    <p className="text-sm text-destructive">{elicitPanel.error}</p>
                  )}
                  {elicitPanel.notes.length > 0 && (
                    <ul className="list-disc pl-5 space-y-1 text-xs text-muted-foreground">
                      {elicitPanel.notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  )}
                  {elicitPanel.missingFacts.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold">Missing facts</p>
                      <ul className="list-disc pl-5 space-y-1 text-xs text-muted-foreground">
                        {elicitPanel.missingFacts.map((fact) => (
                          <li key={fact}>{fact}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-xs font-medium border-t border-amber-500/30 pt-2">
                    Elicited facts are proposals: confirm or edit them, the deterministic
                    ladder alone decides.
                  </p>
                </div>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label
                  className="flex items-center gap-2 text-sm font-medium leading-none"
                  htmlFor="domain"
                >
                  Domain
                  {elicitedFields.domain && <ElicitedChip />}
                </label>
                <select
                  id="domain"
                  className={`${SELECT_CLS} w-full`}
                  value={domain}
                  onChange={(e) => {
                    setDomain(e.target.value);
                    clearElicited("domain");
                  }}
                >
                  <option value="">(unspecified)</option>
                  {DOMAINS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label
                  className="flex items-center gap-2 text-sm font-medium leading-none"
                  htmlFor="autonomy"
                >
                  Autonomy
                  {elicitedFields.autonomy && <ElicitedChip />}
                </label>
                <select
                  id="autonomy"
                  className={`${SELECT_CLS} w-full`}
                  value={autonomy}
                  onChange={(e) => {
                    setAutonomy(e.target.value);
                    clearElicited("autonomy");
                  }}
                >
                  <option value="">(unspecified)</option>
                  <option value="advisory">advisory (informs a human decision)</option>
                  <option value="partial">partial</option>
                  <option value="full">full</option>
                </select>
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium leading-none">
                Prohibition-relevant facts (Article 5). Unknown is never treated as false.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {PROHIBITION_FLAGS.map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-1.5 leading-tight">
                      {label}
                      {elicitedFields[key] && <ElicitedChip />}
                    </span>
                    <TriStateSelect
                      label={label}
                      value={flags[key] ?? "unknown"}
                      onChange={(v) => {
                        setFlags((prev) => ({ ...prev, [key]: v }));
                        clearElicited(key);
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium leading-none">
                High-risk and transparency facts (Article 6 + Annex III, Article 50)
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {CATEGORY_FLAGS.map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-1.5 leading-tight">
                      {label}
                      {elicitedFields[key] && <ElicitedChip />}
                    </span>
                    <TriStateSelect
                      label={label}
                      value={flags[key] ?? "unknown"}
                      onChange={(v) => {
                        setFlags((prev) => ({ ...prev, [key]: v }));
                        clearElicited(key);
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                className={BUTTON_PRIMARY}
                onClick={runClassify}
                disabled={classifyLoading || description.trim().length < 10}
              >
                {classifyLoading ? "Classifying..." : "Classify"}
              </button>
              <span className="text-xs text-muted-foreground">
                Deterministic rule ladder, free, no model call.
              </span>
            </div>
            {classifyError && <p className="text-sm text-destructive">{classifyError}</p>}
          </div>
        </Card>

        {classification && (
          <Card title="2. Classification">
            <div className="space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <span
                  className={`text-2xl font-bold ${
                    risk === "prohibited" ? "text-destructive" : ""
                  }`}
                >
                  {risk ?? "(rejected input)"}
                </span>
                <StatusBadge status={classification.status} />
                {classification.answer.annex_iii_category && (
                  <Chip>{classification.answer.annex_iii_category}</Chip>
                )}
              </div>
              {risk === "prohibited" && (
                <p className="text-sm text-destructive">
                  Prohibited AI practice under Article 5: no engineering requirement can make
                  this system permissible. Seek legal review.
                </p>
              )}
              <ul className="list-disc pl-5 space-y-1 text-sm">
                {classification.answer.rationale.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <EnvelopeMeta envelope={classification} />
              <EvidenceGraph subgraph={classification.graph_evidence_subgraph} />
              <div className="space-y-2 rounded-md border border-border p-3">
                <p className="text-xs font-semibold">Audit export</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <DownloadEnvelopeButton
                    envelope={classification}
                    filename="tere4ai-classification-envelope.json"
                  />
                  <button
                    type="button"
                    className={BUTTON_OUTLINE_SM}
                    onClick={copyPermalink}
                    disabled={!permalink}
                  >
                    {permalinkCopied ? "Copied" : "Copy permalink"}
                  </button>
                </div>
                {permalink && (
                  <>
                    <input
                      readOnly
                      aria-label="Audit permalink encoding the assessment inputs"
                      className={`${INPUT_CLS} font-mono text-xs`}
                      value={permalink}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <p className="text-xs text-muted-foreground">
                      The link carries the describe-system inputs (base64 in the URL
                      hash). Opening it prefills the form and re-runs the same
                      deterministic classification.
                    </p>
                  </>
                )}
              </div>
              <div className="flex items-center gap-3">
                <button
                  className={BUTTON_PRIMARY}
                  onClick={loadRequirements}
                  disabled={reqLoading}
                >
                  {reqLoading ? "Loading..." : "Load requirements"}
                </button>
                <span className="text-xs text-muted-foreground">
                  Judge-accepted norms only, grouped by article. Free, no model call.
                </span>
              </div>
              {reqError && <p className="text-sm text-destructive">{reqError}</p>}
            </div>
          </Card>
        )}

        {requirements && (
          <Card title="3. Applicable requirements">
            <div className="space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <StatusBadge status={requirements.status} />
                <span className="text-sm text-muted-foreground">
                  {requirements.answer.summary?.returned ?? 0} judge-accepted norms returned
                  {typeof requirements.answer.summary?.needs_human_review_total === "number"
                    ? `, ${requirements.answer.summary.needs_human_review_total} in the human review queue (never returned as requirements)`
                    : ""}
                </span>
                <DownloadEnvelopeButton
                  envelope={requirements}
                  filename="tere4ai-requirements-envelope.json"
                />
              </div>
              {requirements.answer.message && (
                <p className="text-sm">{requirements.answer.message}</p>
              )}
              {alignmentsError && (
                <p className="text-sm text-destructive">
                  HLEG alignment chips unavailable: {alignmentsError}
                </p>
              )}
              <div className="space-y-1">
                {Object.entries(grouped).map(([group, norms]) => (
                  <details key={group} className="rounded-md border border-border">
                    <summary className="cursor-pointer p-3 text-sm font-medium hover:bg-accent">
                      {group} ({norms.length} accepted norms)
                    </summary>
                    <EvidenceGraph
                      subgraph={mergeSubgraphs(
                        norms.map((n) => alignments?.[n.norm_id]?.graph_evidence_subgraph)
                      )}
                      nodeSpanIds={buildNodeSpanIds(norms, alignments)}
                    />
                    <div>
                      {norms.map((norm) => {
                        const ev = evidenceStateFor(norm.norm_id);
                        return (
                          <div
                            key={norm.norm_id}
                            className="border-t border-border p-3 space-y-2"
                          >
                            <div className="flex items-start gap-2">
                              <input
                                type="checkbox"
                                className="mt-1"
                                aria-label={`select ${norm.norm_id} for the backlog`}
                                checked={!!selected[norm.norm_id]}
                                onChange={(e) =>
                                  setSelected((prev) => ({
                                    ...prev,
                                    [norm.norm_id]: e.target.checked,
                                  }))
                                }
                              />
                              <div className="space-y-2 min-w-0">
                                <p className="text-sm leading-6">
                                  <span className="font-semibold">
                                    {norm.actor ?? "unspecified actor"}
                                  </span>{" "}
                                  <span className="text-xs font-semibold uppercase text-muted-foreground">
                                    {norm.modal}
                                  </span>{" "}
                                  {norm.action}{" "}
                                  <span className="text-muted-foreground">{norm.object}</span>
                                  {norm.actor_source === "inferred" && (
                                    <span className="text-xs text-muted-foreground">
                                      {" "}
                                      (actor inferred)
                                    </span>
                                  )}
                                </p>
                                {norm.conditions && norm.conditions.length > 0 && (
                                  <p className="text-xs text-muted-foreground">
                                    Conditions: {norm.conditions.join("; ")}
                                  </p>
                                )}
                                <div className="flex flex-wrap gap-1.5">
                                  <Chip>{norm.norm_id}</Chip>
                                  <Chip>{norm.source_node_id}</Chip>
                                  <Chip>{norm.source_span_id}</Chip>
                                </div>
                                <HlegAlignments
                                  envelope={alignments?.[norm.norm_id]}
                                />

                                <details className="rounded-md border border-border">
                                  <summary className="cursor-pointer p-2 text-xs font-medium hover:bg-accent">
                                    Evaluate evidence against this norm
                                  </summary>
                                  <div className="p-3 space-y-3 border-t border-border">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                      <select
                                        className={SELECT_CLS}
                                        aria-label="artifact type"
                                        value={ev.artifactType}
                                        onChange={(e) =>
                                          patchEvidence(norm.norm_id, {
                                            artifactType: e.target.value,
                                          })
                                        }
                                      >
                                        {ARTIFACT_TYPES.map((t) => (
                                          <option key={t} value={t}>
                                            {t}
                                          </option>
                                        ))}
                                      </select>
                                    </div>
                                    <textarea
                                      className={`${INPUT_CLS} min-h-16`}
                                      rows={4}
                                      placeholder="Paste the evidence artifact content (untrusted input; evaluated verbatim)"
                                      value={ev.content}
                                      onChange={(e) =>
                                        patchEvidence(norm.norm_id, {
                                          content: e.target.value,
                                        })
                                      }
                                    />
                                    <div className="flex items-center gap-3 flex-wrap">
                                      <button
                                        className={BUTTON_OUTLINE}
                                        onClick={() => evaluateEvidence(norm.norm_id)}
                                        disabled={ev.loading || ev.content.trim().length === 0}
                                      >
                                        {ev.loading ? "Evaluating..." : "Evaluate evidence"}
                                      </button>
                                      <span className="text-xs text-muted-foreground">
                                        Paid model call: OpenAI generator plus Anthropic
                                        grounding judge.
                                      </span>
                                    </div>
                                    {ev.error && (
                                      <p className="text-sm text-destructive">{ev.error}</p>
                                    )}
                                    {ev.result && (
                                      <div className="rounded-lg border border-border bg-card shadow-sm p-4 space-y-3">
                                        <div className="flex items-center gap-3 flex-wrap">
                                          <span className="text-sm font-semibold">
                                            Assessment: {ev.result.answer.assessment}
                                          </span>
                                          <StatusBadge status={ev.result.status} />
                                        </div>
                                        {ev.result.answer.message && (
                                          <p className="text-sm">{ev.result.answer.message}</p>
                                        )}
                                        {ev.result.answer.quotes?.length > 0 && (
                                          <div className="space-y-1">
                                            <p className="text-xs font-semibold">
                                              Surviving verbatim quotes
                                            </p>
                                            {ev.result.answer.quotes.map((q) => (
                                              <blockquote
                                                key={q}
                                                className="border-l-2 border-border pl-3 text-sm text-muted-foreground"
                                              >
                                                &ldquo;{q}&rdquo;
                                              </blockquote>
                                            ))}
                                          </div>
                                        )}
                                        {ev.result.answer.gaps?.length > 0 && (
                                          <div>
                                            <p className="text-xs font-semibold">Gaps</p>
                                            <ul className="list-disc pl-5 space-y-1 text-sm">
                                              {ev.result.answer.gaps.map((g) => (
                                                <li key={g}>{g}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}
                                        {ev.result.answer.rationale && (
                                          <p className="text-sm">
                                            <span className="font-semibold">Rationale:</span>{" "}
                                            {ev.result.answer.rationale}
                                          </p>
                                        )}
                                        <p className="text-sm">
                                          <span className="font-semibold">
                                            Judge verdict:
                                          </span>{" "}
                                          <code className="font-mono text-xs">
                                            {ev.result.judge_verdict}
                                          </code>{" "}
                                          <span className="text-muted-foreground">
                                            {ev.result.answer.judge_rationale}
                                          </span>
                                        </p>
                                        <EnvelopeMeta envelope={ev.result} />
                                        <DownloadEnvelopeButton
                                          envelope={ev.result}
                                          filename={`tere4ai-evidence-envelope-${norm.norm_id.replace(/[^a-z0-9-]+/gi, "_")}.json`}
                                        />
                                      </div>
                                    )}
                                  </div>
                                </details>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                ))}
              </div>
              <EnvelopeMeta envelope={requirements} />
            </div>
          </Card>
        )}

        {requirements && allNorms.length > 0 && (
          <Card title="4. Control backlog">
            <div className="space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  className={BUTTON_PRIMARY}
                  onClick={generateBacklog}
                  disabled={backlogLoading || backlogIds.length === 0}
                >
                  {backlogLoading ? "Generating..." : "Generate backlog"}
                </button>
                <span className="text-xs text-muted-foreground">
                  Paid model call: OpenAI generator plus Anthropic grounding judge. Uses{" "}
                  {selectedIds.length > 0
                    ? `the ${backlogIds.length} selected norms`
                    : `the first ${backlogIds.length} accepted norms`}{" "}
                  (max {MAX_BACKLOG_NORMS}).
                </span>
              </div>
              {backlogError && <p className="text-sm text-destructive">{backlogError}</p>}
              {backlog && (
                <div className="space-y-4">
                  <div className="flex items-center gap-3 flex-wrap">
                    <StatusBadge status={backlog.status} />
                    <span className="text-xs text-muted-foreground">
                      generated from {backlogUsedIds.length} norms
                      {backlog.answer.dropped_items > 0
                        ? `, ${backlog.answer.dropped_items} item(s) dropped by the mechanical citation check`
                        : ""}
                    </span>
                  </div>
                  {backlog.answer.message && (
                    <p className="text-sm">{backlog.answer.message}</p>
                  )}
                  <div className="space-y-4">
                    {groupBacklogByArticle(backlog.answer.items ?? []).map(
                      ([group, items]) => (
                        <div key={group} className="space-y-2">
                          <h3 className="text-sm font-semibold">
                            <code className="font-mono">{group}</code>{" "}
                            <span className="font-normal text-muted-foreground">
                              ({items.length} backlog item{items.length === 1 ? "" : "s"})
                            </span>
                          </h3>
                          <div className="space-y-3">
                            {items.map((item) => (
                              <div
                                key={item.title}
                                className="rounded-lg border border-border bg-card shadow-sm p-4 space-y-2"
                              >
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-sm font-semibold">{item.title}</span>
                                  <PriorityBadge priority={item.priority} />
                                </div>
                                <p className="text-sm">{item.description}</p>
                                <div className="flex flex-wrap gap-1.5">
                                  {item.norm_ids.map((id) => (
                                    <Chip key={id}>{id}</Chip>
                                  ))}
                                </div>
                                {item.suggested_evidence.length > 0 && (
                                  <p className="text-xs text-muted-foreground">
                                    Suggested evidence: {item.suggested_evidence.join(", ")}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )
                    )}
                  </div>
                  {backlog.answer.judge_rationale && (
                    <p className="text-sm">
                      <span className="font-semibold">Judge verdict:</span>{" "}
                      <code className="font-mono text-xs">{backlog.judge_verdict}</code>{" "}
                      <span className="text-muted-foreground">
                        {backlog.answer.judge_rationale}
                      </span>
                    </p>
                  )}
                  <EnvelopeMeta envelope={backlog} />
                  <DownloadEnvelopeButton
                    envelope={backlog}
                    filename="tere4ai-backlog-envelope.json"
                  />
                </div>
              )}
            </div>
          </Card>
        )}

        <div className="rounded-lg border border-border bg-muted/50 p-4">
          <p className="text-xs text-muted-foreground">
            {classification?.non_legal_advice_notice ?? NOTICE}
          </p>
        </div>
      </div>
    </div>
  );
}
