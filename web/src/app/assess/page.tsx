"use client";

/* M3 demo flow (docs/architecture.md Sections 8, 9, 14): describe a system,
   see the deterministic classification, load judge-accepted requirements
   with citations, evaluate evidence, generate a backlog. The UI never
   touches the database or model APIs: every call goes to the thin HTTP
   facade, which calls the same pure functions the MCP server exposes.
   Every result card renders source citations (node ids and span ids), the
   judge verdict, the calibrated status vocabulary badge, and the page ends
   with the non-legal-advice notice. Visual system: docs/DESIGN.md. */

import { useState } from "react";

const FACADE_URL = "http://localhost:8008";
const MAX_BACKLOG_NORMS = 10;

type Span = Record<string, unknown>;

type Envelope<A = Record<string, unknown>> = {
  answer: A;
  status: string;
  confidence: number;
  source_nodes: string[];
  source_spans: Span[];
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

type RequirementsAnswer = {
  risk_category: string;
  requirements_by_article: Record<string, Requirement[]>;
  summary: { returned?: number; needs_human_review_total?: number };
  message?: string;
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

const PROHIBITION_FLAGS: [string, string][] = [
  ["subliminal_or_manipulative", "Subliminal or manipulative techniques"],
  ["exploits_vulnerabilities", "Exploits vulnerabilities (age, disability, situation)"],
  ["social_scoring", "Social scoring"],
  ["predictive_policing_profiling", "Predictive policing by profiling"],
  ["facial_image_scraping", "Untargeted facial image scraping"],
  ["emotion_recognition_workplace_or_education", "Emotion recognition at work / education"],
  ["biometric_categorisation", "Biometric categorisation (sensitive traits)"],
  ["real_time_remote_biometric_public", "Real-time remote biometric ID in public"],
  ["law_enforcement_use", "Law enforcement use"],
];

const CATEGORY_FLAGS: [string, string][] = [
  ["biometric_identification", "Biometric identification"],
  ["emotion_recognition", "Emotion recognition"],
  ["critical_infrastructure_safety", "Critical infrastructure safety component"],
  ["education_scoring_or_access", "Education scoring or access"],
  ["employment_decisions", "Employment decisions"],
  ["essential_services_access", "Essential services access (incl. healthcare)"],
  ["migration_asylum_border_use", "Migration, asylum, border control use"],
  ["justice_democratic_use", "Justice or democratic processes"],
  ["medical_or_safety_component", "Medical or product safety component"],
  ["preparatory_or_narrow_procedural_task", "Preparatory or narrow procedural task"],
  ["interacts_with_natural_persons", "Interacts with natural persons"],
  ["generates_synthetic_content", "Generates synthetic content"],
  ["profiling_of_natural_persons", "Profiling of natural persons"],
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

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
      {children}
    </code>
  );
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
const INPUT_CLS =
  "w-full border border-input bg-transparent rounded-md shadow-xs px-3 py-2 " +
  "text-base md:text-sm outline-none focus-visible:border-ring " +
  "focus-visible:ring-ring/50 focus-visible:ring-[3px]";
const SELECT_CLS =
  "h-9 border border-input bg-transparent rounded-md shadow-xs px-2 " +
  "text-base md:text-sm outline-none focus-visible:border-ring " +
  "focus-visible:ring-ring/50 focus-visible:ring-[3px]";

function TriStateSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      className={`${SELECT_CLS} h-8 px-1 text-xs`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="unknown">unknown</option>
      <option value="true">true</option>
      <option value="false">false</option>
    </select>
  );
}

export default function AssessPage() {
  const [description, setDescription] = useState("");
  const [domain, setDomain] = useState("");
  const [autonomy, setAutonomy] = useState("");
  const [flags, setFlags] = useState<Record<string, string>>({});

  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyError, setClassifyError] = useState<string | null>(null);
  const [classification, setClassification] =
    useState<Envelope<ClassificationAnswer> | null>(null);

  const [reqLoading, setReqLoading] = useState(false);
  const [reqError, setReqError] = useState<string | null>(null);
  const [requirements, setRequirements] =
    useState<Envelope<RequirementsAnswer> | null>(null);

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [evidenceUi, setEvidenceUi] = useState<Record<string, EvidenceUiState>>({});

  const [backlogLoading, setBacklogLoading] = useState(false);
  const [backlogError, setBacklogError] = useState<string | null>(null);
  const [backlogUsedIds, setBacklogUsedIds] = useState<string[]>([]);
  const [backlog, setBacklog] = useState<Envelope<BacklogAnswer> | null>(null);

  function buildFeatures() {
    const flagPayload: Record<string, boolean> = {};
    for (const [key, value] of Object.entries(flags)) {
      if (value === "true") flagPayload[key] = true;
      if (value === "false") flagPayload[key] = false;
      // "unknown" is omitted: absence is never treated as false.
    }
    const features: Record<string, unknown> = { description, flags: flagPayload };
    if (domain) features.domain = domain;
    if (autonomy) features.autonomy = autonomy;
    return features;
  }

  async function runClassify() {
    setClassifyLoading(true);
    setClassifyError(null);
    setRequirements(null);
    setBacklog(null);
    setSelected({});
    setEvidenceUi({});
    try {
      const envelope = await postJson<Envelope<ClassificationAnswer>>("/api/classify", {
        features: buildFeatures(),
      });
      setClassification(envelope);
    } catch (err) {
      setClassification(null);
      setClassifyError(err instanceof Error ? err.message : String(err));
    } finally {
      setClassifyLoading(false);
    }
  }

  async function loadRequirements() {
    if (!classification) return;
    setReqLoading(true);
    setReqError(null);
    setBacklog(null);
    try {
      const envelope = await postJson<Envelope<RequirementsAnswer>>("/api/requirements", {
        classification,
      });
      setRequirements(envelope);
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
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium leading-none" htmlFor="domain">
                  Domain
                </label>
                <select
                  id="domain"
                  className={`${SELECT_CLS} w-full`}
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
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
                <label className="text-sm font-medium leading-none" htmlFor="autonomy">
                  Autonomy
                </label>
                <select
                  id="autonomy"
                  className={`${SELECT_CLS} w-full`}
                  value={autonomy}
                  onChange={(e) => setAutonomy(e.target.value)}
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
                    <span className="leading-tight">{label}</span>
                    <TriStateSelect
                      value={flags[key] ?? "unknown"}
                      onChange={(v) => setFlags((prev) => ({ ...prev, [key]: v }))}
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
                    <span className="leading-tight">{label}</span>
                    <TriStateSelect
                      value={flags[key] ?? "unknown"}
                      onChange={(v) => setFlags((prev) => ({ ...prev, [key]: v }))}
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
              </div>
              {requirements.answer.message && (
                <p className="text-sm">{requirements.answer.message}</p>
              )}
              <div className="space-y-1">
                {Object.entries(grouped).map(([group, norms]) => (
                  <details key={group} className="rounded-md border border-border">
                    <summary className="cursor-pointer p-3 text-sm font-medium hover:bg-accent">
                      {group} ({norms.length} accepted norms)
                    </summary>
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
                  <div className="space-y-3">
                    {(backlog.answer.items ?? []).map((item) => (
                      <div
                        key={item.title}
                        className="rounded-lg border border-border bg-card shadow-sm p-4 space-y-2"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold">{item.title}</span>
                          <span className="rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                            {item.priority}
                          </span>
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
